"""Testes de multa, pagamento/estorno, dashboard financeiro e da camada de serviços."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Agendamento, Computador, Laboratorio, SolicitacaoInstalacao, Software, TipoAgendamento
from .servicos import financeiro, pagamentos, reservas, solicitacoes
from .servicos.precos import calcular_multa
from .tests import criar_usuario, id_tipo, proximo_bloco
from . import usuarios


class CalcularMultaTests(TestCase):
    """Regra pura: só o dono, em reserva paga, dentro da janela de antecedência."""

    def setUp(self):
        self.agora = timezone.now()

    def _multa(self, horas_ate_inicio, valor='40.00', dono=True):
        return calcular_multa(
            valor_total=Decimal(valor), inicio=self.agora + timedelta(hours=horas_ate_inicio),
            dono_cancela=dono, agora=self.agora,
        )

    def test_sem_multa_com_antecedencia_suficiente(self):
        self.assertEqual(self._multa(48), Decimal('0.00'))

    def test_sem_multa_exatamente_no_limite(self):
        self.assertEqual(self._multa(24), Decimal('0.00'))

    def test_multa_de_50_por_cento_dentro_da_janela(self):
        self.assertEqual(self._multa(23), Decimal('20.00'))

    def test_multa_com_reserva_ja_iniciada(self):
        self.assertEqual(self._multa(-0.5), Decimal('20.00'))

    def test_admin_ou_terceiro_cancelando_nao_gera_multa(self):
        self.assertEqual(self._multa(1, dono=False), Decimal('0.00'))

    def test_reserva_gratuita_nao_gera_multa(self):
        self.assertEqual(self._multa(1, valor='0.00'), Decimal('0.00'))

    def test_arredonda_para_centavos(self):
        self.assertEqual(self._multa(1, valor='33.33'), Decimal('16.67'))

    @override_settings(AGENDAMENTO_MULTA_HORAS=2, AGENDAMENTO_MULTA_PERCENTUAL=100)
    def test_horas_e_percentual_sao_configuraveis(self):
        self.assertEqual(self._multa(3), Decimal('0.00'))
        self.assertEqual(self._multa(1), Decimal('40.00'))


class BaseFinanceira(TestCase):
    def setUp(self):
        self.admin = criar_usuario('adm_fin', tipo='ADMIN')
        self.aluno = criar_usuario('aluno_fin')
        self.lab = Laboratorio.objects.create(nome='Lab F')
        self.pc = Computador.objects.create(identificador='F1', laboratorio=self.lab)

    def reserva(self, horas_ate_inicio, valor='10.00', usuario=None, **extra):
        inicio = timezone.now() + timedelta(hours=horas_ate_inicio)
        return Agendamento.objects.create(
            tipo_id=id_tipo('Desenv'), usuario=usuario or self.aluno, computador=self.pc,
            data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
            valor_total=Decimal(valor), **extra,
        )

    def cancelar_pela_view(self, ag, usuario, **dados):
        self.client.force_login(usuario)
        return self.client.post(reverse('cancelar_agendamento', args=[ag.id]), dados)


class CancelamentoComMultaTests(BaseFinanceira):
    def test_dono_cancela_dentro_do_prazo_paga_multa(self):
        ag = self.reserva(3, '10.00')
        resp = self.cancelar_pela_view(ag, self.aluno)
        ag.refresh_from_db()
        self.assertEqual(ag.status, 'CANCELADO')
        self.assertEqual(ag.multa, Decimal('5.00'))
        self.assertEqual(ag.status_pagamento, 'PENDENTE')  # a multa ainda precisa ser paga
        self.assertEqual(ag.valor_devido, Decimal('5.00'))
        self.assertContains(self.client.get(resp.url), 'Multa por cancelamento', status_code=200)

    def test_dono_cancela_com_antecedencia_nao_paga(self):
        ag = self.reserva(48, '10.00')
        self.cancelar_pela_view(ag, self.aluno)
        ag.refresh_from_db()
        self.assertEqual(ag.multa, Decimal('0.00'))
        self.assertEqual(ag.status_pagamento, 'ISENTO')
        self.assertEqual(ag.valor_devido, Decimal('0.00'))

    def test_admin_cancelando_reserva_de_aluno_nao_gera_multa(self):
        ag = self.reserva(1, '10.00')
        self.cancelar_pela_view(ag, self.admin, origem='admin')
        ag.refresh_from_db()
        self.assertEqual(ag.multa, Decimal('0.00'))
        self.assertEqual(ag.status_pagamento, 'ISENTO')

    def test_reserva_gratuita_cancelada_nao_gera_multa(self):
        ag = self.reserva(1, '0.00', status_pagamento='ISENTO')
        self.cancelar_pela_view(ag, self.aluno)
        ag.refresh_from_db()
        self.assertEqual(ag.multa, Decimal('0.00'))

    def test_manutencao_da_maquina_cancela_sem_multa(self):
        ag = self.reserva(1, '10.00')
        reservas.cancelar_futuras_da_maquina(self.pc, self.admin)
        ag.refresh_from_db()
        self.assertEqual((ag.status, ag.multa, ag.status_pagamento), ('CANCELADO', Decimal('0.00'), 'ISENTO'))

    def test_tela_avisa_da_multa_antes_de_cancelar(self):
        self.reserva(3, '10.00')
        self.client.force_login(self.aluno)
        resp = self.client.get(reverse('meus_agendamentos'))
        self.assertContains(resp, 'Multa de R$ 5,00 se cancelar agora')

    def test_tela_nao_avisa_quando_ainda_ha_prazo(self):
        self.reserva(72, '10.00')
        self.client.force_login(self.aluno)
        resp = self.client.get(reverse('meus_agendamentos'))
        self.assertNotContains(resp, 'se cancelar agora')

    def test_cancelar_com_objeto_desatualizado_preserva_o_pagamento(self):
        ag = self.reserva(72, '10.00')
        copia_antiga = Agendamento.objects.get(pk=ag.pk)   # lida antes do pagamento
        pagamentos.registrar_pagamento(ag, self.admin)
        reservas.cancelar(copia_antiga, self.aluno)
        ag.refresh_from_db()
        self.assertEqual((ag.status_pagamento, ag.valor_pago), ('PAGO', Decimal('10.00')))
        self.assertEqual(ag.estorno_pendente, Decimal('10.00'))

    def test_servico_recusa_terceiro_e_cancelamento_repetido(self):
        ag = self.reserva(3)
        outro = criar_usuario('intruso')
        with self.assertRaises(reservas.CancelamentoRecusado) as ctx:
            reservas.cancelar(ag, outro)
        self.assertTrue(ctx.exception.sem_permissao)
        reservas.cancelar(ag, self.aluno)
        with self.assertRaises(reservas.CancelamentoRecusado):
            reservas.cancelar(ag, self.aluno)


class ReservaGratuitaTests(BaseFinanceira):
    def test_reserva_gratuita_nasce_isenta(self):
        livre = TipoAgendamento.objects.create(nome='Livre', modo='GRATUITO')
        inicio = proximo_bloco(timedelta(days=2))
        ag = reservas.reservar(self.aluno, self.pc, livre, inicio, inicio + timedelta(hours=1))
        self.assertEqual((ag.valor_total, ag.status_pagamento), (Decimal('0.00'), 'ISENTO'))

    def test_reserva_paga_nasce_pendente(self):
        tipo = TipoAgendamento.objects.create(nome='Pago', modo='FIXO', valor_hora=Decimal('8.00'))
        inicio = proximo_bloco(timedelta(days=2))
        ag = reservas.reservar(self.aluno, self.pc, tipo, inicio, inicio + timedelta(hours=1))
        self.assertEqual((ag.valor_total, ag.status_pagamento), (Decimal('8.00'), 'PENDENTE'))


class PagamentoTests(BaseFinanceira):
    def test_admin_registra_pagamento(self):
        ag = self.reserva(48, '10.00')
        self.client.force_login(self.admin)
        self.client.post(reverse('registrar_pagamento', args=[ag.id]))
        ag.refresh_from_db()
        self.assertEqual(ag.status_pagamento, 'PAGO')
        self.assertEqual(ag.valor_pago, Decimal('10.00'))
        self.assertEqual(ag.pagamento_registrado_por, self.admin)
        self.assertIsNotNone(ag.pago_em)

    def test_aluno_nao_registra_pagamento(self):
        ag = self.reserva(48, '10.00')
        self.client.force_login(self.aluno)
        self.client.post(reverse('registrar_pagamento', args=[ag.id]))
        ag.refresh_from_db()
        self.assertEqual(ag.status_pagamento, 'PENDENTE')

    def test_pagamento_exige_post(self):
        ag = self.reserva(48)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('registrar_pagamento', args=[ag.id])).status_code, 405)

    def test_nao_paga_duas_vezes_nem_o_que_e_isento(self):
        ag = self.reserva(48, '10.00')
        pagamentos.registrar_pagamento(ag, self.admin)
        with self.assertRaises(pagamentos.PagamentoRecusado):
            pagamentos.registrar_pagamento(ag, self.admin)
        gratis = self.reserva(72, '0.00', status_pagamento='ISENTO')
        with self.assertRaises(pagamentos.PagamentoRecusado):
            pagamentos.registrar_pagamento(gratis, self.admin)

    def test_paga_somente_a_multa_quando_cancelada(self):
        ag = self.reserva(3, '10.00')
        reservas.cancelar(ag, self.aluno)
        pagamentos.registrar_pagamento(ag, self.admin)
        ag.refresh_from_db()
        self.assertEqual((ag.valor_pago, ag.status_pagamento), (Decimal('5.00'), 'PAGO'))
        self.assertEqual(ag.estorno_pendente, Decimal('0.00'))

    def test_estorno_integral_quando_paga_e_cancelada_sem_multa(self):
        ag = self.reserva(72, '10.00')
        pagamentos.registrar_pagamento(ag, self.admin)
        reservas.cancelar(ag, self.aluno)
        ag.refresh_from_db()
        self.assertEqual(ag.estorno_pendente, Decimal('10.00'))
        pagamentos.registrar_estorno(ag, self.admin)
        ag.refresh_from_db()
        self.assertEqual((ag.status_pagamento, ag.valor_estornado), ('ESTORNADO', Decimal('10.00')))
        self.assertEqual(ag.estorno_pendente, Decimal('0.00'))

    def test_estorno_parcial_retem_a_multa(self):
        ag = self.reserva(3, '10.00')
        pagamentos.registrar_pagamento(ag, self.admin)
        reservas.cancelar(ag, self.aluno)  # multa de 5,00 sobre os 10,00 já pagos
        ag.refresh_from_db()
        self.assertEqual(ag.estorno_pendente, Decimal('5.00'))
        pagamentos.registrar_estorno(ag, self.admin)
        ag.refresh_from_db()
        self.assertEqual(ag.valor_pago - ag.valor_estornado, Decimal('5.00'))  # fica a multa

    def test_estorno_recusado_sem_valor_a_devolver(self):
        ag = self.reserva(48, '10.00')
        with self.assertRaises(pagamentos.PagamentoRecusado):
            pagamentos.registrar_estorno(ag, self.admin)
        pagamentos.registrar_pagamento(ag, self.admin)
        with self.assertRaises(pagamentos.PagamentoRecusado):  # paga mas não cancelada
            pagamentos.registrar_estorno(ag, self.admin)

    def test_estorno_nao_repete(self):
        ag = self.reserva(72, '10.00')
        pagamentos.registrar_pagamento(ag, self.admin)
        reservas.cancelar(ag, self.aluno)
        pagamentos.registrar_estorno(ag, self.admin)
        with self.assertRaises(pagamentos.PagamentoRecusado):
            pagamentos.registrar_estorno(ag, self.admin)

    def test_tela_de_gestao_mostra_acoes(self):
        pendente = self.reserva(48, '10.00')
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('gerenciar_agendamentos'))
        self.assertContains(resp, reverse('registrar_pagamento', args=[pendente.id]))
        self.assertContains(resp, 'Pendente')


class DashboardComMultasTests(BaseFinanceira):
    def test_totais_de_multa_recebido_e_estorno(self):
        paga = self.reserva(48, '20.00')
        pagamentos.registrar_pagamento(paga, self.admin)            # recebido 20
        a_estornar = self.reserva(72, '10.00')
        pagamentos.registrar_pagamento(a_estornar, self.admin)      # +10
        reservas.cancelar(a_estornar, self.aluno)                   # sem multa: devolver 10
        com_multa = self.reserva(2, '10.00')
        reservas.cancelar(com_multa, self.aluno)                    # multa 5 pendente
        pendente = self.reserva(96, '8.00')                         # a receber 8
        self.client.force_login(self.admin)
        ctx = self.client.get(reverse('dashboard_financeiro')).context
        self.assertEqual(ctx['multas'], Decimal('5.00'))
        self.assertEqual(ctx['recebido'], Decimal('30.00'))
        self.assertEqual(ctx['a_receber'], Decimal('13.00'))        # 8 (reserva) + 5 (multa)
        self.assertEqual(ctx['estornos_pendentes'], Decimal('10.00'))
        pagamentos.registrar_estorno(a_estornar, self.admin)
        ctx = financeiro.dashboard()
        self.assertEqual(ctx['recebido'], Decimal('20.00'))
        self.assertEqual(ctx['estornos_pendentes'], Decimal('0.00'))
        self.assertIsNotNone(pendente.pk)

    def test_dashboard_vazio_zera_tudo(self):
        ctx = financeiro.dashboard()
        for chave in ('multas', 'recebido', 'a_receber', 'estornos_pendentes', 'total_geral'):
            self.assertEqual(ctx[chave], Decimal('0.00'), chave)

    def test_totais_do_usuario_incluem_a_pagar(self):
        usada = self.reserva(-3, '12.00')          # já usada e não paga
        multada = self.reserva(2, '10.00')
        reservas.cancelar(multada, self.aluno)     # multa 5
        paga = self.reserva(-6, '9.00')
        pagamentos.registrar_pagamento(paga, self.admin)
        totais = financeiro.totais_do_usuario(self.aluno)
        self.assertEqual(totais['a_pagar'], Decimal('17.00'))
        self.assertEqual(totais['gasto'], Decimal('21.00'))
        self.assertIsNotNone(usada.pk)


class MigracaoPagamentoTests(TransactionTestCase):
    """A migração 0012 classifica as reservas já existentes (canceladas e gratuitas = Isento)."""

    def test_classifica_reservas_existentes(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('agendamentos', '0011_notificacoes_e_config_email')])
        antigo = executor.loader.project_state([('agendamentos', '0011_notificacoes_e_config_email')]).apps
        Usuario, Lab = antigo.get_model('auth', 'User'), antigo.get_model('agendamentos', 'Laboratorio')
        Pc, Tipo = antigo.get_model('agendamentos', 'Computador'), antigo.get_model('agendamentos', 'TipoAgendamento')
        Ag = antigo.get_model('agendamentos', 'Agendamento')
        user = Usuario.objects.create(username='antigo')
        pc = Pc.objects.create(identificador='M1', laboratorio=Lab.objects.create(nome='Lab M'))
        tipo = Tipo.objects.create(nome='Tipo migracao', valor_hora=Decimal('10.00'))
        inicio = timezone.now() + timedelta(days=5)

        def mk(valor, status):
            return Ag.objects.create(
                usuario=user, computador=pc, tipo=tipo, valor_total=Decimal(valor), status=status,
                data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
            ).pk

        pago, cancelada, gratis = mk('10.00', 'CONFIRMADO'), mk('10.00', 'CANCELADO'), mk('0.00', 'CONFIRMADO')

        executor = MigrationExecutor(connection)
        executor.migrate([('agendamentos', '0012_multa_e_pagamento')])
        novo = executor.loader.project_state([('agendamentos', '0012_multa_e_pagamento')]).apps.get_model('agendamentos', 'Agendamento')
        self.assertEqual(novo.objects.get(pk=pago).status_pagamento, 'PENDENTE')
        self.assertEqual(novo.objects.get(pk=cancelada).status_pagamento, 'ISENTO')
        self.assertEqual(novo.objects.get(pk=gratis).status_pagamento, 'ISENTO')
        self.assertEqual(novo.objects.get(pk=pago).multa, Decimal('0'))
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


class ServicoReservarTests(BaseFinanceira):
    def test_recusa_horario_ocupado_e_limite(self):
        tipo = TipoAgendamento.objects.get(pk=id_tipo('Estudo'))
        inicio = proximo_bloco(timedelta(days=2))
        reservas.reservar(self.aluno, self.pc, tipo, inicio, inicio + timedelta(hours=1))
        outro = criar_usuario('outro_fin')
        with self.assertRaisesMessage(reservas.ReservaRecusada, 'já está reservado'):
            reservas.reservar(outro, self.pc, tipo, inicio, inicio + timedelta(hours=1))
        with self.assertRaisesMessage(reservas.ReservaRecusada, 'outra reserva nesse mesmo horário'):
            outra_maquina = Computador.objects.create(identificador='F2', laboratorio=self.lab)
            reservas.reservar(self.aluno, outra_maquina, tipo, inicio, inicio + timedelta(hours=1))

    @override_settings(AGENDAMENTO_MAX_RESERVAS_ATIVAS=1)
    def test_recusa_acima_do_limite_de_reservas_ativas(self):
        tipo = TipoAgendamento.objects.get(pk=id_tipo('Estudo'))
        inicio = proximo_bloco(timedelta(days=2))
        reservas.reservar(self.aluno, self.pc, tipo, inicio, inicio + timedelta(hours=1))
        depois = inicio + timedelta(hours=3)
        with self.assertRaisesMessage(reservas.ReservaRecusada, 'Limite de 1 reservas ativas'):
            reservas.reservar(self.aluno, self.pc, tipo, depois, depois + timedelta(hours=1))

    def test_recusa_maquina_em_manutencao(self):
        Computador.objects.filter(pk=self.pc.pk).update(status='MANUTENCAO')
        tipo = TipoAgendamento.objects.get(pk=id_tipo('Estudo'))
        inicio = proximo_bloco(timedelta(days=2))
        with self.assertRaisesMessage(reservas.ReservaRecusada, 'deixou de estar disponível'):
            reservas.reservar(self.aluno, self.pc, tipo, inicio, inicio + timedelta(hours=1))


class ServicoSolicitacoesTests(TestCase):
    def setUp(self):
        self.tecnico = criar_usuario('tec_srv', tipo='TECNICO')
        self.aluno = criar_usuario('aluno_srv')
        self.lab = Laboratorio.objects.create(nome='Lab S')
        self.pc = Computador.objects.create(identificador='S1', laboratorio=self.lab)
        self.sol = SolicitacaoInstalacao.objects.create(
            usuario=self.aluno, computador=self.pc, laboratorio=self.lab, software_nome='Git 2.0', justificativa='x',
        )

    def test_status_invalido_e_transicao_proibida(self):
        with self.assertRaisesMessage(solicitacoes.SolicitacaoRecusada, 'Status inválido'):
            solicitacoes.atualizar_status(self.sol, 'LIXO', self.tecnico)
        solicitacoes.atualizar_status(self.sol, 'REJEITADO', self.tecnico)
        with self.assertRaises(solicitacoes.SolicitacaoRecusada):
            solicitacoes.atualizar_status(self.sol, 'EM_ANDAMENTO', self.tecnico)

    def test_concluir_vincula_software_ao_inventario(self):
        sw = Software.objects.create(nome='Git', versao='2.0')
        aviso = solicitacoes.atualizar_status(self.sol, 'CONCLUIDO', self.tecnico)
        self.assertIn('adicionado ao inventário', aviso)
        self.assertIn(sw, self.pc.softwares.all())

    def test_retirar_so_se_pendente(self):
        solicitacoes.retirar(self.sol)
        self.assertEqual(self.sol.status, 'CANCELADO')
        with self.assertRaises(solicitacoes.SolicitacaoRecusada):
            solicitacoes.retirar(self.sol)


class ServicoUsuariosTests(TestCase):
    def setUp(self):
        self.admin = criar_usuario('adm_usr', tipo='ADMIN')
        self.alvo = criar_usuario('alvo_usr')

    def test_exclui_usuario_sem_historico(self):
        usuarios.excluir(self.admin, self.alvo)
        self.assertFalse(User.objects.filter(pk=self.alvo.pk).exists())

    def test_nao_exclui_a_si_mesmo(self):
        with self.assertRaisesMessage(usuarios.ExclusaoRecusada, 'própria conta'):
            usuarios.excluir(self.admin, self.admin)

    def test_admin_comum_nao_mexe_em_superusuario(self):
        root = User.objects.create_superuser('root_usr', password='senha-de-teste-123')
        self.assertIn('superusuário', usuarios.erro_superusuario(self.admin, root, 'excluir'))
        with self.assertRaises(usuarios.ExclusaoRecusada):
            usuarios.excluir(self.admin, root)
        self.assertIsNone(usuarios.erro_superusuario(root, self.alvo, 'excluir'))

    def test_usuario_com_reservas_e_protegido(self):
        lab = Laboratorio.objects.create(nome='Lab U')
        pc = Computador.objects.create(identificador='U1', laboratorio=lab)
        inicio = timezone.now() + timedelta(days=3)
        Agendamento.objects.create(
            tipo_id=id_tipo('Desenv'), usuario=self.alvo, computador=pc,
            data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1),
        )
        with self.assertRaisesMessage(usuarios.ExclusaoRecusada, 'histórico financeiro'):
            usuarios.excluir(self.admin, self.alvo)
        self.assertTrue(User.objects.filter(pk=self.alvo.pk).exists())
