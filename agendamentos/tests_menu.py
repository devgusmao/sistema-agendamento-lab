"""Menu lateral: itens por perfil e item ativo."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import menu
from .tests import criar_usuario


def rotulos(estrutura):
    saida = []
    for entrada in estrutura:
        saida.append(entrada['rotulo'])
        saida.extend(item['rotulo'] for item in entrada.get('itens', []))
    return saida


class EstruturaDoMenuTests(SimpleTestCase):
    def test_aluno_so_ve_os_itens_gerais(self):
        itens = rotulos(menu.montar('home', is_gestor=False, is_admin=False))
        self.assertIn('Painel de Máquinas', itens)
        self.assertIn('Minhas Solicitações', itens)
        self.assertNotIn('Cadastros', itens)
        self.assertNotIn('Administração', itens)

    def test_tecnico_ve_cadastros_mas_nao_administracao(self):
        itens = rotulos(menu.montar('home', is_gestor=True, is_admin=False))
        self.assertIn('Cadastros', itens)
        self.assertIn('Solicitações de Software', itens)
        self.assertNotIn('Administração', itens)
        self.assertNotIn('Dashboard Financeiro', itens)

    def test_admin_ve_tudo(self):
        itens = rotulos(menu.montar('home', is_gestor=True, is_admin=True))
        for esperado in ('Cadastros', 'Máquinas', 'Administração', 'Dashboard Financeiro', 'E-mail (Gmail)'):
            self.assertIn(esperado, itens)

    def test_item_e_grupo_ativos(self):
        estrutura = menu.montar('editar_computador', is_gestor=True, is_admin=True)
        cadastros = next(e for e in estrutura if e['rotulo'] == 'Cadastros')
        self.assertTrue(cadastros['ativo'])
        self.assertEqual([i['rotulo'] for i in cadastros['itens'] if i['ativo']], ['Máquinas'])
        admin = next(e for e in estrutura if e['rotulo'] == 'Administração')
        self.assertFalse(admin['ativo'])
        self.assertFalse(estrutura[0]['ativo'])


class MenuNaTelaTests(TestCase):
    def test_pagina_mostra_menu_e_marca_o_item_atual(self):
        self.client.force_login(criar_usuario('adm_menu', tipo='ADMIN'))
        resp = self.client.get(reverse('dashboard_financeiro'))
        self.assertContains(resp, 'id="sidebar"')
        self.assertContains(resp, 'Dashboard Financeiro')
        self.assertContains(resp, 'aria-current="page"')
        self.assertContains(resp, 'sb-group open has-active')

    def test_aluno_nao_recebe_links_de_gestao(self):
        self.client.force_login(criar_usuario('aluno_menu'))
        resp = self.client.get(reverse('home'))
        self.assertNotContains(resp, reverse('dashboard_financeiro'))
        self.assertNotContains(resp, 'Administração')
        self.assertContains(resp, 'Meus Agendamentos')

    def test_tela_de_login_nao_monta_menu(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.context['menu'], [])
