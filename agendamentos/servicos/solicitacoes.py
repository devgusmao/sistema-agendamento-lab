"""Solicitações de instalação de software: mudança de status e vínculo ao inventário."""

from django.db import transaction

from .. import emails
from ..models import Software, SolicitacaoInstalacao


class SolicitacaoRecusada(Exception):
    """Mudança não permitida; a mensagem é exibida ao usuário."""


def atualizar_status(solicitacao, novo_status, ator):
    """Muda o status, registra o técnico e avisa o solicitante. Devolve um aviso de inventário (pode ser '')."""
    opcoes = dict(SolicitacaoInstalacao.STATUS_CHOICES)
    # Sem esta validação qualquer string vinda do cliente era gravada no banco.
    if novo_status not in opcoes:
        raise SolicitacaoRecusada('Status inválido.')
    if not solicitacao.pode_mudar_para(novo_status):
        raise SolicitacaoRecusada(
            f'Não é possível mudar uma solicitação "{solicitacao.get_status_display()}" para "{opcoes[novo_status]}".'
        )

    aviso = ''
    with transaction.atomic():
        solicitacao.status = novo_status
        solicitacao.atendido_por = ator
        solicitacao.save(update_fields=['status', 'atendido_por', 'data_atualizacao'])
        if novo_status == 'CONCLUIDO':
            aviso = registrar_instalacao_no_inventario(solicitacao)
        emails.notificar_solicitacao_atualizada(solicitacao)
    return aviso


def registrar_instalacao_no_inventario(solicitacao):
    """Ao concluir, vincula o software à máquina solicitada, se ele existir no inventário."""
    if not solicitacao.computador_id:
        return ' Atualize o inventário da máquina onde o software foi instalado.'
    nome = solicitacao.software_nome.strip().lower()
    software = next((sw for sw in Software.objects.all() if str(sw).lower() == nome), None)
    if software is None:
        return ' Software não encontrado no inventário: cadastre-o e vincule à máquina.'
    solicitacao.computador.softwares.add(software)
    return f' "{software}" adicionado ao inventário de {solicitacao.computador.identificador}.'


def retirar(solicitacao):
    """O próprio solicitante retira um pedido que ainda não foi atendido."""
    if solicitacao.status != 'PENDENTE':
        raise SolicitacaoRecusada('Esta solicitação já está sendo atendida e não pode mais ser retirada.')
    solicitacao.status = 'CANCELADO'
    solicitacao.save(update_fields=['status', 'data_atualizacao'])
    return solicitacao
