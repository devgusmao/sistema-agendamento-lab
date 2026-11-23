"""Envia o lembrete das reservas que começam nas próximas horas.

Agende a execução a cada 10-15 minutos (cron):
    */15 * * * * docker compose exec -T web python manage.py enviar_lembretes
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from agendamentos import emails
from agendamentos.models import Agendamento


class Command(BaseCommand):
    help = 'Envia lembretes de reservas que começam nas próximas AGENDAMENTO_LEMBRETE_HORAS horas.'

    def handle(self, *args, **options):
        if not emails.evento_ativo('lembrete_reserva'):
            self.stdout.write('Notificação "lembrete_reserva" está desativada; nada a fazer.')
            return

        agora = timezone.now()
        limite = agora + timedelta(hours=settings.AGENDAMENTO_LEMBRETE_HORAS)
        enviados = 0
        with transaction.atomic():
            reservas = (
                Agendamento.objects.select_for_update(of=('self',))
                .select_related('usuario', 'computador__laboratorio')
                .filter(status='CONFIRMADO', lembrete_enviado_em__isnull=True,
                        data_hora_inicio__gt=agora, data_hora_inicio__lte=limite)
            )
            for ag in reservas:
                emails.notificar_lembrete_reserva(ag)
                ag.lembrete_enviado_em = agora
                ag.save(update_fields=['lembrete_enviado_em'])
                enviados += 1
        self.stdout.write(f'{enviados} lembrete(s) processado(s).')
