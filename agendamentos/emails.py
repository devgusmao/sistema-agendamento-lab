"""Notificações por e-mail (catálogo de eventos, liga/desliga, log e envio).

Nunca derruba a requisição: falha de SMTP é registrada no log e ignorada.
O endereço do destinatário não é gravado em log nem no banco (LGPD).
Credenciais: tela "E-mail" (banco, cifradas) com fallback para o .env.
"""

import logging
from collections import namedtuple

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

Evento = namedtuple('Evento', 'titulo descricao destinatario ativo_padrao')

# Cores por tom: (faixa/borda, fundo do ícone e do aviso, texto do aviso)
TONS = {
    'sucesso': ('#16a34a', '#dcfce7', '#166534'),
    'erro': ('#dc2626', '#fee2e2', '#991b1b'),
    'aviso': ('#d97706', '#fef3c7', '#92400e'),
    'info': ('#2563eb', '#dbeafe', '#1e3a8a'),
}


class Conteudo:
    """Conteúdo de uma notificação; gera o texto simples e o HTML a partir dos mesmos dados."""

    def __init__(self, titulo, icone, tom, paragrafos, detalhes=(), destaque='', botao=None):
        self.titulo, self.icone, self.tom = titulo, icone, tom
        self.paragrafos, self.detalhes, self.destaque = list(paragrafos), list(detalhes), destaque
        self.botao = botao  # (texto, url)

    def texto(self, saudacao):
        partes = [saudacao, '', *self.paragrafos]
        if self.detalhes:
            partes += ['', *(f'{rotulo}: {valor}' for rotulo, valor in self.detalhes)]
        if self.botao:
            partes += ['', f'{self.botao[0]}: {self.botao[1]}']
        if self.destaque:
            partes += ['', self.destaque]
        return '\n'.join(partes) + '\n'

    def html(self, saudacao):
        cor, fundo, texto = TONS[self.tom]
        return render_to_string('agendamentos/emails/mensagem.html', {
            'titulo': self.titulo, 'icone': self.icone, 'saudacao': saudacao,
            'paragrafos': self.paragrafos, 'detalhes': self.detalhes, 'destaque': self.destaque, 'botao': self.botao,
            'resumo': self.paragrafos[0] if self.paragrafos else self.titulo,
            'cor': cor, 'cor_fundo': fundo, 'cor_texto': texto,
        })

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
    'reserva_nova_admin': Evento(
        'Nova reserva (aviso à administração)',
        'Avisa os administradores a cada reserva feita por outro usuário, com máquina, horário e valor.',
        'Todos os administradores', True),
    'reserva_cancelada_propria': Evento(
        'Cancelamento confirmado ao usuário',
        'Enviado ao usuário quando ele mesmo cancela uma reserva, com a multa aplicada, se houver.',
        'Quem cancelou', True),
    'reserva_cancelada_admin': Evento(
        'Cancelamento feito pelo usuário (aviso à administração)',
        'Avisa os administradores quando um usuário cancela a própria reserva, com a multa a cobrar.',
        'Todos os administradores', True),
    'lembrete_reserva': Evento(
        'Lembrete de reserva',
        'Enviado algumas horas antes do início da reserva (configurável, padrão 2 h). '
        'Exige agendar o comando "enviar_lembretes" no servidor.',
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


# Avisos de segurança da conta: sempre enviados, não aparecem para liga/desliga.
EVENTOS_SEGURANCA = {
    'confirmar_email': 'Confirmação de e-mail',
    'recuperar_senha': 'Recuperação de senha',
    'senha_alterada': 'Senha alterada pelo próprio usuário',
}


def evento_ativo(slug):
    from .models import ConfiguracaoNotificacao
    if slug in EVENTOS_SEGURANCA:
        return True
    cfg = ConfiguracaoNotificacao.objects.filter(evento=slug).first()
    return EVENTOS[slug].ativo_padrao if cfg is None else cfg.ativo


def _fmt(dt):
    return timezone.localtime(dt).strftime('%d/%m/%Y %H:%M')


def _nome(usuario):
    return usuario.first_name or usuario.username


def _saudacao(usuario):
    return f'Olá, {_nome(usuario)}!'


def _moeda(valor):
    return 'R$ ' + f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _maquina(ag):
    return f'{ag.computador.identificador} ({ag.computador.laboratorio.nome})'


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


def _enviar_agora(email, assunto, conteudo, saudacao='Olá!'):
    """Envia de verdade (texto + HTML). Devolve '' se deu certo ou o nome da exceção."""
    try:
        remetente, conexao = _remetente_e_conexao()
        mensagem = EmailMultiAlternatives(
            f'[Agendamento Lab] {assunto}', conteudo.texto(saudacao), remetente, [email], connection=conexao,
        )
        mensagem.attach_alternative(conteudo.html(saudacao), 'text/html')
        mensagem.send()
        return ''
    except Exception as exc:
        logger.exception('Falha ao enviar e-mail "%s"', assunto)
        return type(exc).__name__


def enviar(evento, usuario, assunto, conteudo):
    """Aplica liga/desliga, envia após o commit e registra o resultado no log."""
    from .models import LogNotificacao

    ativo = evento_ativo(evento)
    email = usuario.email
    saudacao = _saudacao(usuario)

    def _executar():
        if not ativo:
            status, erro = 'DESATIVADO', ''
        elif not email:
            status, erro = 'SEM_EMAIL', ''
        else:
            erro = _enviar_agora(email, assunto, conteudo, saudacao)
            status = 'FALHA' if erro else 'ENVIADO'
        LogNotificacao.objects.create(evento=evento, usuario=usuario, status=status, erro=erro)

    transaction.on_commit(_executar)


def enviar_teste(destino):
    """Envio síncrono para a tela de configuração. Devolve (ok, erro)."""
    erro = _enviar_agora(destino, 'Teste de e-mail', Conteudo(
        'Teste de e-mail', '✅', 'sucesso',
        ['Se você recebeu esta mensagem, o envio de e-mails do LabManager está funcionando.'],
        destaque='Você pode fechar esta mensagem: nenhuma ação é necessária.',
    ))
    return (not erro), erro


def _administradores():
    return User.objects.filter(Q(is_superuser=True) | Q(perfil__tipo='ADMIN', perfil__aprovado=True)).distinct()


def _gestores():
    return User.objects.filter(
        Q(is_superuser=True) | Q(perfil__tipo__in=['ADMIN', 'TECNICO'], perfil__aprovado=True)
    ).distinct()


# --- Reservas ---

def notificar_reserva_confirmada(ag):
    enviar('reserva_confirmada', ag.usuario, 'Reserva confirmada', Conteudo(
        'Reserva confirmada', '✅', 'sucesso',
        ['Sua reserva foi confirmada. Confira os detalhes abaixo.'],
        detalhes=[
            ('Máquina', _maquina(ag)),
            ('Início', _fmt(ag.data_hora_inicio)),
            ('Término', _fmt(ag.data_hora_fim)),
            ('Valor', _moeda(ag.valor_total)),
        ],
        destaque=(
            'Cancelamentos feitos com menos de '
            f'{settings.AGENDAMENTO_MULTA_HORAS} h de antecedência podem gerar multa de '
            f'{settings.AGENDAMENTO_MULTA_PERCENTUAL}% do valor.'
        ) if ag.valor_total and ag.valor_total > 0 else '',
    ))


def notificar_reserva_cancelada(ag, motivo=''):
    enviar('reserva_cancelada', ag.usuario, 'Reserva cancelada', Conteudo(
        'Reserva cancelada', '❌', 'erro',
        ['Sua reserva foi cancelada.'],
        detalhes=[
            ('Máquina', _maquina(ag)),
            ('Início', _fmt(ag.data_hora_inicio)),
            *([('Motivo', motivo)] if motivo else []),
        ],
        destaque='Se precisar, faça uma nova reserva em outro horário ou máquina.',
    ))


def notificar_nova_reserva_admins(ag):
    """Avisa os administradores de uma reserva nova (quem reservou não recebe o aviso duas vezes)."""
    for admin in _administradores().exclude(pk=ag.usuario_id):
        enviar('reserva_nova_admin', admin, 'Nova reserva registrada', Conteudo(
            'Nova reserva registrada', '📅', 'info',
            [f'{_nome(ag.usuario)} fez uma nova reserva.'],
            detalhes=[
                ('Usuário', ag.usuario.username),
                ('Máquina', _maquina(ag)),
                ('Início', _fmt(ag.data_hora_inicio)),
                ('Término', _fmt(ag.data_hora_fim)),
                ('Valor', _moeda(ag.valor_total)),
            ],
        ))


def notificar_cancelamento_pelo_dono(ag):
    """O usuário cancelou a própria reserva: confirma a ele e avisa os administradores."""
    multa = ag.multa or 0
    detalhes = [('Máquina', _maquina(ag)), ('Início', _fmt(ag.data_hora_inicio))]
    if multa > 0:
        detalhes.append(('Multa', _moeda(multa)))
    enviar('reserva_cancelada_propria', ag.usuario, 'Cancelamento confirmado', Conteudo(
        'Cancelamento confirmado', '❌', 'aviso' if multa > 0 else 'sucesso',
        ['Sua reserva foi cancelada.'],
        detalhes=detalhes,
        destaque=(
            f'Como o cancelamento foi feito com menos de {settings.AGENDAMENTO_MULTA_HORAS} h de antecedência, '
            f'foi aplicada multa de {_moeda(multa)}. O pagamento é registrado pela administração.'
        ) if multa > 0 else 'Cancelamento dentro do prazo: nenhuma multa foi aplicada.',
    ))
    for admin in _administradores().exclude(pk=ag.usuario_id):
        enviar('reserva_cancelada_admin', admin, 'Reserva cancelada pelo usuário', Conteudo(
            'Reserva cancelada pelo usuário', '❌', 'aviso' if multa > 0 else 'info',
            [f'{_nome(ag.usuario)} cancelou a própria reserva.'],
            detalhes=[('Usuário', ag.usuario.username), *detalhes],
            destaque=f'Há multa de {_moeda(multa)} a cobrar.' if multa > 0 else '',
        ))


def notificar_lembrete_reserva(ag):
    enviar('lembrete_reserva', ag.usuario, 'Lembrete da sua reserva', Conteudo(
        'Sua reserva começa em breve', '⏰', 'aviso',
        ['Este é um lembrete da sua reserva.'],
        detalhes=[
            ('Máquina', _maquina(ag)),
            ('Início', _fmt(ag.data_hora_inicio)),
            ('Término', _fmt(ag.data_hora_fim)),
        ],
    ))


# --- Usuários ---

def notificar_novo_cadastro(novo):
    for admin in _administradores():
        enviar('novo_cadastro', admin, 'Novo cadastro aguardando aprovação', Conteudo(
            'Novo cadastro aguardando aprovação', '👤', 'info',
            ['Uma pessoa se cadastrou e aguarda a liberação do acesso.'],
            detalhes=[('Usuário', novo.username)],
            destaque='Libere em Administração > Aprovar Usuários.',
        ))


def notificar_cadastro_aprovado(usuario):
    enviar('cadastro_aprovado', usuario, 'Seu acesso foi liberado', Conteudo(
        'Seu acesso foi liberado', '🎉', 'sucesso',
        ['Seu cadastro foi aprovado. Você já pode entrar no sistema e fazer reservas.'],
    ))


def notificar_acesso_revogado(usuario):
    enviar('acesso_revogado', usuario, 'Seu acesso foi suspenso', Conteudo(
        'Seu acesso foi suspenso', '🔒', 'erro',
        ['Seu acesso ao sistema foi suspenso por um administrador.'],
        destaque='Em caso de dúvida, procure a gestão do laboratório.',
    ))


def notificar_senha_redefinida(usuario):
    enviar('senha_redefinida', usuario, 'Sua senha foi redefinida', Conteudo(
        'Sua senha foi redefinida', '🔑', 'aviso',
        ['Sua senha foi redefinida por um administrador. A nova senha será informada a você por outro canal.'],
        destaque='Se você não esperava isso, avise a gestão do laboratório.',
    ))


# --- Solicitações de software ---

def notificar_solicitacao_nova(sol):
    for gestor in _gestores().exclude(pk=sol.usuario_id):
        enviar('solicitacao_nova', gestor, 'Nova solicitação de software', Conteudo(
            'Nova solicitação de software', '🛠️', 'info',
            ['Chegou um novo pedido de instalação de software.'],
            detalhes=[('Software', sol.software_nome), ('Destino', sol.destino_display())],
        ))


_TOM_SOLICITACAO = {'CONCLUIDO': ('✅', 'sucesso'), 'REJEITADO': ('❌', 'erro'), 'EM_ANDAMENTO': ('⏳', 'info')}


def notificar_solicitacao_atualizada(sol):
    icone, tom = _TOM_SOLICITACAO.get(sol.status, ('🛠️', 'info'))
    enviar('solicitacao_atualizada', sol.usuario, f'Solicitação {sol.get_status_display().lower()}', Conteudo(
        f'Solicitação {sol.get_status_display().lower()}', icone, tom,
        ['O andamento da sua solicitação de software mudou.'],
        detalhes=[
            ('Software', sol.software_nome),
            ('Destino', sol.destino_display()),
            ('Situação', sol.get_status_display()),
        ],
    ))


# --- Segurança da conta (links com token) ---

def notificar_confirmacao_email(usuario, url, validade_horas):
    enviar('confirmar_email', usuario, 'Confirme seu e-mail', Conteudo(
        'Confirme seu e-mail', '✉️', 'info',
        [
            'Recebemos seu cadastro no LabManager. Para continuar, confirme que este e-mail é seu.',
            'Depois da confirmação, um administrador precisa liberar o seu acesso.',
        ],
        detalhes=[('Usuário', usuario.username), ('Validade do link', f'{validade_horas} horas')],
        destaque='Se você não fez este cadastro, ignore esta mensagem: nada será ativado.',
        botao=('Confirmar meu e-mail', url),
    ))


def notificar_recuperacao_senha(usuario, url, validade_min):
    enviar('recuperar_senha', usuario, 'Recuperação de senha', Conteudo(
        'Recuperação de senha', '🔑', 'aviso',
        ['Recebemos um pedido para criar uma nova senha para a sua conta.'],
        detalhes=[('Usuário', usuario.username), ('Validade do link', f'{validade_min} minutos'), ('Uso', 'Link de uso único')],
        destaque=(
            'Se você não pediu esta recuperação, ignore esta mensagem: sua senha continua a mesma. '
            'Nunca compartilhe este link com ninguém.'
        ),
        botao=('Criar nova senha', url),
    ))


def notificar_senha_alterada(usuario):
    enviar('senha_alterada', usuario, 'Sua senha foi alterada', Conteudo(
        'Sua senha foi alterada', '🔒', 'sucesso',
        ['A senha da sua conta acabou de ser alterada pelo link de recuperação.'],
        detalhes=[('Usuário', usuario.username)],
        destaque='Se não foi você, procure a gestão do laboratório imediatamente.',
    ))
