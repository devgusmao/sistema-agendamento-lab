"""Totais financeiros: painel do usuário e dashboard da administração."""

from datetime import datetime
from decimal import Decimal

from django.db.models import Count, DecimalField, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from ..models import Agendamento, Computador, Laboratorio

ZERO = Decimal('0.00')


def parse_data(valor):
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def totais_do_usuario(usuario, agora=None):
    """Quanto o usuário já usou, tem previsto e deve (reservas pendentes + multas)."""
    agora = agora or timezone.now()
    reservas = Agendamento.objects.filter(usuario=usuario)
    confirmadas = reservas.filter(status='CONFIRMADO')
    pendente = Q(status_pagamento=Agendamento.PAGAMENTO_PENDENTE)
    usadas_pendentes = reservas.filter(pendente, status='CONFIRMADO', data_hora_fim__lte=agora)
    multas_pendentes = reservas.filter(pendente, status='CANCELADO')
    return {
        'gasto': confirmadas.filter(data_hora_fim__lte=agora).aggregate(t=Sum('valor_total'))['t'] or ZERO,
        'previsto': confirmadas.filter(data_hora_fim__gt=agora).aggregate(t=Sum('valor_total'))['t'] or ZERO,
        'a_pagar': (usadas_pendentes.aggregate(t=Sum('valor_total'))['t'] or ZERO)
        + (multas_pendentes.aggregate(t=Sum('multa'))['t'] or ZERO),
    }


def _soma(campo, filtro):
    return Sum(campo, filter=filtro, output_field=DecimalField(max_digits=12, decimal_places=2))


def dashboard(de=None, ate=None, lab_id='', agora=None):
    """Contexto do dashboard financeiro, filtrado por período (início da reserva) e laboratório."""
    agora = agora or timezone.now()

    def periodo_q(prefixo=''):
        q = Q()
        if de:
            q &= Q(**{f'{prefixo}data_hora_inicio__date__gte': de})
        if ate:
            q &= Q(**{f'{prefixo}data_hora_inicio__date__lte': ate})
        return q

    por_laboratorio = lab_id.isdigit() if isinstance(lab_id, str) else bool(lab_id)
    confirmado = Q(status='CONFIRMADO')
    cancelado = Q(status='CANCELADO')

    base = Agendamento.objects.filter(periodo_q())
    if por_laboratorio:
        base = base.filter(computador__laboratorio_id=lab_id)

    totais = base.aggregate(
        realizada=_soma('valor_total', confirmado & Q(data_hora_fim__lte=agora)),
        prevista=_soma('valor_total', confirmado & Q(data_hora_fim__gt=agora)),
        cancelado=_soma('valor_total', cancelado),
        multas=_soma('multa', cancelado),
        pago=_soma('valor_pago', Q()),
        estornado=_soma('valor_estornado', Q()),
        a_receber_reservas=_soma('valor_total', confirmado & Q(status_pagamento=Agendamento.PAGAMENTO_PENDENTE)),
        a_receber_multas=_soma('multa', cancelado & Q(status_pagamento=Agendamento.PAGAMENTO_PENDENTE)),
        estornos_pendentes=Sum(
            ExpressionWrapper(F('valor_pago') - F('multa') - F('valor_estornado'),
                              output_field=DecimalField(max_digits=12, decimal_places=2)),
            filter=cancelado & Q(status_pagamento=Agendamento.PAGAMENTO_PAGO),
        ),
        reservas=Count('id', filter=confirmado),
        canceladas=Count('id', filter=cancelado),
        duracao=Sum(
            ExpressionWrapper(F('data_hora_fim') - F('data_hora_inicio'), output_field=DurationField()),
            filter=confirmado,
        ),
    )
    receita_realizada = totais['realizada'] or ZERO
    receita_prevista = totais['prevista'] or ZERO
    total_geral = receita_realizada + receita_prevista
    total_reservas = totais['reservas'] or 0
    total_canceladas = totais['canceladas'] or 0
    solicitadas = total_reservas + total_canceladas
    multas = totais['multas'] or ZERO
    recebido = (totais['pago'] or ZERO) - (totais['estornado'] or ZERO)

    ag = 'computadores__agendamentos__'
    ativa_lab = periodo_q(ag) & Q(**{f'{ag}status': 'CONFIRMADO'})
    por_lab = Laboratorio.objects.annotate(
        maquinas=Count('computadores', distinct=True),
        agendamentos=Count(f'{ag}id', filter=ativa_lab, distinct=True),
        receita=Sum(f'{ag}valor_total', filter=ativa_lab),
    ).order_by('nome')

    ag_pc = 'agendamentos__'
    ativa_pc = periodo_q(ag_pc) & Q(**{f'{ag_pc}status': 'CONFIRMADO'})
    maquinas = Computador.objects.select_related('laboratorio').annotate(
        total_agendamentos=Count(f'{ag_pc}id', filter=ativa_pc),
        receita=Sum(f'{ag_pc}valor_total', filter=ativa_pc),
    ).order_by(F('receita').desc(nulls_last=True), 'laboratorio__nome', 'identificador')

    if por_laboratorio:
        por_lab = por_lab.filter(id=lab_id)
        maquinas = maquinas.filter(laboratorio_id=lab_id)

    confirmados = base.filter(confirmado)
    por_finalidade = list(
        confirmados.values('tipo__nome').annotate(total=Count('id'), receita=Sum('valor_total')).order_by('-total')
    )
    for linha in por_finalidade:
        linha['rotulo'] = linha['tipo__nome']

    por_mes = list(
        confirmados.annotate(mes=TruncMonth('data_hora_inicio'))
        .values('mes').annotate(total=Count('id'), receita=Sum('valor_total')).order_by('-mes')[:12]
    )

    return {
        'summary': por_lab,
        'maquinas': maquinas,
        'total_geral': total_geral,
        'receita_realizada': receita_realizada,
        'receita_prevista': receita_prevista,
        'valor_cancelado': totais['cancelado'] or ZERO,
        'multas': multas,
        'recebido': recebido,
        'a_receber': (totais['a_receber_reservas'] or ZERO) + (totais['a_receber_multas'] or ZERO),
        'estornos_pendentes': totais['estornos_pendentes'] or ZERO,
        'total_reservas': total_reservas,
        'total_canceladas': total_canceladas,
        'taxa_cancelamento': round(100 * total_canceladas / solicitadas, 1) if solicitadas else 0,
        'ticket_medio': (total_geral / total_reservas).quantize(Decimal('0.01')) if total_reservas else ZERO,
        'horas_reservadas': round(totais['duracao'].total_seconds() / 3600, 1) if totais['duracao'] else 0,
        'por_finalidade': por_finalidade,
        'por_mes': por_mes,
    }
