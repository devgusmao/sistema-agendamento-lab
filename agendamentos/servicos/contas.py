"""Confirmação de e-mail no cadastro e recuperação de senha pelo próprio usuário.

Segurança aplicada:
- links de uso único (recuperação: o token deixa de valer quando a senha muda) e com validade;
- resposta igual exista ou não a conta, para não revelar quem está cadastrado;
- limite de pedidos por usuário e por IP;
- o link nunca é montado a partir do cabeçalho Host (usa SITE_URL);
- só contas ativas recebem o link de recuperação.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .. import emails
from . import limites

SAL_CONFIRMACAO = 'agendamentos.confirmar-email'
TOKEN_NA_SESSAO = 'definir-senha'


def _url(nome, *args):
    return settings.SITE_URL.rstrip('/') + reverse(nome, args=args)


# --- Confirmação de e-mail ---

def gerar_token_confirmacao(usuario):
    """Token assinado com o id e o e-mail atual: trocar o e-mail invalida links antigos."""
    return signing.dumps({'u': usuario.pk, 'e': usuario.email.lower()}, salt=SAL_CONFIRMACAO)


def usuario_do_token_de_confirmacao(token):
    """Usuário dono do token, ou None se ele for inválido, adulterado, expirado ou de e-mail antigo."""
    try:
        dados = signing.loads(token, salt=SAL_CONFIRMACAO, max_age=settings.CONFIRMACAO_EMAIL_VALIDADE_HORAS * 3600)
        usuario = User.objects.get(pk=dados['u'], is_active=True)
    except (signing.BadSignature, User.DoesNotExist, KeyError, TypeError):
        return None
    return usuario if usuario.email.lower() == dados['e'] else None


def enviar_confirmacao(usuario, ip=''):
    """Envia o link de confirmação. Devolve False se o limite de pedidos foi atingido ou não há e-mail."""
    if not usuario.email:
        return False
    if not limites.permitir(f'confirmacao:usuario:{usuario.pk}', settings.LIMITE_EMAIL_POR_USUARIO_HORA):
        return False
    if ip and not limites.permitir(f'confirmacao:ip:{ip}', settings.LIMITE_EMAIL_POR_IP_HORA):
        return False
    emails.notificar_confirmacao_email(
        usuario, _url('confirmar_email', gerar_token_confirmacao(usuario)),
        settings.CONFIRMACAO_EMAIL_VALIDADE_HORAS,
    )
    return True


def confirmar_email(usuario):
    """Marca o e-mail como confirmado. Na primeira vez, avisa os administradores do novo cadastro."""
    perfil = usuario.perfil
    if perfil.email_verificado:
        return False
    perfil.email_verificado = True
    perfil.save(update_fields=['email_verificado'])
    if not perfil.aprovado:
        emails.notificar_novo_cadastro(usuario)
    return True


# --- Recuperação de senha ---

def solicitar_recuperacao(email, ip=''):
    """Envia o link de recuperação às contas ativas com esse e-mail.

    O chamador deve responder sempre a mesma coisa, enviando ou não (não revela se a conta existe).
    """
    email = (email or '').strip().lower()
    if not email:
        return 0
    if ip and not limites.permitir(f'recuperacao:ip:{ip}', settings.LIMITE_EMAIL_POR_IP_HORA):
        return 0
    enviados = 0
    for usuario in User.objects.filter(email__iexact=email, is_active=True):
        if not limites.permitir(f'recuperacao:usuario:{usuario.pk}', settings.LIMITE_EMAIL_POR_USUARIO_HORA):
            continue
        uid = urlsafe_base64_encode(force_bytes(usuario.pk))
        emails.notificar_recuperacao_senha(
            usuario, _url('redefinir_senha', uid, default_token_generator.make_token(usuario)),
            settings.PASSWORD_RESET_TIMEOUT // 60,
        )
        enviados += 1
    return enviados


def usuario_do_uid(uidb64):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)), is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def token_de_recuperacao_valido(usuario, token):
    return bool(usuario) and bool(token) and default_token_generator.check_token(usuario, token)


def concluir_recuperacao(usuario):
    """Depois da nova senha: prova o e-mail, libera tentativas de login e avisa o dono da conta."""
    from axes.utils import reset
    confirmar_email(usuario)  # quem abriu o link no e-mail comprovou que é dono dele
    reset(username=usuario.username)
    emails.notificar_senha_alterada(usuario)
