"""Notificações por e-mail (catálogo de eventos, liga/desliga, log e envio).

Nunca derruba a requisição: falha de SMTP é registrada no log e ignorada.
O endereço do destinatário não é gravado em log nem no banco (LGPD).
Credenciais: tela "E-mail" (banco, cifradas) com fallback para o .env.
"""

import logging
from collections import namedtuple

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

Evento = namedtuple('Evento', 'titulo descricao destinatario ativo_padrao')

# Catálogo exibido na tela "Notificações". A chave é gravada no banco: não renomear.
EVENTOS = {
    'reserva_confirmada': Evento(
        'Reserva confirmada',
        'Enviado logo após o usuário concluir uma reserva, com máquina, horário e valor.',
        'Quem fez a reserva', True),
    'reserva_cancelada': Evento(
        'Reserva cancelada pela administração',
        'Enviado quando um administrador cancela a reserva de outra pessoa ou quando a máquina '
        'entra em manutenção/inativa e as reservas futuras são canceladas.',
        'Dono da reserva', True),
    'lembrete_reserva': Evento(
        'Lembrete de reserva',
        f'Enviado algumas horas antes do início da reserva (configurável, padrão 2 h). '
        f'Exige agendar o comando "enviar_lembretes" no servidor.',
        'Dono da reserva', True),
    'novo_cadastro': Evento(
        'Novo cadastro aguardando aprovação',
        'Avisa a equipe quando alguém se cadastra e precisa ser liberado.',
        'Todos os administradores', True),
    'cadastro_aprovado': Evento(
        'Cadastro aprovado',
        'Avisa a pessoa de que o acesso foi liberado e ela já pode entrar.',
        'Usuário aprovado', True),
    'acesso_revogado': Evento(
        'Acesso revogado',
        'Avisa a pessoa de que o acesso foi suspenso por um administrador.',
        'Usuário revogado', True),
    'senha_redefinida': Evento(
        'Senha redefinida por administrador',
        'Alerta de segurança: a senha foi trocada por um administrador (a nova senha nunca vai no e-mail).',
        'Usuário afetado', True),
    'solicitacao_nova': Evento(
        'Nova solicitação de software',
        'Avisa a equipe técnica e os administradores quando chega um pedido de instalação.',
        'Técnicos e administradores', True),
    'solicitacao_atualizada': Evento(
        'Solicitação de software atualizada',
        'Enviado quando o pedido passa para Em andamento, Concluído ou Rejeitado.',
        'Quem fez a solicitação', True),
}


def evento_ativo(slug):
    from .models import ConfiguracaoNotificacao
    cfg = ConfiguracaoNotificacao.objects.filter(evento=slug).first()
    return EVENTOS[slug].ativo_padrao if cfg is None else cfg.ativo


def _fmt(dt):
    return timezone.localtime(dt).strftime('%d/%m/%Y %H:%M')


def _nome(usuario):
    return usuario.first_name or usuario.username


def _remetente_e_conexao():
    from .models import ConfiguracaoEmail
    cfg = ConfiguracaoEmail.obter()
    if cfg.configurada:
        conexao = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=cfg.host, port=cfg.porta, username=cfg.usuario, password=cfg.senha,
            use_tls=cfg.usar_tls, timeout=settings.EMAIL_TIMEOUT,
        )
        remetente = f'{cfg.nome_remetente} <{cfg.usuario}>' if cfg.nome_remetente else cfg.usuario
        return remetente, conexao
    return settings.DEFAULT_FROM_EMAIL, get_connection()


def _enviar_agora(email, assunto, mensagem):
    """Envia de verdade. Devolve '' se deu certo ou o nome da exceção."""
    try:
        remetente, conexao = _remetente_e_conexao()
        EmailMessage(f'[Agendamento Lab] {assunto}', mensagem, remetente, [email], connection=conexao).send()
        return ''
    except Exception as exc:
        logger.exception('Falha ao enviar e-mail "%s"', assunto)
        return type(exc).__name__


def enviar(evento, usuario, assunto, mensagem):
    """Aplica liga/desliga, envia após o commit e registra o resultado no log."""
    from .models import LogNotificacao

    ativo = evento_ativo(evento)
    email = usuario.email

    def _executar():
        if not ativo:
            status, erro = 'DESATIVADO', ''
        elif not email:
            status, erro = 'SEM_EMAIL', ''
        else:
            erro = _enviar_agora(email, assunto, mensagem)
            status = 'FALHA' if erro else 'ENVIADO'
        LogNotificacao.objects.create(evento=evento, usuario=usuario, status=status, erro=erro)

    transaction.on_commit(_executar)


def enviar_teste(destino):
    """Envio síncrono para a tela de configuração. Devolve (ok, erro)."""
    erro = _enviar_agora(destino, 'Teste de e-mail', 'Se você recebeu esta mensagem, o envio está funcionando.')
    return (not erro), erro


def _administradores():
    return User.objects.filter(Q(is_superuser=True) | Q(perfil__tipo='ADMIN', perfil__aprovado=True)).distinct()


def _gestores():
    return User.objects.filter(
        Q(is_superuser=True) | Q(perfil__tipo__in=['ADMIN', 'TECNICO'], perfil__aprovado=True)
    ).distinct()


# --- Reservas ---

def notificar_reserva_confirmada(ag):
    enviar('reserva_confirmada', ag.usuario, 'Reserva confirmada', (
        f'Olá, {_nome(ag.usuario)}!\n\n'
        f'Sua reserva foi confirmada:\n'
        f'Máquina: {ag.computador.identificador} ({ag.computador.laboratorio.nome})\n'
        f'Início: {_fmt(ag.data_hora_inicio)}\n'
        f'Fim: {_fmt(ag.data_hora_fim)}\n'
        f'Valor: R$ {ag.valor_total}\n'
    ))


def notificar_reserva_cancelada(ag, motivo=''):
    enviar('reserva_cancelada', ag.usuario, 'Reserva cancelada', (
        f'Olá, {_nome(ag.usuario)}!\n\n'
        f'Sua reserva da máquina {ag.computador.identificador} '
        f'({ag.computador.laboratorio.nome}) em {_fmt(ag.data_hora_inicio)} foi cancelada.\n'
        + (f'Motivo: {motivo}\n' if motivo else '')
    ))


def notificar_lembrete_reserva(ag):
    enviar('lembrete_reserva', ag.usuario, 'Lembrete da sua reserva', (
        f'Olá, {_nome(ag.usuario)}!\n\n'
        f'Sua reserva começa em breve:\n'
        f'Máquina: {ag.computador.identificador} ({ag.computador.laboratorio.nome})\n'
        f'Início: {_fmt(ag.data_hora_inicio)}\n'
        f'Fim: {_fmt(ag.data_hora_fim)}\n'
    ))


# --- Usuários ---

def notificar_novo_cadastro(novo):
    for admin in _administradores():
        enviar('novo_cadastro', admin, 'Novo cadastro aguardando aprovação', (
            f'Olá, {_nome(admin)}!\n\n'
            f'O usuário "{novo.username}" se cadastrou e aguarda liberação em '
            f'Gestão > Aprovar Usuários.\n'
        ))


def notificar_cadastro_aprovado(usuario):
    enviar('cadastro_aprovado', usuario, 'Seu acesso foi liberado', (
        f'Olá, {_nome(usuario)}!\n\nSeu cadastro foi aprovado. Você já pode entrar e fazer reservas.\n'
    ))


def notificar_acesso_revogado(usuario):
    enviar('acesso_revogado', usuario, 'Seu acesso foi suspenso', (
        f'Olá, {_nome(usuario)}!\n\nSeu acesso ao sistema foi suspenso por um administrador. '
        f'Em caso de dúvida, procure a gestão do laboratório.\n'
    ))


def notificar_senha_redefinida(usuario):
    enviar('senha_redefinida', usuario, 'Sua senha foi redefinida', (
        f'Olá, {_nome(usuario)}!\n\nSua senha foi redefinida por um administrador. '
        f'A nova senha será informada a você por outro canal. '
        f'Se você não esperava isso, avise a gestão do laboratório.\n'
    ))


# --- Solicitações de software ---

def notificar_solicitacao_nova(sol):
    for gestor in _gestores().exclude(pk=sol.usuario_id):
        enviar('solicitacao_nova', gestor, 'Nova solicitação de software', (
            f'Olá, {_nome(gestor)}!\n\n'
            f'Nova solicitação: {sol.software_nome}\nDestino: {sol.destino_display()}\n'
        ))


def notificar_solicitacao_atualizada(sol):
    enviar('solicitacao_atualizada', sol.usuario, f'Solicitação {sol.get_status_display().lower()}', (
        f'Olá, {_nome(sol.usuario)}!\n\n'
        f'Sua solicitação de "{sol.software_nome}" ({sol.destino_display()}) '
        f'agora está: {sol.get_status_display()}.\n'
    ))
