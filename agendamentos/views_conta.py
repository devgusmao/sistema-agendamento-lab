"""Telas públicas de conta: confirmar e-mail, esqueci a senha e criar nova senha com código de 6 dígitos."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .forms import CodigoForm, EsqueciSenhaForm, NovaSenhaForm
from .servicos import contas

SESSAO_EMAIL = '_email_codigo'
RESPOSTA_RECUPERACAO = (
    'Se este e-mail estiver cadastrado, enviamos um código de 6 dígitos. '
    'Digite-o abaixo para criar uma nova senha. Confira também a caixa de spam.'
)
RESPOSTA_REENVIO = 'Se este e-mail estiver aguardando confirmação, enviamos um novo código.'
CODIGO_INVALIDO = 'Código inválido ou expirado. Confira o código ou peça um novo.'
MUITAS_TENTATIVAS = 'Muitas tentativas em pouco tempo. Aguarde um pouco e tente de novo.'


def _ip(request):
    return request.META.get('REMOTE_ADDR', '')


def _inicial_do_email(request):
    return {'email': request.session.get(SESSAO_EMAIL, '')}


@never_cache
def confirmar_email(request):
    """Tela para digitar o código de confirmação recebido por e-mail."""
    if request.method == 'POST':
        form = CodigoForm(request.POST)
        if form.is_valid():
            if not contas.tentativa_permitida(_ip(request)):
                form.add_error('codigo', MUITAS_TENTATIVAS)
            else:
                usuario = contas.confirmar_com_codigo(form.cleaned_data['email'], form.cleaned_data['codigo'])
                if usuario is None:
                    form.add_error('codigo', CODIGO_INVALIDO)
                else:
                    request.session.pop(SESSAO_EMAIL, None)
                    return render(request, 'agendamentos/confirmar_email.html', {
                        'confirmado': True, 'aprovado': usuario.perfil.liberado or usuario.perfil.aprovado,
                    })
    else:
        form = CodigoForm(initial=_inicial_do_email(request))
    return render(request, 'agendamentos/confirmar_email.html', {'form': form})


@require_POST
def reenviar_confirmacao(request):
    """Reenvia o código (logado: para si; anônimo: para o e-mail informado). Resposta sempre igual."""
    if request.user.is_authenticated:
        if request.user.perfil.email_verificado:
            return redirect('home')
        enviado = contas.enviar_confirmacao(request.user, _ip(request))
        messages.success(request, 'Enviamos um novo código de confirmação para o seu e-mail.') if enviado else messages.error(
            request, 'Muitos pedidos em pouco tempo. Aguarde um pouco e tente de novo.')
        return redirect('confirmar_email')
    contas.reenviar_confirmacao_por_email(request.POST.get('email', ''), _ip(request))
    messages.success(request, RESPOSTA_REENVIO)
    return redirect('confirmar_email')


@never_cache
def esqueci_senha(request):
    if request.user.is_authenticated:
        return redirect('alterar_senha')
    if request.method == 'POST':
        form = EsqueciSenhaForm(request.POST)
        if form.is_valid():
            contas.solicitar_recuperacao(form.cleaned_data['email'], _ip(request))
            request.session[SESSAO_EMAIL] = form.cleaned_data['email']
            # Mesma resposta exista ou não a conta, e esteja ou não no limite de pedidos.
            messages.success(request, RESPOSTA_RECUPERACAO)
            return redirect('redefinir_senha')
    else:
        form = EsqueciSenhaForm()
    return render(request, 'agendamentos/esqueci_senha.html', {'form': form})


@never_cache
@sensitive_post_parameters()
def redefinir_senha(request):
    """E-mail + código + nova senha, numa tela só. O código só é consumido se a senha for aceita."""
    if request.user.is_authenticated:
        return redirect('alterar_senha')
    if request.method != 'POST':
        return render(request, 'agendamentos/redefinir_senha.html', {
            'form_codigo': CodigoForm(initial=_inicial_do_email(request)), 'form_senha': None,
        })

    form_codigo = CodigoForm(request.POST)
    form_senha = None
    if form_codigo.is_valid():
        if not contas.tentativa_permitida(_ip(request)):
            form_codigo.add_error('codigo', MUITAS_TENTATIVAS)
        else:
            usuario = contas.usuario_pelo_email(form_codigo.cleaned_data['email'])
            registro = usuario and contas.conferir_codigo_de_recuperacao(usuario, form_codigo.cleaned_data['codigo'])
            if not registro:
                form_codigo.add_error('codigo', CODIGO_INVALIDO)
            else:
                form_senha = NovaSenhaForm(usuario, request.POST)
                if form_senha.is_valid():
                    if contas.concluir_recuperacao(usuario, registro):
                        form_senha.save()
                        request.session.pop(SESSAO_EMAIL, None)
                        messages.success(request, 'Senha alterada com sucesso. Entre com a nova senha.')
                        return redirect('login')
                    form_codigo.add_error('codigo', CODIGO_INVALIDO)
    return render(request, 'agendamentos/redefinir_senha.html', {'form_codigo': form_codigo, 'form_senha': form_senha})
