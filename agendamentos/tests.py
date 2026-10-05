"""Testes de regressão para os bugs e falhas corrigidos.

Cada teste referencia o comportamento que estava quebrado antes da correção.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import AgendamentoForm, SolicitacaoInstalacaoForm
from .models import Agendamento, Computador, Laboratorio, Perfil, Software, SolicitacaoInstalacao, TipoAgendamento


def id_tipo(nome='Estudo'):
    """Id de um dos tipos criados pela migração de dados (busca por trecho do nome)."""
    return TipoAgendamento.objects.get(nome__istartswith=nome).id


def proximo_bloco(delta=timedelta(hours=2), bloco=30):
    """Horário local futuro alinhado a blocos de `bloco` minutos (regra de agendamento)."""
    dt = timezone.localtime(timezone.now() + delta).replace(second=0, microsecond=0)
    resto = dt.minute % bloco
    return dt + timedelta(minutes=bloco - resto) if resto else dt


def criar_usuario(username, tipo='ALUNO', aprovado=True, **kwargs):
    user = User.objects.create_user(username=username, password='senha-de-teste-123', **kwargs)
    # O Perfil é criado por signal; aqui apenas ajustamos tipo/aprovação.
    Perfil.objects.filter(usuario=user).update(tipo=tipo, aprovado=aprovado)
    user.refresh_from_db()
    return user


class PerfilSignalTests(TestCase):
    def test_perfil_criado_junto_com_usuario(self):
        """Antes, o Perfil só nascia quando um admin abria a tela de liberação."""
        user = User.objects.create_user(username='novato', password='x')
        self.assertTrue(Perfil.objects.filter(usuario=user).exists())
        self.assertFalse(user.perfil.aprovado)

    def test_superusuario_ja_nasce_admin_aprovado(self):
        root = User.objects.create_superuser(username='root', password='x', email='r@e.com')
        self.assertEqual(root.perfil.tipo, 'ADMIN')
        self.assertTrue(root.perfil.aprovado)


class AgendamentoFormTests(TestCase):
    def _dados(self, **over):
        inicio = proximo_bloco(timedelta(hours=2))
        dados = {
            'tipo': id_tipo('Estudo'),
            'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
            'data_hora_fim': (inicio + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        }
        dados.update(over)
        return dados

    def test_form_valido_com_tipo(self):
        self.assertTrue(AgendamentoForm(self._dados()).is_valid())

    def test_tipo_ausente_invalida_o_form(self):
        """Regressão: o template não renderizava `finalidade`, então nenhuma
        reserva podia ser criada. O campo continua obrigatório de propósito."""
        dados = self._dados()
        del dados['tipo']
        form = AgendamentoForm(dados)
        self.assertFalse(form.is_valid())
        self.assertIn('tipo', form.errors)

    def test_rejeita_duracao_acima_de_duas_horas(self):
        inicio = proximo_bloco(timedelta(hours=2))
        form = AgendamentoForm(self._dados(
            data_hora_fim=(inicio + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')
        ))
        self.assertFalse(form.is_valid())

    def test_rejeita_inicio_no_passado(self):
        passado = proximo_bloco(timedelta(hours=-3))
        form = AgendamentoForm(self._dados(
            data_hora_inicio=passado.strftime('%Y-%m-%d %H:%M'),
            data_hora_fim=(passado + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        ))
        self.assertFalse(form.is_valid())

    def test_rejeita_antecedencia_maior_que_30_dias(self):
        distante = proximo_bloco(timedelta(days=45))
        form = AgendamentoForm(self._dados(
            data_hora_inicio=distante.strftime('%Y-%m-%d %H:%M'),
            data_hora_fim=(distante + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        ))
        self.assertFalse(form.is_valid())


class CriarAgendamentoViewTests(TestCase):
    def setUp(self):
        self.lab = Laboratorio.objects.create(nome='Lab 01', capacidade=10)
        self.pc = Computador.objects.create(
            identificador='PC-01', laboratorio=self.lab
        )
        TipoAgendamento.objects.filter(nome__istartswith='Desenv').update(valor_hora=Decimal('5.00'), modo='FIXO')
        self.aluno = criar_usuario('aluno')
        self.client.force_login(self.aluno)

    def _payload(self, horas=2, offset=1):
        inicio = proximo_bloco(timedelta(hours=offset))
        return {
            'tipo': id_tipo('Desenvolvimento'),
            'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
            'data_hora_fim': (inicio + timedelta(hours=horas)).strftime('%Y-%m-%d %H:%M'),
        }

    def test_usuario_aprovado_consegue_reservar(self):
        resposta = self.client.post(reverse('criar_agendamento', args=[self.pc.id]), self._payload())
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_valor_total_calculado_pela_tarifa(self):
        self.client.post(reverse('criar_agendamento', args=[self.pc.id]), self._payload(horas=2))
        self.assertEqual(Agendamento.objects.get().valor_total, Decimal('10.00'))

    def test_bloqueia_horario_sobreposto(self):
        payload = self._payload()
        self.client.post(reverse('criar_agendamento', args=[self.pc.id]), payload)
        self.client.post(reverse('criar_agendamento', args=[self.pc.id]), payload)
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_maquina_em_manutencao_nao_aceita_reserva(self):
        self.pc.status = 'MANUTENCAO'
        self.pc.save()
        resposta = self.client.post(reverse('criar_agendamento', args=[self.pc.id]), self._payload())
        self.assertRedirects(resposta, reverse('home'))
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_usuario_nao_aprovado_e_bloqueado(self):
        pendente = criar_usuario('pendente', aprovado=False)
        self.client.force_login(pendente)
        resposta = self.client.post(reverse('criar_agendamento', args=[self.pc.id]), self._payload())
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Agendamento.objects.count(), 0)


class CancelamentoTests(TestCase):
    def setUp(self):
        self.lab = Laboratorio.objects.create(nome='Lab 01')
        self.pc = Computador.objects.create(identificador='PC-01', laboratorio=self.lab)
        self.dono = criar_usuario('dono')
        self.outro = criar_usuario('outro')
        self.admin = criar_usuario('gestor', tipo='ADMIN')
        inicio = proximo_bloco(timedelta(hours=3))
        self.agendamento = Agendamento.objects.create(tipo_id=id_tipo('Desenv'), 
            usuario=self.dono, computador=self.pc,
            data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
        )

    def _url(self):
        return reverse('cancelar_agendamento', args=[self.agendamento.id])

    def test_dono_cancela_a_propria_reserva(self):
        self.client.force_login(self.dono)
        self.client.post(self._url())
        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.status, 'CANCELADO')
        self.assertEqual(self.agendamento.cancelado_por, self.dono)

    def test_admin_cancela_reserva_de_terceiro(self):
        self.client.force_login(self.admin)
        self.client.post(self._url(), {'origem': 'admin'})
        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.status, 'CANCELADO')

    def test_outro_usuario_nao_cancela(self):
        self.client.force_login(self.outro)
        self.client.post(self._url())
        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.status, 'CONFIRMADO')

    def test_get_nao_cancela(self):
        """Regressão de CSRF: a view aceitava GET, então bastava induzir a
        vítima a carregar a URL para cancelar a reserva dela."""
        self.client.force_login(self.dono)
        resposta = self.client.get(self._url())
        self.assertEqual(resposta.status_code, 405)
        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.status, 'CONFIRMADO')

    def test_reserva_encerrada_nao_pode_ser_cancelada(self):
        passado = timezone.now() - timedelta(days=2)
        Agendamento.objects.filter(pk=self.agendamento.pk).update(
            data_hora_inicio=passado, data_hora_fim=passado + timedelta(hours=1)
        )
        self.client.force_login(self.dono)
        self.client.post(self._url())
        self.agendamento.refresh_from_db()
        self.assertEqual(self.agendamento.status, 'CONFIRMADO')

    def test_horario_liberado_apos_cancelamento(self):
        self.client.force_login(self.dono)
        self.client.post(self._url())

        self.client.force_login(self.outro)
        inicio = timezone.localtime(self.agendamento.data_hora_inicio)
        resposta = self.client.post(reverse('criar_agendamento', args=[self.pc.id]), {
            'tipo': id_tipo('Estudo'),
            'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
            'data_hora_fim': (inicio + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Agendamento.objects.filter(status='CONFIRMADO').count(), 1)


class ControleDeAcessoTests(TestCase):
    def setUp(self):
        self.aluno = criar_usuario('aluno')
        self.tecnico = criar_usuario('tecnico', tipo='TECNICO')
        self.admin = criar_usuario('admin_lab', tipo='ADMIN')

    def test_aluno_nao_acessa_telas_de_gestao(self):
        self.client.force_login(self.aluno)
        for nome in ['listar_laboratorios', 'listar_computadores', 'listar_softwares',
                     'gerenciar_agendamentos', 'dashboard_financeiro', 'gerenciar_usuarios',
                     'permissoes_acesso', 'liberar_usuarios']:
            with self.subTest(view=nome):
                self.assertRedirects(self.client.get(reverse(nome)), reverse('home'))

    def test_tecnico_nao_acessa_telas_exclusivas_de_admin(self):
        self.client.force_login(self.tecnico)
        for nome in ['gerenciar_agendamentos', 'dashboard_financeiro', 'gerenciar_usuarios']:
            with self.subTest(view=nome):
                self.assertRedirects(self.client.get(reverse(nome)), reverse('home'))

    def test_tecnico_acessa_telas_de_ti(self):
        self.client.force_login(self.tecnico)
        for nome in ['listar_laboratorios', 'listar_computadores', 'listar_softwares']:
            with self.subTest(view=nome):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse('home'))
        self.assertIn(reverse('login'), resposta.url)


class ValidacaoDeEntradaTests(TestCase):
    def setUp(self):
        self.admin = criar_usuario('admin_lab', tipo='ADMIN')
        self.alvo = criar_usuario('alvo')
        self.solicitacao = SolicitacaoInstalacao.objects.create(
            usuario=self.alvo, software_nome='Docker', justificativa='Preciso para a disciplina X'
        )

    def test_status_de_solicitacao_invalido_e_recusado(self):
        """Regressão: o status vinha da URL e era gravado sem validação."""
        self.client.force_login(self.admin)
        self.client.post(
            reverse('atualizar_status_solicitacao', args=[self.solicitacao.id]),
            {'novo_status': 'QUALQUER_COISA'},
        )
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.status, 'PENDENTE')

    def test_status_valido_e_aplicado_e_registra_responsavel(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('atualizar_status_solicitacao', args=[self.solicitacao.id]),
            {'novo_status': 'CONCLUIDO'},
        )
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.status, 'CONCLUIDO')
        self.assertEqual(self.solicitacao.atendido_por, self.admin)

    def test_tipo_de_perfil_invalido_e_recusado(self):
        """Regressão: `novo_tipo` do POST ia direto para o banco."""
        self.client.force_login(self.admin)
        self.client.post(reverse('permissoes_acesso'), {
            'perfil_id': self.alvo.perfil.id,
            'novo_tipo': 'SUPER_HACKER',
        })
        self.alvo.perfil.refresh_from_db()
        self.assertEqual(self.alvo.perfil.tipo, 'ALUNO')

    def test_admin_nao_rebaixa_a_si_mesmo(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('permissoes_acesso'), {
            'perfil_id': self.admin.perfil.id,
            'novo_tipo': 'ALUNO',
        })
        self.admin.perfil.refresh_from_db()
        self.assertEqual(self.admin.perfil.tipo, 'ADMIN')

    def test_admin_nao_exclui_a_si_mesmo(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('deletar_usuario', args=[self.admin.id]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_exclusao_de_usuario_exige_post(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('deletar_usuario', args=[self.alvo.id]))
        self.assertEqual(resposta.status_code, 405)
        self.assertTrue(User.objects.filter(pk=self.alvo.pk).exists())

    def test_aprovacao_de_usuario_exige_post(self):
        self.client.force_login(self.admin)
        pendente = criar_usuario('pendente2', aprovado=False)
        self.assertEqual(
            self.client.get(reverse('aprovar_usuario', args=[pendente.perfil.id])).status_code, 405
        )
        pendente.perfil.refresh_from_db()
        self.assertFalse(pendente.perfil.aprovado)


class SolicitacaoInstalacaoTests(TestCase):
    def setUp(self):
        self.lab = Laboratorio.objects.create(nome='Lab 02')
        self.pc = Computador.objects.create(identificador='PC-09', laboratorio=self.lab)
        self.aluno = criar_usuario('aluno')
        self.client.force_login(self.aluno)

    def test_laboratorio_e_gravado(self):
        """Regressão: `laboratorio` ficava fora de `fields`, então toda
        solicitação era salva como "Qualquer máquina"."""
        self.client.post(reverse('criar_solicitacao_global'), {
            'laboratorio': self.lab.id,
            'software_nome': 'PostgreSQL 15',
            'justificativa': 'Disciplina de banco de dados',
        })
        solicitacao = SolicitacaoInstalacao.objects.get()
        self.assertEqual(solicitacao.laboratorio, self.lab)
        self.assertIn(self.lab.nome, solicitacao.destino_display())

    def test_solicitacao_por_maquina_herda_o_laboratorio(self):
        self.client.post(reverse('criar_solicitacao_instalacao', args=[self.pc.id]), {
            'software_nome': 'VS Code',
            'justificativa': 'Desenvolvimento das atividades',
        })
        solicitacao = SolicitacaoInstalacao.objects.get()
        self.assertEqual(solicitacao.computador, self.pc)
        self.assertEqual(solicitacao.laboratorio, self.lab)

    def test_justificativa_curta_e_rejeitada(self):
        form = SolicitacaoInstalacaoForm({'software_nome': 'Git', 'justificativa': 'preciso'})
        self.assertFalse(form.is_valid())
        self.assertIn('justificativa', form.errors)

    def test_aluno_so_enxerga_as_proprias_solicitacoes(self):
        outro = criar_usuario('outro')
        SolicitacaoInstalacao.objects.create(
            usuario=outro, software_nome='Secreto', justificativa='Justificativa do outro'
        )
        SolicitacaoInstalacao.objects.create(
            usuario=self.aluno, software_nome='Meu', justificativa='Justificativa minha'
        )
        conteudo = self.client.get(reverse('listar_solicitacoes')).content.decode()
        self.assertIn('Meu', conteudo)
        self.assertNotIn('Secreto', conteudo)


class IntegridadeDeDadosTests(TestCase):
    def test_identificador_de_maquina_e_unico_por_laboratorio(self):
        lab = Laboratorio.objects.create(nome='Lab 03')
        Computador.objects.create(identificador='PC-01', laboratorio=lab)
        with self.assertRaises(Exception):
            Computador.objects.create(identificador='PC-01', laboratorio=lab)

    def test_mesmo_identificador_permitido_em_laboratorios_distintos(self):
        lab_a = Laboratorio.objects.create(nome='Lab A')
        lab_b = Laboratorio.objects.create(nome='Lab B')
        Computador.objects.create(identificador='PC-01', laboratorio=lab_a)
        Computador.objects.create(identificador='PC-01', laboratorio=lab_b)
        self.assertEqual(Computador.objects.count(), 2)

    def test_software_duplicado_e_bloqueado(self):
        Software.objects.create(nome='Java', versao='17')
        with self.assertRaises(Exception):
            Software.objects.create(nome='Java', versao='17')


class ListagensTests(TestCase):
    def test_filtro_por_software_nao_duplica_maquinas(self):
        """Regressão: o join com `softwares` repetia a mesma máquina no grid."""
        lab = Laboratorio.objects.create(nome='Lab 04')
        pc = Computador.objects.create(identificador='PC-07', laboratorio=lab)
        java = Software.objects.create(nome='Java', versao='17')
        pc.softwares.add(java, Software.objects.create(nome='Git', versao='2.4'))

        admin = criar_usuario('admin_lab', tipo='ADMIN')
        self.client.force_login(admin)
        resposta = self.client.get(reverse('home'), {'software': java.id})
        self.assertEqual(len(resposta.context['computadores'].object_list), 1)

    def test_dashboard_financeiro_soma_apenas_reservas_confirmadas(self):
        lab = Laboratorio.objects.create(nome='Lab 05')
        pc = Computador.objects.create(identificador='PC-08', laboratorio=lab)
        aluno = criar_usuario('aluno')
        inicio = timezone.now() + timedelta(hours=2)

        Agendamento.objects.create(tipo_id=id_tipo('Desenv'), 
            usuario=aluno, computador=pc, data_hora_inicio=inicio,
            data_hora_fim=inicio + timedelta(hours=1), valor_total=Decimal('10.00'),
        )
        Agendamento.objects.create(tipo_id=id_tipo('Desenv'), 
            usuario=aluno, computador=pc, data_hora_inicio=inicio + timedelta(hours=5),
            data_hora_fim=inicio + timedelta(hours=6), valor_total=Decimal('99.00'),
            status='CANCELADO',
        )

        admin = criar_usuario('admin_lab', tipo='ADMIN')
        self.client.force_login(admin)
        resposta = self.client.get(reverse('dashboard_financeiro'))
        self.assertEqual(resposta.context['total_geral'], Decimal('10.00'))


class AlterarSenhaTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario('joao')
        self.client.force_login(self.usuario)

    def test_troca_a_propria_senha_com_senha_atual_correta(self):
        resposta = self.client.post(reverse('alterar_senha'), {
            'old_password': 'senha-de-teste-123',
            'new_password1': 'nova-senha-forte-456',
            'new_password2': 'nova-senha-forte-456',
        })
        self.assertRedirects(resposta, reverse('home'))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('nova-senha-forte-456'))

    def test_sessao_continua_valida_apos_trocar_a_propria_senha(self):
        """Regressão: sem update_session_auth_hash, trocar a própria senha
        derruba a sessão atual (o usuário é deslogado no meio do fluxo)."""
        self.client.post(reverse('alterar_senha'), {
            'old_password': 'senha-de-teste-123',
            'new_password1': 'nova-senha-forte-456',
            'new_password2': 'nova-senha-forte-456',
        })
        resposta = self.client.get(reverse('home'))
        self.assertEqual(resposta.status_code, 200)

    def test_senha_atual_incorreta_e_rejeitada(self):
        resposta = self.client.post(reverse('alterar_senha'), {
            'old_password': 'senha-errada',
            'new_password1': 'nova-senha-forte-456',
            'new_password2': 'nova-senha-forte-456',
        })
        self.assertEqual(resposta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('senha-de-teste-123'))

    def test_confirmacao_divergente_e_rejeitada(self):
        self.client.post(reverse('alterar_senha'), {
            'old_password': 'senha-de-teste-123',
            'new_password1': 'nova-senha-forte-456',
            'new_password2': 'outra-coisa-789',
        })
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('senha-de-teste-123'))

    def test_senha_fraca_e_rejeitada_pelos_validadores(self):
        self.client.post(reverse('alterar_senha'), {
            'old_password': 'senha-de-teste-123',
            'new_password1': '12345678',
            'new_password2': '12345678',
        })
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('senha-de-teste-123'))


class ResetarSenhaUsuarioTests(TestCase):
    def setUp(self):
        self.admin = criar_usuario('admin_lab', tipo='ADMIN')
        self.esquecido = criar_usuario('esquecido')

    def _url(self, user):
        return reverse('resetar_senha_usuario', args=[user.id])

    def test_admin_redefine_senha_de_outro_usuario_sem_senha_atual(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(self._url(self.esquecido), {
            'new_password1': 'senha-recuperada-999',
            'new_password2': 'senha-recuperada-999',
        })
        self.assertRedirects(resposta, reverse('editar_usuario', args=[self.esquecido.id]))
        self.esquecido.refresh_from_db()
        self.assertTrue(self.esquecido.check_password('senha-recuperada-999'))

    def test_sessao_antiga_do_usuario_afetado_e_invalidada(self):
        """A pessoa cuja senha foi redefinida precisa logar de novo."""
        self.client.force_login(self.esquecido)
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

        outro_client = self.client_class()
        outro_client.force_login(self.admin)
        outro_client.post(self._url(self.esquecido), {
            'new_password1': 'senha-recuperada-999',
            'new_password2': 'senha-recuperada-999',
        })

        resposta = self.client.get(reverse('home'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse('login'), resposta.url)

    def test_aluno_nao_pode_resetar_senha_de_terceiros(self):
        aluno = criar_usuario('outro_aluno')
        self.client.force_login(aluno)
        resposta = self.client.post(self._url(self.esquecido), {
            'new_password1': 'senha-recuperada-999',
            'new_password2': 'senha-recuperada-999',
        })
        self.assertRedirects(resposta, reverse('home'))
        self.esquecido.refresh_from_db()
        self.assertTrue(self.esquecido.check_password('senha-de-teste-123'))

    def test_admin_comum_nao_reseta_senha_de_superusuario(self):
        root = User.objects.create_superuser(username='root', password='x', email='r@e.com')
        self.client.force_login(self.admin)
        resposta = self.client.post(self._url(root), {
            'new_password1': 'senha-recuperada-999',
            'new_password2': 'senha-recuperada-999',
        })
        self.assertRedirects(resposta, reverse('gerenciar_usuarios'))
        self.assertFalse(root.check_password('senha-recuperada-999'))

    def test_senha_fraca_e_rejeitada(self):
        self.client.force_login(self.admin)
        self.client.post(self._url(self.esquecido), {
            'new_password1': '12345678',
            'new_password2': '12345678',
        })
        self.esquecido.refresh_from_db()
        self.assertTrue(self.esquecido.check_password('senha-de-teste-123'))


class AcessoDeContaRevogadaTests(TestCase):
    """Etapa 1: admin/técnico com acesso revogado não pode manter privilégios."""

    def setUp(self):
        self.client.defaults['wsgi.url_scheme'] = 'https'
        self.admin_revogado = criar_usuario('adm_revogado', tipo='ADMIN', aprovado=False)
        self.tecnico_revogado = criar_usuario('tec_revogado', tipo='TECNICO', aprovado=False)
        self.admin = criar_usuario('adm', tipo='ADMIN')
        self.root = User.objects.create_superuser('root', 'root@example.com', 'senha-de-teste-123')

    def test_admin_revogado_nao_acessa_gestao(self):
        self.client.force_login(self.admin_revogado)
        for nome in ('gerenciar_agendamentos', 'dashboard_financeiro', 'liberar_usuarios', 'gerenciar_usuarios'):
            resp = self.client.get(reverse(nome), secure=True)
            self.assertEqual(resp.status_code, 302, nome)

    def test_tecnico_revogado_nao_acessa_telas_de_ti(self):
        self.client.force_login(self.tecnico_revogado)
        resp = self.client.get(reverse('listar_laboratorios'), secure=True)
        self.assertEqual(resp.status_code, 302)

    def test_conta_revogada_nao_cancela_agendamento(self):
        lab = Laboratorio.objects.create(nome='L')
        pc = Computador.objects.create(identificador='PC', laboratorio=lab)
        agora = timezone.now()
        ag = Agendamento.objects.create(tipo_id=id_tipo('Desenv'), 
            usuario=self.admin_revogado, computador=pc,
            data_hora_inicio=agora + timedelta(hours=1), data_hora_fim=agora + timedelta(hours=2),
        )
        self.client.force_login(self.admin_revogado)
        resp = self.client.post(reverse('cancelar_agendamento', args=[ag.id]), secure=True)
        self.assertEqual(resp.status_code, 403)
        ag.refresh_from_db()
        self.assertEqual(ag.status, 'CONFIRMADO')

    def test_admin_comum_nao_edita_superusuario(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('editar_usuario', args=[self.root.id]),
            {'username': 'root', 'email': 'hack@example.com', 'tipo': 'ALUNO', 'aprovado': ''},
            secure=True,
        )
        self.assertEqual(resp.status_code, 302)
        self.root.refresh_from_db()
        self.assertEqual(self.root.email, 'root@example.com')

    def test_admin_comum_nao_revoga_outro_admin(self):
        outro = criar_usuario('outro_adm', tipo='ADMIN')
        self.client.force_login(self.admin)
        self.client.post(reverse('revogar_usuario', args=[outro.perfil.id]), secure=True)
        outro.perfil.refresh_from_db()
        self.assertTrue(outro.perfil.aprovado)

    def test_superusuario_revoga_admin(self):
        outro = criar_usuario('outro_adm2', tipo='ADMIN')
        self.client.force_login(self.root)
        self.client.post(reverse('revogar_usuario', args=[outro.perfil.id]), secure=True)
        outro.perfil.refresh_from_db()
        self.assertFalse(outro.perfil.aprovado)


class IntegridadeFinanceiraTests(TestCase):
    """Etapa 2: histórico financeiro não pode ser apagado em cascata."""

    def setUp(self):
        self.admin = criar_usuario('adm2', tipo='ADMIN')
        self.aluno = criar_usuario('aluno2')
        self.lab = Laboratorio.objects.create(nome='Lab P', capacidade=1)
        self.pc = Computador.objects.create(identificador='PC1', laboratorio=self.lab)
        agora = timezone.now()
        self.ag = Agendamento.objects.create(tipo_id=id_tipo('Desenv'), 
            usuario=self.aluno, computador=self.pc,
            data_hora_inicio=agora + timedelta(hours=1), data_hora_fim=agora + timedelta(hours=2),
            valor_total=Decimal('10.00'),
        )
        self.client.force_login(self.admin)

    def test_nao_exclui_usuario_com_reservas(self):
        self.client.post(reverse('deletar_usuario', args=[self.aluno.id]), secure=True)
        self.assertTrue(User.objects.filter(pk=self.aluno.pk).exists())
        self.assertTrue(Agendamento.objects.filter(pk=self.ag.pk).exists())

    def test_nao_exclui_computador_com_reservas(self):
        self.client.post(reverse('excluir_computador', args=[self.pc.id]), secure=True)
        self.assertTrue(Computador.objects.filter(pk=self.pc.pk).exists())

    def test_exclui_computador_sem_reservas(self):
        livre = Computador.objects.create(identificador='PC2', laboratorio=Laboratorio.objects.create(nome='Lab Q'))
        self.client.post(reverse('excluir_computador', args=[livre.id]), secure=True)
        self.assertFalse(Computador.objects.filter(pk=livre.pk).exists())

    def test_excluir_computador_exige_admin(self):
        tec = criar_usuario('tec2', tipo='TECNICO')
        self.client.force_login(tec)
        self.client.post(reverse('excluir_computador', args=[self.pc.id]), secure=True)
        self.assertTrue(Computador.objects.filter(pk=self.pc.pk).exists())

    def test_laboratorio_com_maquina_protegido_no_banco(self):
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            self.lab.delete()

    def test_reserva_grava_tarifa_aplicada(self):
        TipoAgendamento.objects.filter(nome__istartswith='Estudo').update(valor_hora=Decimal('10.00'), modo='FIXO')
        self.client.force_login(self.aluno)
        inicio = proximo_bloco(timedelta(days=1))
        self.client.post(reverse('criar_agendamento', args=[self.pc.id]), {
            'tipo': id_tipo('Estudo'),
            'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
            'data_hora_fim': (inicio + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        }, secure=True)
        novo = Agendamento.objects.exclude(pk=self.ag.pk).get()
        self.assertEqual(novo.valor_hora_aplicado, Decimal('10.00'))
        TipoAgendamento.objects.filter(nome__istartswith='Desenv').update(valor_hora=Decimal('99.00'))
        novo.refresh_from_db()
        self.assertEqual(novo.valor_hora_aplicado, Decimal('10.00'))

    def test_capacidade_do_laboratorio_limita_maquinas(self):
        from .forms import ComputadorForm
        form = ComputadorForm({'identificador': 'PC9', 'laboratorio': self.lab.id,
                               'status': 'DISPONIVEL'})
        self.assertFalse(form.is_valid())
        self.assertIn('laboratorio', form.errors)
        # editar a máquina já existente continua permitido
        form = ComputadorForm({'identificador': 'PC1', 'laboratorio': self.lab.id,
                               'status': 'DISPONIVEL'}, instance=self.pc)
        self.assertTrue(form.is_valid(), form.errors)


class RegrasDeAgendamentoTests(TestCase):
    """Etapa 3: regras de duração, blocos, conflitos por usuário, limite e manutenção."""

    def setUp(self):
        self.lab = Laboratorio.objects.create(nome='Lab R')
        self.pc1 = Computador.objects.create(identificador='R1', laboratorio=self.lab)
        self.pc2 = Computador.objects.create(identificador='R2', laboratorio=self.lab)
        self.aluno = criar_usuario('aluno_r', email='aluno_r@example.com')
        self.tec = criar_usuario('tec_r', tipo='TECNICO')
        self.client.force_login(self.aluno)

    def _post(self, pc, inicio, minutos=60):
        return self.client.post(reverse('criar_agendamento', args=[pc.id]), {
            'tipo': id_tipo('Estudo'),
            'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
            'data_hora_fim': (inicio + timedelta(minutes=minutos)).strftime('%Y-%m-%d %H:%M'),
        })

    def test_rejeita_horario_fora_do_bloco(self):
        inicio = proximo_bloco(timedelta(hours=3)) + timedelta(minutes=10)
        self._post(self.pc1, inicio)
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_rejeita_duracao_minima(self):
        self._post(self.pc1, proximo_bloco(), minutos=0)
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_aceita_bloco_de_30_min(self):
        TipoAgendamento.objects.filter(nome__istartswith='Estudo').update(valor_hora=Decimal('4.00'), modo='FIXO')
        self._post(self.pc1, proximo_bloco(), minutos=30)
        self.assertEqual(Agendamento.objects.get().valor_total, Decimal('2.00'))

    def test_usuario_nao_reserva_duas_maquinas_no_mesmo_horario(self):
        inicio = proximo_bloco()
        self._post(self.pc1, inicio)
        self._post(self.pc2, inicio)
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_limite_de_reservas_ativas(self):
        with self.settings(AGENDAMENTO_MAX_RESERVAS_ATIVAS=2):
            base = proximo_bloco(timedelta(hours=3))
            for i in range(3):
                self._post(self.pc1, base + timedelta(hours=2 * i), minutos=60)
        self.assertEqual(Agendamento.objects.count(), 2)

    def test_horario_de_funcionamento(self):
        with self.settings(AGENDAMENTO_HORA_ABERTURA=7, AGENDAMENTO_HORA_FECHAMENTO=22):
            noite = proximo_bloco(timedelta(days=1)).replace(hour=23, minute=0)
            self._post(self.pc1, noite)
            self.assertEqual(Agendamento.objects.count(), 0)
            dia = noite.replace(hour=10)
            self._post(self.pc1, dia)
            self.assertEqual(Agendamento.objects.count(), 1)

    def test_manutencao_cancela_reservas_futuras_e_avisa(self):
        from django.core import mail
        self._post(self.pc1, proximo_bloco(timedelta(hours=3)))
        ag = Agendamento.objects.get()
        self.client.force_login(self.tec)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(reverse('editar_computador', args=[self.pc1.id]), {
                'identificador': 'R1', 'laboratorio': self.lab.id,
                'status': 'MANUTENCAO',
            })
        self.assertEqual(resp.status_code, 302)
        ag.refresh_from_db()
        self.assertEqual(ag.status, 'CANCELADO')
        self.assertEqual(ag.cancelado_por_id, self.tec.id)
        self.assertTrue(any('cancelada' in m.subject.lower() for m in mail.outbox))

    def test_confirmacao_envia_email(self):
        from django.core import mail
        with self.captureOnCommitCallbacks(execute=True):
            self._post(self.pc1, proximo_bloco(timedelta(hours=3)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['aluno_r@example.com'])

    def test_usuario_sem_email_nao_quebra(self):
        sem = criar_usuario('sem_email')
        self.client.force_login(sem)
        with self.captureOnCommitCallbacks(execute=True):
            self._post(self.pc1, proximo_bloco(timedelta(hours=3)))
        self.assertEqual(Agendamento.objects.count(), 1)


class FluxoSolicitacaoTests(TestCase):
    """Etapa 4: transições válidas, histórico e inventário."""

    def setUp(self):
        self.tec = criar_usuario('tec_s', tipo='TECNICO')
        self.aluno = criar_usuario('aluno_s')
        self.lab = Laboratorio.objects.create(nome='Lab S')
        self.pc = Computador.objects.create(identificador='S1', laboratorio=self.lab)
        self.sw = Software.objects.create(nome='Docker', versao='24')
        self.sol = SolicitacaoInstalacao.objects.create(
            usuario=self.aluno, computador=self.pc, laboratorio=self.lab,
            software_nome='Docker 24', justificativa='Preciso para a disciplina X',
        )

    def _status(self, novo):
        self.client.force_login(self.tec)
        self.client.post(reverse('atualizar_status_solicitacao', args=[self.sol.id]), {'novo_status': novo})
        self.sol.refresh_from_db()

    def test_concluir_adiciona_software_ao_inventario(self):
        self._status('CONCLUIDO')
        self.assertEqual(self.sol.status, 'CONCLUIDO')
        self.assertIn(self.sw, self.pc.softwares.all())

    def test_concluir_software_desconhecido_nao_quebra(self):
        self.sol.software_nome = 'Programa Inexistente'
        self.sol.save()
        self._status('CONCLUIDO')
        self.assertEqual(self.sol.status, 'CONCLUIDO')
        self.assertEqual(self.pc.softwares.count(), 0)

    def test_estado_final_nao_volta(self):
        self._status('CONCLUIDO')
        self._status('PENDENTE')
        self.assertEqual(self.sol.status, 'CONCLUIDO')

    def test_tecnico_nao_marca_como_cancelado(self):
        self._status('CANCELADO')
        self.assertEqual(self.sol.status, 'PENDENTE')

    def test_retirar_mantem_historico(self):
        self.client.force_login(self.aluno)
        self.client.post(reverse('cancelar_solicitacao', args=[self.sol.id]))
        self.sol.refresh_from_db()
        self.assertEqual(self.sol.status, 'CANCELADO')

    def test_nao_retira_solicitacao_em_andamento(self):
        self._status('EM_ANDAMENTO')
        self.client.force_login(self.aluno)
        self.client.post(reverse('cancelar_solicitacao', args=[self.sol.id]))
        self.sol.refresh_from_db()
        self.assertEqual(self.sol.status, 'EM_ANDAMENTO')

    def test_maquina_inativa_nao_recebe_solicitacao(self):
        self.pc.status = 'INATIVO'
        self.pc.save()
        self.client.force_login(self.aluno)
        self.client.post(reverse('criar_solicitacao_instalacao', args=[self.pc.id]), {
            'software_nome': 'Git', 'justificativa': 'Controle de versão das aulas',
        })
        self.assertEqual(SolicitacaoInstalacao.objects.count(), 1)


class DashboardFinanceiroTests(TestCase):
    """Etapa 5: realizada × prevista, período, cancelamento e horas."""

    def setUp(self):
        self.admin = criar_usuario('adm_dash', tipo='ADMIN')
        self.aluno = criar_usuario('aluno_dash')
        self.lab = Laboratorio.objects.create(nome='Lab D')
        self.pc = Computador.objects.create(identificador='D1', laboratorio=self.lab)
        agora = timezone.now()
        mk = lambda ini, h, valor, status='CONFIRMADO': Agendamento.objects.create(tipo_id=id_tipo('Desenv'), 
            usuario=self.aluno, computador=self.pc, data_hora_inicio=ini,
            data_hora_fim=ini + timedelta(hours=h), valor_total=Decimal(valor), status=status,
        )
        self.passada = mk(agora - timedelta(days=40), 2, '20.00')       # realizada (2h)
        self.futura = mk(agora + timedelta(days=1), 1, '10.00')          # prevista (1h)
        self.cancelada = mk(agora + timedelta(days=2), 1, '10.00', 'CANCELADO')
        self.client.force_login(self.admin)

    def _ctx(self, **params):
        return self.client.get(reverse('dashboard_financeiro'), params).context

    def test_separa_realizada_e_prevista(self):
        ctx = self._ctx()
        self.assertEqual(ctx['receita_realizada'], Decimal('20.00'))
        self.assertEqual(ctx['receita_prevista'], Decimal('10.00'))
        self.assertEqual(ctx['total_geral'], Decimal('30.00'))
        self.assertEqual(ctx['valor_cancelado'], Decimal('10.00'))

    def test_horas_e_taxa_de_cancelamento(self):
        ctx = self._ctx()
        self.assertEqual(ctx['horas_reservadas'], 3.0)
        self.assertEqual(ctx['total_reservas'], 2)
        self.assertAlmostEqual(ctx['taxa_cancelamento'], 33.3, places=1)
        self.assertEqual(ctx['ticket_medio'], Decimal('15.00'))

    def test_filtro_de_periodo(self):
        hoje = timezone.localdate()
        ctx = self._ctx(de=hoje.isoformat())
        self.assertEqual(ctx['receita_realizada'], Decimal('0.00'))
        self.assertEqual(ctx['receita_prevista'], Decimal('10.00'))

    def test_data_invalida_e_ignorada(self):
        ctx = self._ctx(de='lixo', ate='99-99-99')
        self.assertEqual(ctx['total_geral'], Decimal('30.00'))

    def test_filtro_por_laboratorio(self):
        outro = Laboratorio.objects.create(nome='Lab E')
        ctx = self._ctx(laboratorio=outro.id)
        self.assertEqual(ctx['total_geral'], Decimal('0.00'))

    def test_pagina_renderiza(self):
        resp = self.client.get(reverse('dashboard_financeiro'))
        self.assertContains(resp, 'Receita realizada')

    def test_meus_agendamentos_separa_usado_e_previsto(self):
        self.client.force_login(self.aluno)
        ctx = self.client.get(reverse('meus_agendamentos')).context
        self.assertEqual(ctx['total_gasto'], Decimal('20.00'))
        self.assertEqual(ctx['total_previsto'], Decimal('10.00'))


class TipoAgendamentoPrecoTests(TestCase):
    """Preço configurável por tipo de agendamento."""

    def setUp(self):
        self.admin = criar_usuario('adm_tipo', tipo='ADMIN')
        self.aluno = criar_usuario('aluno_tipo')
        self.lab = Laboratorio.objects.create(nome='Lab T')
        self.pc = Computador.objects.create(identificador='T1', laboratorio=self.lab)

    def _reservar(self, tipo, minutos=60):
        self.client.force_login(self.aluno)
        inicio = proximo_bloco(timedelta(hours=3))
        return self.client.post(reverse('criar_agendamento', args=[self.pc.id]), {
            'tipo': tipo.id,
            'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
            'data_hora_fim': (inicio + timedelta(minutes=minutos)).strftime('%Y-%m-%d %H:%M'),
        })

    def test_migracao_criou_tipos_padrao(self):
        self.assertGreaterEqual(TipoAgendamento.objects.count(), 4)

    def test_modo_fixo_calcula_pela_duracao(self):
        t = TipoAgendamento.objects.create(nome='Evento', modo='FIXO', valor_hora=Decimal('30.00'))
        self._reservar(t, 60)
        self.assertEqual(Agendamento.objects.get().valor_total, Decimal('30.00'))

    def test_modo_gratuito(self):
        t = TipoAgendamento.objects.create(nome='Aula', modo='GRATUITO')
        self._reservar(t, 60)
        self.assertEqual(Agendamento.objects.get().valor_total, Decimal('0.00'))

    def test_tipo_inativo_nao_pode_ser_usado(self):
        t = TipoAgendamento.objects.create(nome='Antigo', modo='GRATUITO', ativo=False)
        self._reservar(t)
        self.assertEqual(Agendamento.objects.count(), 0)

    def test_duracao_maxima_por_tipo(self):
        t = TipoAgendamento.objects.create(nome='Longo', modo='GRATUITO', duracao_maxima_min=240)
        self._reservar(t, 240)
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_mudar_preco_nao_altera_reservas_existentes(self):
        t = TipoAgendamento.objects.create(nome='Var', modo='FIXO', valor_hora=Decimal('8.00'))
        self._reservar(t, 60)
        t.valor_hora = Decimal('99.00')
        t.save()
        self.assertEqual(Agendamento.objects.get().valor_total, Decimal('8.00'))

    def test_admin_cria_tipo_pela_tela(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('cadastrar_tipo_agendamento'), {
            'nome': 'Comunidade', 'modo': 'FIXO', 'valor_hora': '12.00',
            'ordem': '5', 'ativo': 'on',
        })
        self.assertEqual(TipoAgendamento.objects.get(nome='Comunidade').valor_hora, Decimal('12.00'))

    def test_modo_fixo_exige_valor(self):
        from .forms import TipoAgendamentoForm
        form = TipoAgendamentoForm({'nome': 'X', 'modo': 'FIXO', 'ordem': 0, 'ativo': True})
        self.assertFalse(form.is_valid())
        self.assertIn('valor_hora', form.errors)

    def test_aluno_nao_acessa_tela_de_tipos(self):
        self.client.force_login(self.aluno)
        resp = self.client.get(reverse('listar_tipos_agendamento'))
        self.assertEqual(resp.status_code, 302)

    def test_tipo_usado_nao_e_excluido(self):
        t = TipoAgendamento.objects.create(nome='Usado', modo='GRATUITO')
        self._reservar(t)
        self.client.force_login(self.admin)
        self.client.post(reverse('excluir_tipo_agendamento', args=[t.id]))
        self.assertTrue(TipoAgendamento.objects.filter(pk=t.pk).exists())

    def test_tela_de_agendar_renderiza_com_taxas(self):
        self.client.force_login(self.aluno)
        resp = self.client.get(reverse('criar_agendamento', args=[self.pc.id]))
        self.assertContains(resp, 'taxas-data')
