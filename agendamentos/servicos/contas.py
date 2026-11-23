"""Confirmação de e-mail no cadastro e recuperação de senha pelo próprio usuário.

Segurança aplicada:
- código numérico de 6 dígitos, de uso único, com validade curta e limite de tentativas
  (ver `codigos`); guardado só como HMAC;
- resposta igual exista ou não a conta, para não revelar quem está cadastrado;
- limite de pedidos por usuário e por IP, e de tentativas de digitar código por IP;
- só contas ativas recebem código.
"""

from django.conf import settings
from django.contrib.auth.models import User

from .. import emails
from ..models import CodigoVerificacao
from . import codigos, limites


def usuario_pelo_email(email):
    email = (email or '').strip().lower()
    if not email:
        return None
    return User.objects.filter(email__iexact=email, is_active=True).first()


def tentativa_permitida(ip):
    """Limita as tentativas de digitar código por IP (contra adivinhação)."""
    return not ip or limites.permitir(f'codigo:ip:{ip}', settings.LIMITE_TENTATIVAS_TOKEN_IP_HORA)


def _pedido_permitido(tipo, usuario, ip):
    if not limites.permitir(f'{tipo}:usuario:{usuario.pk}', settings.LIMITE_EMAIL_POR_USUARIO_HORA):
        return False
    return not ip or limites.permitir(f'{tipo}:ip:{ip}', settings.LIMITE_EMAIL_POR_IP_HORA)


# --- Confirmação de e-mail ---

def enviar_confirmacao(usuario, ip=''):
    """Envia o código de confirmação. Devolve False se o limite foi atingido ou não há e-mail."""
    if not usuario.email or not _pedido_permitido('confirmacao', usuario, ip):
        return False
    minutos = settings.CONFIRMACAO_EMAIL_VALIDADE_MIN
    emails.notificar_confirmacao_email(usuario, codigos.gerar(usuario, CodigoVerificacao.EMAIL, minutos), minutos)
    return True


def reenviar_confirmacao_por_email(email, ip=''):
    """Reenvio pela tela pública: só para conta ainda não confirmada; o chamador responde sempre igual."""
    usuario = usuario_pelo_email(email)
    if usuario and not usuario.perfil.email_verificado:
        enviar_confirmacao(usuario, ip)


def confirmar_com_codigo(email, digitado):
    """Confere o código de confirmação; se certo, consome e confirma. Devolve o usuário ou None."""
    usuario = usuario_pelo_email(email)
    if usuario is None:
        return None
    registro = codigos.conferir(usuario, CodigoVerificacao.EMAIL, digitado)
    if registro is None or not codigos.consumir(registro):
        return None
    confirmar_email(usuario)
    return usuario


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
    """Envia o código de recuperação à conta ativa com esse e-mail.

    O chamador deve responder sempre a mesma coisa, enviando ou não (não revela se a conta existe).
    """
    usuario = usuario_pelo_email(email)
    if usuario is None or not _pedido_permitido('recuperacao', usuario, ip):
        return False
    minutos = settings.CODIGO_RECUPERACAO_VALIDADE_MIN
    emails.notificar_recuperacao_senha(usuario, codigos.gerar(usuario, CodigoVerificacao.SENHA, minutos), minutos)
    return True


def conferir_codigo_de_recuperacao(usuario, digitado):
    return codigos.conferir(usuario, CodigoVerificacao.SENHA, digitado)


def concluir_recuperacao(usuario, registro):
    """Consome o código (uso único), prova o e-mail, libera tentativas de login e avisa o dono."""
    from axes.utils import reset
    if not codigos.consumir(registro):
        return False
    confirmar_email(usuario)  # quem recebeu o código no e-mail comprovou que é dono dele
    reset(username=usuario.username)
    emails.notificar_senha_alterada(usuario)
    return True
