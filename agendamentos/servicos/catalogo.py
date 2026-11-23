"""Busca de máquinas para a tela inicial."""

from django.db.models import Prefetch, Q
from django.utils import timezone

from ..models import Agendamento, Computador


def buscar_computadores(busca='', lab_id='', status='', software_id=''):
    reservas_futuras = Agendamento.objects.filter(
        status='CONFIRMADO', data_hora_fim__gte=timezone.now()
    ).order_by('data_hora_inicio')

    computadores = Computador.objects.select_related('laboratorio').prefetch_related(
        'softwares', Prefetch('agendamentos', queryset=reservas_futuras, to_attr='reservas_ativas')
    )
    if busca:
        computadores = computadores.filter(
            Q(identificador__icontains=busca) | Q(laboratorio__nome__icontains=busca)
        )
    if lab_id.isdigit():
        computadores = computadores.filter(laboratorio_id=lab_id)
    if status in dict(Computador.STATUS_CHOICES):
        computadores = computadores.filter(status=status)
    if software_id.isdigit():
        # O join com softwares duplica linhas quando a máquina tem mais de um
        # software; distinct() evita a mesma máquina aparecer várias vezes.
        computadores = computadores.filter(softwares__id=software_id).distinct()
    return computadores
