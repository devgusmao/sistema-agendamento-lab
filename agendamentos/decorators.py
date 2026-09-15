"""Decoradores de controle de acesso.

Antes, cada view repetia a mesma expressão de checagem de papel inline. Além de
duplicado, isso deixava buracos: várias telas (minhas solicitações, meus
agendamentos, solicitar software) não verificavam se a conta estava aprovada,
então um usuário ainda pendente conseguia usar parte do sistema.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import perfil_aprovado, perfil_e_admin, perfil_e_gestor


def _exige(teste, mensagem):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not teste(request.user):
                messages.error(request, mensagem)
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


admin_required = _exige(
    perfil_e_admin,
    'Acesso restrito a administradores.',
)

gestor_required = _exige(
    perfil_e_gestor,
    'Acesso restrito à equipe técnica e a administradores.',
)


def aprovado_required(view_func):
    """Bloqueia contas que ainda não foram liberadas por um administrador."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not perfil_aprovado(request.user):
            return render(request, 'agendamentos/pendente.html', status=403)
        return view_func(request, *args, **kwargs)

    return _wrapped
