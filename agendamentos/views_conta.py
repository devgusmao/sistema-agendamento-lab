"""Telas públicas de conta: confirmar e-mail, esqueci a senha e criar nova senha pelo link."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .forms import EsqueciSenhaForm, NovaSenhaForm
from .servicos import contas

SESSAO_TOKEN = '_token_recuperacao_senha'
RESPOSTA_RECUPERACAO = (
    'Se este e-mail estiver cadastrado, enviamos um link para criar uma nova senha. '
    'Confira também a caixa de spam.'
)


def _ip(request):
    return request.META.get('REMOTE_ADDR', '')


@never_cache
def confirmar_email(request, token):
    usuario = contas.usuario_do_token_de_confirmacao(token)
    if usuario is None:
        return render(request, 'agendamentos/confirmar_email.html', {'valido': False}, status=400)
    contas.confirmar_email(usuario)
    return render(request, 'agendamentos/confirmar_email.html', {'valido': True, 'aprovado': usuario.perfil.aprovado})


@login_required
@require_POST
def reenviar_confirmacao(request):
    if request.user.perfil.email_verificado:
        return redirect('home')
    if contas.enviar_confirmacao(request.user, _ip(request)):
        messages.success(request, 'Enviamos um novo link de confirmação para o seu e-mail.')
    else:
        messages.error(request, 'Muitos pedidos em pouco tempo. Aguarde um pouco e tente de novo.')
    return redirect('home')


@never_cache
def esqueci_senha(request):
    if request.user.is_authenticated:
        return redirect('alterar_senha')
    if request.method == 'POST':
        form = EsqueciSenhaForm(request.POST)
        if form.is_valid():
            contas.solicitar_recuperacao(form.cleaned_data['email'], _ip(request))
            # Mesma resposta exista ou não a conta, e esteja ou não no limite de pedidos.
            messages.success(request, RESPOSTA_RECUPERACAO)
            return redirect('login')
    else:
        form = EsqueciSenhaForm()
    return render(request, 'agendamentos/esqueci_senha.html', {'form': form})


@never_cache
@sensitive_post_parameters()
def redefinir_senha(request, uidb64, token):
    """Valida o link e troca o token da URL por um da sessão, para não vazar em Referer nem histórico."""
    usuario = contas.usuario_do_uid(uidb64)

    if token == contas.TOKEN_NA_SESSAO:
        token_sessao = request.session.get(SESSAO_TOKEN, '')
        if not contas.token_de_recuperacao_valido(usuario, token_sessao):
            return render(request, 'agendamentos/redefinir_senha.html', {'valido': False}, status=400)
        if request.method == 'POST':
            form = NovaSenhaForm(usuario, request.POST)
            if form.is_valid():
                form.save()
                request.session.pop(SESSAO_TOKEN, None)
                contas.concluir_recuperacao(usuario)
                messages.success(request, 'Senha alterada com sucesso. Entre com a nova senha.')
                return redirect('login')
        else:
            form = NovaSenhaForm(usuario)
        return render(request, 'agendamentos/redefinir_senha.html', {'valido': True, 'form': form})

    if contas.token_de_recuperacao_valido(usuario, token):
        request.session[SESSAO_TOKEN] = token
        return redirect('redefinir_senha', uidb64=uidb64, token=contas.TOKEN_NA_SESSAO)
    return render(request, 'agendamentos/redefinir_senha.html', {'valido': False}, status=400)
