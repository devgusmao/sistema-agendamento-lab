"""Reservar e cancelar máquinas (com trava de concorrência, multa e e-mails)."""

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .. import emails
from ..models import Agendamento, Computador, perfil_e_admin
from .financeiro import totais_do_usuario
from .precos import calcular_multa


class ReservaRecusada(Exception):
    """Reserva não pôde ser feita; a mensagem é exibida ao usuário."""


class CancelamentoRecusado(Exception):
    """Cancelamento não permitido. `sem_permissao` distingue falta de acesso de estado inválido."""

    def __init__(self, mensagem, sem_permissao=False):
        super().__init__(mensagem)
        self.sem_permissao = sem_permissao


def reservas_futuras_da_maquina(computador):
    return Agendamento.objects.filter(
        computador=computador, status='CONFIRMADO', data_hora_fim__gte=timezone.now()
    ).order_by('data_hora_inicio')


def _divida_que_bloqueia(usuario):
    """Valor em aberto se ele passa do limite configurado; None se pode reservar.

    Administradores não são bloqueados; limite negativo desliga a regra.
    """
    limite = settings.AGENDAMENTO_LIMITE_DIVIDA
    if limite < 0 or perfil_e_admin(usuario):
        return None
    a_pagar = totais_do_usuario(usuario)['a_pagar']
    return a_pagar if a_pagar > limite else None


def _motivo_de_recusa(usuario, computador, inicio, fim):
    """Primeira regra violada ou None. Deve rodar sob as travas de `reservar`."""
    confirmadas = Agendamento.objects.filter(status='CONFIRMADO')
    divida = _divida_que_bloqueia(usuario)
    if divida is not None:
        return (
            f'Você tem R$ {divida:.2f} em aberto (uso e multas). '
            'Regularize o pagamento com a administração para fazer novas reservas.'
        )
    if not computador.disponivel:
        return 'Esta máquina deixou de estar disponível para reservas.'
    if confirmadas.filter(computador=computador, data_hora_inicio__lt=fim, data_hora_fim__gt=inicio).exists():
        return 'Este computador já está reservado nesse horário. Escolha outro intervalo.'
    if confirmadas.filter(usuario=usuario, data_hora_inicio__lt=fim, data_hora_fim__gt=inicio).exists():
        return 'Você já tem outra reserva nesse mesmo horário.'
    limite = settings.AGENDAMENTO_MAX_RESERVAS_ATIVAS
    if confirmadas.filter(usuario=usuario, data_hora_fim__gt=timezone.now()).count() >= limite:
        return (
            f'Limite de {limite} reservas ativas atingido. '
            'Cancele ou aguarde o término de uma reserva para agendar outra.'
        )
    return None


def reservar(usuario, computador, tipo, inicio, fim):
    """Cria a reserva ou levanta `ReservaRecusada`.

    Conflito e gravação acontecem sob o mesmo lock: sem isso, duas reservas
    simultâneas para o mesmo horário passavam as duas pela checagem.
    """
    with transaction.atomic():
        travado = Computador.objects.select_for_update(of=('self',)).select_related('laboratorio').get(pk=computador.pk)
        # Trava também o usuário, para serializar as checagens por usuário.
        User.objects.select_for_update().get(pk=usuario.pk)

        motivo = _motivo_de_recusa(usuario, travado, inicio, fim)
        if motivo:
            raise ReservaRecusada(motivo)

        agendamento = Agendamento(
            usuario=usuario, computador=travado, tipo=tipo, data_hora_inicio=inicio, data_hora_fim=fim,
        )
        agendamento.valor_hora_aplicado, agendamento.valor_total = tipo.calcular_valor(inicio, fim)
        if agendamento.valor_total <= 0:
            agendamento.status_pagamento = Agendamento.PAGAMENTO_ISENTO
        agendamento.save()
        emails.notificar_reserva_confirmada(agendamento)
        emails.notificar_nova_reserva_admins(agendamento)
    return agendamento


def cancelar(agendamento, ator):
    """Cancela a reserva em nome de `ator`, aplicando multa quando devida.

    Levanta `CancelamentoRecusado` se o ator não pode ou a reserva não está mais ativa.
    A linha é relida sob trava: um pagamento registrado ao mesmo tempo não pode ser sobrescrito.
    """
    with transaction.atomic():
        atual = Agendamento.objects.select_for_update().select_related('usuario').get(pk=agendamento.pk)

        if atual.usuario_id != ator.id and not perfil_e_admin(ator):
            raise CancelamentoRecusado('Você não tem permissão para cancelar este agendamento.', sem_permissao=True)

        if not atual.pode_ser_cancelado_por(ator):
            if atual.status == 'CANCELADO':
                raise CancelamentoRecusado('Este agendamento já estava cancelado.')
            raise CancelamentoRecusado('Reservas que já terminaram não podem ser canceladas.')

        multa = calcular_multa(
            valor_total=atual.valor_total,
            inicio=atual.data_hora_inicio,
            dono_cancela=atual.usuario_id == ator.id,
        )
        atual.cancelar(ator, multa=multa)
        if atual.usuario_id != ator.id:
            emails.notificar_reserva_cancelada(atual, 'cancelada pela administração.')
        else:
            emails.notificar_cancelamento_pelo_dono(atual)
    agendamento.refresh_from_db()
    return agendamento


def cancelar_futuras_da_maquina(computador, ator):
    """Cancela as reservas que ainda não terminaram quando a máquina sai de operação.

    Deve rodar dentro de `transaction.atomic()`. Nunca gera multa (quem cancela é a administração).
    """
    pendentes = list(
        Agendamento.objects.select_for_update()
        .select_related('usuario', 'computador__laboratorio')
        .filter(computador=computador, status='CONFIRMADO', data_hora_fim__gt=timezone.now())
    )
    for ag in pendentes:
        ag.cancelar(ator)
        emails.notificar_reserva_cancelada(ag, f'a máquina entrou em "{computador.get_status_display()}".')
    return len(pendentes)
