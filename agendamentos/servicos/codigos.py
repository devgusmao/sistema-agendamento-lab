"""Códigos numéricos curtos (6 dígitos) para confirmar e-mail e recuperar senha.

Por ser curto, o código depende de outras proteções: validade de poucos minutos, uso único,
limite de tentativas erradas por código, um código ativo por usuário e finalidade, e guarda
apenas como HMAC com a SECRET_KEY (o dump do banco sozinho não revela o código).
"""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import CodigoVerificacao

TAMANHO = 6


def normalizar(texto):
    """Só os dígitos; devolve '' se não sobrar exatamente um código de 6 dígitos."""
    digitos = re.sub(r'\D', '', texto or '')
    return digitos if len(digitos) == TAMANHO else ''


def _hash(usuario_id, finalidade, codigo):
    mensagem = f'{usuario_id}:{finalidade}:{codigo}'.encode()
    return hmac.new(settings.SECRET_KEY.encode(), mensagem, hashlib.sha256).hexdigest()


def gerar(usuario, finalidade, validade_min):
    """Cria um código novo (invalidando os anteriores) e devolve o texto, que só existe no e-mail."""
    agora = timezone.now()
    with transaction.atomic():
        CodigoVerificacao.objects.filter(usuario=usuario, finalidade=finalidade, usado_em__isnull=True).update(usado_em=agora)
        codigo = f'{secrets.randbelow(10 ** TAMANHO):0{TAMANHO}d}'
        CodigoVerificacao.objects.create(
            usuario=usuario, finalidade=finalidade, codigo_hash=_hash(usuario.pk, finalidade, codigo),
            expira_em=agora + timedelta(minutes=validade_min),
        )
    return codigo


def conferir(usuario, finalidade, digitado):
    """Confere o código sem consumi-lo. Devolve o registro se certo; erro conta como tentativa."""
    codigo = normalizar(digitado)
    if not codigo:
        return None
    with transaction.atomic():
        ativo = (
            CodigoVerificacao.objects.select_for_update()
            .filter(usuario=usuario, finalidade=finalidade, usado_em__isnull=True, expira_em__gt=timezone.now())
            .order_by('-criado_em').first()
        )
        if ativo is None:
            return None
        if hmac.compare_digest(ativo.codigo_hash, _hash(usuario.pk, finalidade, codigo)):
            return ativo
        ativo.tentativas += 1
        if ativo.tentativas >= settings.CODIGO_MAX_TENTATIVAS:
            ativo.usado_em = timezone.now()  # esgotou as tentativas: precisa pedir outro
        ativo.save(update_fields=['tentativas', 'usado_em'])
    return None


def consumir(registro):
    """Marca o código como usado. False se alguém já o usou antes (uso único)."""
    with transaction.atomic():
        atual = CodigoVerificacao.objects.select_for_update().get(pk=registro.pk)
        if atual.usado_em is not None or atual.expira_em <= timezone.now():
            return False
        atual.usado_em = timezone.now()
        atual.save(update_fields=['usado_em'])
    return True


def limpar_antigos(dias=2):
    CodigoVerificacao.objects.filter(expira_em__lt=timezone.now() - timedelta(days=dias)).delete()
