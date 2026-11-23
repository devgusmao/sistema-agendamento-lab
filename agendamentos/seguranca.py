"""Criptografia de segredos guardados no banco (ex.: senha de app do Gmail).

A chave é derivada da SECRET_KEY: quem tem só o dump do banco não consegue ler
o segredo. Trocar a SECRET_KEY invalida o segredo gravado (será preciso
informá-lo de novo), o que `decifrar` trata devolvendo string vazia.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    chave = hashlib.sha256(f'agendamento-lab:{settings.SECRET_KEY}'.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def cifrar(texto):
    return _fernet().encrypt(texto.encode()).decode() if texto else ''


def decifrar(token):
    if not token:
        return ''
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ''
