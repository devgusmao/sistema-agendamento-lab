"""Cálculo de multa por cancelamento.

Regra: só o próprio dono cancelando uma reserva paga, já dentro da janela de
antecedência, paga multa (percentual do valor da reserva). Cancelamento feito
pela administração ou por manutenção da máquina nunca gera multa.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.utils import timezone

CENTAVOS = Decimal('0.01')


def prazo_sem_multa(inicio):
    """Último instante em que o dono ainda cancela sem multa."""
    return inicio - timedelta(hours=settings.AGENDAMENTO_MULTA_HORAS)


def calcular_multa(*, valor_total, inicio, dono_cancela, agora=None):
    """Multa (Decimal, 2 casas) devida se a reserva for cancelada `agora`."""
    agora = agora or timezone.now()
    if not dono_cancela or not valor_total or valor_total <= 0:
        return Decimal('0.00')
    if agora <= prazo_sem_multa(inicio):
        return Decimal('0.00')
    percentual = Decimal(settings.AGENDAMENTO_MULTA_PERCENTUAL) / Decimal(100)
    return (Decimal(valor_total) * percentual).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
