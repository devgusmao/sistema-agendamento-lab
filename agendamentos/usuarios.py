"""Regras únicas para alterar perfil/acesso de usuários.

Antes, três telas (aprovar/revogar, editar usuário e permissões de acesso)
gravavam os mesmos campos com regras de proteção duplicadas e divergentes.
Toda mudança passa por `erro_ao_alterar` + `aplicar`.
"""

from . import emails
from .models import Perfil


def erro_ao_alterar(ator, alvo, *, tipo=None, aprovado=None):
    """Mensagem de erro se `ator` não puder aplicar a mudança em `alvo`; None se puder.

    `tipo`/`aprovado` None significam "não será alterado".
    """
    if ator.is_superuser:
        if alvo.is_superuser and alvo.id != ator.id and aprovado is False:
            return 'O acesso de outro superusuário não pode ser revogado por aqui.'
        return None

    perfil = Perfil.objects.get_or_create(usuario=alvo)[0]

    if alvo.is_superuser:
        return 'Apenas um superusuário pode alterar outro superusuário.'

    if alvo.id == ator.id and (
        (tipo is not None and tipo != perfil.tipo) or aprovado is False
    ):
        return 'Você não pode alterar o próprio nível nem remover o próprio acesso.'

    mexe_em_admin = perfil.tipo == 'ADMIN' and (
        (tipo is not None and tipo != 'ADMIN') or (aprovado is False and perfil.aprovado)
    )
    if mexe_em_admin:
        return 'Apenas um superusuário pode rebaixar ou revogar um administrador.'

    if tipo == 'ADMIN' and perfil.tipo != 'ADMIN':
        return 'Apenas um superusuário pode promover alguém a administrador.'

    return None


def aplicar(perfil, *, tipo=None, aprovado=None):
    """Grava a mudança e notifica o usuário quando o acesso é liberado ou revogado."""
    era_aprovado = perfil.aprovado
    campos = []
    if tipo is not None and tipo != perfil.tipo:
        perfil.tipo = tipo
        campos.append('tipo')
    if aprovado is not None and aprovado != perfil.aprovado:
        perfil.aprovado = aprovado
        campos.append('aprovado')
    if campos:
        perfil.save(update_fields=campos)
    if 'aprovado' in campos:
        if aprovado and not era_aprovado:
            emails.notificar_cadastro_aprovado(perfil.usuario)
        elif not aprovado and era_aprovado:
            emails.notificar_acesso_revogado(perfil.usuario)
