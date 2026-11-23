"""Estrutura do menu lateral, por perfil.

Cada entrada é um link ou um grupo (que abre um submenu). `ativos` lista os nomes
de URL que mantêm o item marcado (ex.: editar e listar máquinas marcam "Máquinas").
"""

from django.urls import reverse


def _link(rotulo, icone, url_name, ativos=None):
    return {'rotulo': rotulo, 'icone': icone, 'url': reverse(url_name), 'ativos': tuple(ativos or (url_name,))}


def _grupo(rotulo, icone, itens):
    return {'rotulo': rotulo, 'icone': icone, 'itens': itens}


def estrutura(is_gestor, is_admin):
    menu = [
        _link('Painel de Máquinas', 'home', 'home', ('home', 'criar_agendamento')),
        _link('Meus Agendamentos', 'calendario', 'meus_agendamentos'),
        _link(
            'Solicitações de Software' if is_gestor else 'Minhas Solicitações',
            'caixa', 'listar_solicitacoes',
        ),
        _link('Solicitar Software', 'ferramenta', 'criar_solicitacao_global',
              ('criar_solicitacao_global', 'criar_solicitacao_instalacao')),
        _link('Alterar Senha', 'cadeado', 'alterar_senha'),
    ]
    if is_gestor:
        menu.append(_grupo('Cadastros', 'predio', [
            _link('Laboratórios', 'predio', 'listar_laboratorios',
                  ('listar_laboratorios', 'cadastrar_laboratorio', 'editar_laboratorio')),
            _link('Máquinas', 'computador', 'listar_computadores',
                  ('listar_computadores', 'cadastrar_computador', 'editar_computador')),
            _link('Inventário de Softwares', 'engrenagem', 'listar_softwares'),
        ]))
    if is_admin:
        menu.append(_grupo('Administração', 'escudo', [
            _link('Todas as Reservas', 'lista', 'gerenciar_agendamentos'),
            _link('Dashboard Financeiro', 'grafico', 'dashboard_financeiro'),
            _link('Tipos e Preços', 'etiqueta', 'listar_tipos_agendamento',
                  ('listar_tipos_agendamento', 'cadastrar_tipo_agendamento', 'editar_tipo_agendamento')),
            _link('Aprovar Usuários', 'chave', 'liberar_usuarios'),
            _link('Gerenciar Usuários', 'usuarios', 'gerenciar_usuarios',
                  ('gerenciar_usuarios', 'editar_usuario', 'resetar_senha_usuario')),
            _link('Notificações', 'sino', 'notificacoes'),
            _link('E-mail (Gmail)', 'email', 'configurar_email'),
        ]))
    return menu


def marcar_ativo(menu, url_name):
    """Devolve o menu com `ativo` em cada link e `ativo` no grupo que contém o link ativo."""
    for entrada in menu:
        if 'itens' in entrada:
            for item in entrada['itens']:
                item['ativo'] = url_name in item['ativos']
            entrada['ativo'] = any(item['ativo'] for item in entrada['itens'])
        else:
            entrada['ativo'] = url_name in entrada['ativos']
    return menu


def montar(url_name, is_gestor, is_admin):
    return marcar_ativo(estrutura(is_gestor, is_admin), url_name)
