"""Registro manual de pagamento e estorno (não há gateway de pagamento online).

O administrador confirma o recebimento fora do sistema e registra aqui. Valores
nunca são digitados: o pago é o que estava devido na hora (valor da reserva ou
multa) e o estorno é o que sobrou a devolver depois do cancelamento.
"""

from django.db import transaction
from django.utils import timezone

from ..models import Agendamento


class PagamentoRecusado(Exception):
    """Operação inválida para o estado atual da reserva; a mensagem é exibida ao admin."""


def _travar(agendamento):
    return Agendamento.objects.select_for_update().get(pk=agendamento.pk)


def registrar_pagamento(agendamento, ator):
    with transaction.atomic():
        ag = _travar(agendamento)
        if ag.status_pagamento != Agendamento.PAGAMENTO_PENDENTE or ag.valor_devido <= 0:
            raise PagamentoRecusado('Não há valor pendente de pagamento nesta reserva.')
        ag.status_pagamento = Agendamento.PAGAMENTO_PAGO
        ag.valor_pago = ag.valor_devido
        ag.pago_em = timezone.now()
        ag.pagamento_registrado_por = ator
        ag.save(update_fields=['status_pagamento', 'valor_pago', 'pago_em', 'pagamento_registrado_por'])
    agendamento.refresh_from_db()
    return agendamento


def registrar_estorno(agendamento, ator):
    with transaction.atomic():
        ag = _travar(agendamento)
        devolver = ag.estorno_pendente
        if devolver <= 0:
            raise PagamentoRecusado('Não há estorno pendente nesta reserva.')
        ag.valor_estornado += devolver
        ag.status_pagamento = Agendamento.PAGAMENTO_ESTORNADO
        ag.estornado_em = timezone.now()
        ag.pagamento_registrado_por = ator
        ag.save(update_fields=['valor_estornado', 'status_pagamento', 'estornado_em', 'pagamento_registrado_por'])
    agendamento.refresh_from_db()
    return agendamento
