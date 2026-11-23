"""Avisos de reserva à administração e confirmação de cancelamento ao próprio usuário."""

from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Agendamento, Computador, ConfiguracaoNotificacao, Laboratorio
from .tests import criar_usuario, id_tipo, proximo_bloco


class AvisosDeReservaTests(TestCase):
    def setUp(self):
        self.admin = criar_usuario('adm_av', tipo='ADMIN', email='adm@example.com')
        self.outro_admin = criar_usuario('adm2_av', tipo='ADMIN', email='adm2@example.com')
        self.aluno = criar_usuario('alu_av', email='alu@example.com')
        lab = Laboratorio.objects.create(nome='Lab Av')
        self.pc = Computador.objects.create(identificador='AV1', laboratorio=lab)

    def _reservar(self, usuario, delta=timedelta(days=2)):
        inicio = proximo_bloco(delta)
        self.client.force_login(usuario)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('criar_agendamento', args=[self.pc.id]), {
                'tipo': id_tipo('Desenv'),
                'data_hora_inicio': inicio.strftime('%Y-%m-%d %H:%M'),
                'data_hora_fim': (inicio + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M'),
            })

    def _reserva_existente(self, horas, valor='10.00'):
        inicio = timezone.now() + timedelta(hours=horas)
        return Agendamento.objects.create(
            tipo_id=id_tipo('Desenv'), usuario=self.aluno, computador=self.pc,
            data_hora_inicio=inicio, data_hora_fim=inicio + timedelta(hours=1), valor_total=Decimal(valor),
        )

    def _destinatarios(self):
        return sorted(tuple(m.to) for m in mail.outbox)

    def test_nova_reserva_avisa_o_dono_e_todos_os_administradores(self):
        self._reservar(self.aluno)
        self.assertEqual(self._destinatarios(), [('adm2@example.com',), ('adm@example.com',), ('alu@example.com',)])
        assunto_admin = next(m for m in mail.outbox if m.to == ['adm@example.com'])
        self.assertIn('Nova reserva', assunto_admin.subject)
        self.assertIn('alu_av', assunto_admin.body)

    def test_admin_que_reserva_nao_recebe_aviso_duplicado(self):
        self._reservar(self.admin)
        self.assertEqual(self._destinatarios(), [('adm2@example.com',), ('adm@example.com',)])
        para_admin = [m for m in mail.outbox if m.to == ['adm@example.com']]
        self.assertEqual(len(para_admin), 1)
        self.assertIn('confirmada', para_admin[0].subject.lower())

    def test_cancelamento_pelo_dono_avisa_ele_e_os_administradores(self):
        ag = self._reserva_existente(72)
        self.client.force_login(self.aluno)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cancelar_agendamento', args=[ag.id]))
        self.assertEqual(self._destinatarios(), [('adm2@example.com',), ('adm@example.com',), ('alu@example.com',)])
        dono = next(m for m in mail.outbox if m.to == ['alu@example.com'])
        self.assertIn('nenhuma multa', dono.body)

    def test_cancelamento_com_multa_informa_o_valor(self):
        ag = self._reserva_existente(3, '10.00')
        self.client.force_login(self.aluno)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cancelar_agendamento', args=[ag.id]))
        dono = next(m for m in mail.outbox if m.to == ['alu@example.com'])
        admin = next(m for m in mail.outbox if m.to == ['adm@example.com'])
        self.assertIn('R$ 5,00', dono.body)
        self.assertIn('multa de R$ 5,00 a cobrar', admin.body)
        self.assertIn('R$ 5,00', dono.alternatives[0][0])  # versão HTML

    def test_admin_cancelando_nao_gera_aviso_de_cancelamento_pelo_dono(self):
        ag = self._reserva_existente(72)
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cancelar_agendamento', args=[ag.id]), {'origem': 'admin'})
        self.assertEqual(self._destinatarios(), [('alu@example.com',)])
        self.assertIn('cancelada', mail.outbox[0].subject.lower())

    def test_avisos_podem_ser_desligados(self):
        ConfiguracaoNotificacao.objects.create(evento='reserva_nova_admin', ativo=False)
        self._reservar(self.aluno)
        self.assertEqual(self._destinatarios(), [('alu@example.com',)])
