"""Limite de pedidos sensíveis por chave (usuário ou IP) em uma janela de tempo."""

from datetime import timedelta

from django.utils import timezone

from ..models import LimiteSolicitacao


def permitir(chave, maximo, janela=timedelta(hours=1)):
    """Registra o pedido e diz se ainda está dentro do limite. Pedidos acima do limite não são contados."""
    agora = timezone.now()
    recentes = LimiteSolicitacao.objects.filter(chave=chave, criado_em__gte=agora - janela).count()
    if recentes >= maximo:
        return False
    LimiteSolicitacao.objects.create(chave=chave)
    return True


def limpar_antigos(dias=2):
    """Remove registros que já saíram de qualquer janela."""
    LimiteSolicitacao.objects.filter(criado_em__lt=timezone.now() - timedelta(days=dias)).delete()
