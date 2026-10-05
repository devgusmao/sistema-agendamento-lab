"""Envio de e-mails transacionais (Gmail/SMTP configurado via .env).

Nunca derruba a requisição: falha de SMTP é registrada no log e ignorada.
O endereço do destinatário não é gravado no log (LGPD).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _fmt(dt):
    return timezone.localtime(dt).strftime('%d/%m/%Y %H:%M')


def enviar(usuario, assunto, mensagem):
    """Envia após o commit da transação atual, se o usuário tiver e-mail."""
    if not usuario.email:
        return

    def _enviar():
        try:
            send_mail(f'[Agendamento Lab] {assunto}', mensagem, settings.DEFAULT_FROM_EMAIL, [usuario.email])
        except Exception:
            logger.exception('Falha ao enviar e-mail "%s" (usuário id=%s)', assunto, usuario.pk)

    transaction.on_commit(_enviar)


def notificar_reserva_confirmada(ag):
    enviar(ag.usuario, 'Reserva confirmada', (
        f'Olá, {ag.usuario.first_name or ag.usuario.username}!\n\n'
        f'Sua reserva foi confirmada:\n'
        f'Máquina: {ag.computador.identificador} ({ag.computador.laboratorio.nome})\n'
        f'Início: {_fmt(ag.data_hora_inicio)}\n'
        f'Fim: {_fmt(ag.data_hora_fim)}\n'
        f'Valor: R$ {ag.valor_total}\n'
    ))


def notificar_reserva_cancelada(ag, motivo=''):
    enviar(ag.usuario, 'Reserva cancelada', (
        f'Olá, {ag.usuario.first_name or ag.usuario.username}!\n\n'
        f'Sua reserva da máquina {ag.computador.identificador} '
        f'({ag.computador.laboratorio.nome}) em {_fmt(ag.data_hora_inicio)} foi cancelada.\n'
        + (f'Motivo: {motivo}\n' if motivo else '')
    ))
