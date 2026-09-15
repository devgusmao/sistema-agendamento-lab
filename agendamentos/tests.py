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
from .models import Agendamento, Computador, Laboratorio, Perfil, Software, SolicitacaoInstalacao


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
        inicio = timezone.localtime(timezone.now() + timedelta(hours=2))
        dados = {
            'finalidade': 'ESTUDO',
            'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
            'data_hora_fim': (inicio + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        }
        dados.update(over)
        return dados

    def test_form_valido_com_finalidade(self):
        self.assertTrue(AgendamentoForm(self._dados()).is_valid())

    def test_finalidade_ausente_invalida_o_form(self):
        """Regressão: o template não renderizava `finalidade`, então nenhuma
        reserva podia ser criada. O campo continua obrigatório de propósito."""
        dados = self._dados()
        del dados['finalidade']
        form = AgendamentoForm(dados)
        self.assertFalse(form.is_valid())
        self.assertIn('finalidade', form.errors)

    def test_rejeita_duracao_acima_de_duas_horas(self):
        inicio = timezone.localtime(timezone.now() + timedelta(hours=2))
        form = AgendamentoForm(self._dados(
            data_hora_fim=(inicio + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')
        ))
        self.assertFalse(form.is_valid())

    def test_rejeita_inicio_no_passado(self):
        passado = timezone.localtime(timezone.now() - timedelta(hours=3))
        form = AgendamentoForm(self._dados(
            data_hora_inicio=passado.strftime('%Y-%m-%d %H:%M'),
            data_hora_fim=(passado + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        ))
        self.assertFalse(form.is_valid())

    def test_rejeita_antecedencia_maior_que_30_dias(self):
        distante = timezone.localtime(timezone.now() + timedelta(days=45))
        form = AgendamentoForm(self._dados(
            data_hora_inicio=distante.strftime('%Y-%m-%d %H:%M'),
            data_hora_fim=(distante + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
        ))
        self.assertFalse(form.is_valid())


class CriarAgendamentoViewTests(TestCase):
    def setUp(self):
        self.lab = Laboratorio.objects.create(nome='Lab 01', capacidade=10)
        self.pc = Computador.objects.create(
            identificador='PC-01', laboratorio=self.lab, valor_hora=Decimal('5.00')
        )
        self.aluno = criar_usuario('aluno')
        self.client.force_login(self.aluno)

    def _payload(self, horas=2, offset=1):
        inicio = timezone.localtime(timezone.now() + timedelta(hours=offset))
        return {
            'finalidade': 'PROGRAMACAO',
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
        inicio = timezone.now() + timedelta(hours=3)
        self.agendamento = Agendamento.objects.create(
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
            'finalidade': 'ESTUDO',
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
        pc = Computador.objects.create(identificador='PC-08', laboratorio=lab, valor_hora=Decimal('10.00'))
        aluno = criar_usuario('aluno')
        inicio = timezone.now() + timedelta(hours=2)

        Agendamento.objects.create(
            usuario=aluno, computador=pc, data_hora_inicio=inicio,
            data_hora_fim=inicio + timedelta(hours=1), valor_total=Decimal('10.00'),
        )
        Agendamento.objects.create(
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
