"""Regras de janela da reserva (duração, blocos, antecedência, horário de funcionamento)."""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

TOLERANCIA_PASSADO = timedelta(minutes=5)  # tempo gasto preenchendo o formulário


def validar_janela(inicio, fim, tipo=None):
    """Levanta ValidationError se o intervalo violar alguma regra de reserva."""
    agora = timezone.now()
    minima = timedelta(minutes=settings.AGENDAMENTO_DURACAO_MINIMA_MIN)
    maxima = timedelta(minutes=tipo.duracao_maxima() if tipo else settings.AGENDAMENTO_DURACAO_MAXIMA_MIN)
    antecedencia = timedelta(days=settings.AGENDAMENTO_ANTECEDENCIA_MAXIMA_DIAS)
    bloco = settings.AGENDAMENTO_BLOCO_MIN

    if inicio < agora - TOLERANCIA_PASSADO:
        raise ValidationError('A data de início do agendamento não pode ser no passado.')

    if inicio > agora + antecedencia:
        raise ValidationError(
            f'Só é possível reservar com até {settings.AGENDAMENTO_ANTECEDENCIA_MAXIMA_DIAS} dias de antecedência.'
        )

    if fim <= inicio:
        raise ValidationError('A data/hora de término deve ser posterior ao horário de início.')

    for rotulo, dt in (('início', inicio), ('término', fim)):
        local = timezone.localtime(dt)
        if local.second or local.microsecond or local.minute % bloco:
            raise ValidationError(
                f'O {rotulo} deve estar alinhado a blocos de {bloco} minutos (ex.: 14:00, 14:30).'
            )

    if fim - inicio < minima:
        raise ValidationError(f'A duração mínima da reserva é de {settings.AGENDAMENTO_DURACAO_MINIMA_MIN} minutos.')

    if fim - inicio > maxima:
        horas = maxima.total_seconds() / 3600
        raise ValidationError(f'O tempo máximo permitido por reserva é de {horas:g} hora(s).')

    _validar_horario_de_funcionamento(inicio, fim)


def _validar_horario_de_funcionamento(inicio, fim):
    abertura, fechamento = settings.AGENDAMENTO_HORA_ABERTURA, settings.AGENDAMENTO_HORA_FECHAMENTO
    if (abertura, fechamento) == (0, 24):
        return
    li, lf = timezone.localtime(inicio), timezone.localtime(fim)
    minutos_ini = li.hour * 60 + li.minute
    # término à meia-noite do dia seguinte conta como 24h
    virou_dia = lf.date() > li.date()
    minutos_fim = 24 * 60 if virou_dia and lf.hour == lf.minute == 0 else lf.hour * 60 + lf.minute
    if (virou_dia and minutos_fim != 24 * 60) or minutos_ini < abertura * 60 or minutos_fim > fechamento * 60:
        raise ValidationError(f'Os laboratórios funcionam das {abertura:02d}h às {fechamento:02d}h.')
