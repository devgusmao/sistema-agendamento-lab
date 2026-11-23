"""Confirmação de e-mail no cadastro e recuperação de senha pelo link do e-mail."""

import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail, signing
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import LimiteSolicitacao, Perfil
from .servicos import contas
from .tests import criar_usuario

SENHA_NOVA = 'Nova-Senha-Forte-987'


def entrar(cliente, username, senha):
    """Login real pela tela (o `client.login` do Django não funciona com o django-axes)."""
    cliente.post(reverse('login'), {'username': username, 'password': senha})
    return '_auth_user_id' in cliente.session


def link_do_email(mensagem):
    """Caminho (sem domínio) do primeiro link do e-mail, a partir do texto simples."""
    return re.search(r'https?://[^\s]+?(/conta/[^\s]+)', mensagem.body).group(1)


class CadastroComConfirmacaoTests(TestCase):
    def setUp(self):
        self.admin = criar_usuario('adm_c', tipo='ADMIN', email='adm@example.com')

    def _cadastrar(self, username='novato', email='novato@example.com'):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('cadastrar'), {
                'username': username, 'email': email,
                'password1': 'Senha-Forte-123', 'password2': 'Senha-Forte-123',
            })

    def test_cadastro_envia_link_so_ao_novo_usuario(self):
        self._cadastrar()
        perfil = Perfil.objects.get(usuario__username='novato')
        self.assertFalse(perfil.email_verificado)
        self.assertFalse(perfil.aprovado)
        self.assertEqual([m.to for m in mail.outbox], [['novato@example.com']])
        self.assertIn('/conta/confirmar-email/', mail.outbox[0].body)
        self.assertIn('Confirmar meu e-mail', mail.outbox[0].alternatives[0][0])

    def test_confirmar_avisa_os_administradores_uma_unica_vez(self):
        self._cadastrar()
        caminho = link_do_email(mail.outbox[0])
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.get(caminho)
        self.assertContains(resp, 'E-mail confirmado')
        self.assertTrue(Perfil.objects.get(usuario__username='novato').email_verificado)
        self.assertEqual([m.to for m in mail.outbox], [['adm@example.com']])
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.get(caminho)  # clicar de novo (ou um antivírus que abre o link) não repete o aviso
        self.assertEqual(mail.outbox, [])

    def test_confirmar_nao_libera_o_acesso(self):
        self._cadastrar()
        self.client.get(link_do_email(mail.outbox[0]))
        entrar(self.client, 'novato', 'Senha-Forte-123')
        resp = self.client.get(reverse('home'))
        self.assertEqual(resp.status_code, 403)  # ainda falta a aprovação do administrador
        self.assertContains(resp, 'Cadastro pendente de liberação', status_code=403)

    def test_aprovado_mas_sem_confirmar_o_email_nao_entra(self):
        self._cadastrar()
        Perfil.objects.filter(usuario__username='novato').update(aprovado=True)
        entrar(self.client, 'novato', 'Senha-Forte-123')
        resp = self.client.get(reverse('home'))
        self.assertContains(resp, 'Confirme o seu e-mail', status_code=403)

    def test_aprovado_e_confirmado_entra(self):
        self._cadastrar()
        self.client.get(link_do_email(mail.outbox[0]))
        Perfil.objects.filter(usuario__username='novato').update(aprovado=True)
        entrar(self.client, 'novato', 'Senha-Forte-123')
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_token_adulterado_ou_invalido(self):
        self.assertEqual(self.client.get(reverse('confirmar_email', args=['lixo'])).status_code, 400)
        usuario = criar_usuario('u1', email='u1@example.com')
        token = contas.gerar_token_confirmacao(usuario) + 'x'
        self.assertEqual(self.client.get(reverse('confirmar_email', args=[token])).status_code, 400)

    def test_token_expira(self):
        usuario = criar_usuario('u2', email='u2@example.com')
        token = contas.gerar_token_confirmacao(usuario)
        futuro = timezone.now().timestamp() + 25 * 3600
        with mock.patch('django.core.signing.time.time', return_value=futuro):
            self.assertIsNone(contas.usuario_do_token_de_confirmacao(token))
        self.assertEqual(contas.usuario_do_token_de_confirmacao(token), usuario)

    def test_token_vale_so_para_o_email_atual(self):
        usuario = criar_usuario('u3', email='velho@example.com')
        token = contas.gerar_token_confirmacao(usuario)
        usuario.email = 'novo@example.com'
        usuario.save()
        self.assertIsNone(contas.usuario_do_token_de_confirmacao(token))

    def test_token_de_outro_proposito_nao_serve(self):
        usuario = criar_usuario('u4', email='u4@example.com')
        falso = signing.dumps({'u': usuario.pk, 'e': usuario.email}, salt='outro-uso')
        self.assertIsNone(contas.usuario_do_token_de_confirmacao(falso))

    def test_reenvio_so_para_logado_pendente_e_com_limite(self):
        self._cadastrar()
        mail.outbox.clear()
        self.assertEqual(self.client.post(reverse('reenviar_confirmacao')).status_code, 302)  # anônimo
        self.assertEqual(mail.outbox, [])
        entrar(self.client, 'novato', 'Senha-Forte-123')
        for _ in range(5):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('reenviar_confirmacao'))
        # 1 do cadastro + 2 reenvios = limite de 3 por hora por usuário
        self.assertEqual(len(mail.outbox), 2)

    def test_reenvio_exige_post(self):
        self._cadastrar()
        entrar(self.client, 'novato', 'Senha-Forte-123')
        self.assertEqual(self.client.get(reverse('reenviar_confirmacao')).status_code, 405)

    def test_usuarios_existentes_continuam_confirmados(self):
        self.assertTrue(Perfil.objects.get(usuario=self.admin).email_verificado)

    def test_lista_de_aprovacao_mostra_se_o_email_foi_confirmado(self):
        self._cadastrar()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('liberar_usuarios')), 'e-mail ainda não confirmado')


class EsqueciSenhaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.usuario = criar_usuario('maria', email='maria@example.com')

    def _pedir(self, email, **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('esqueci_senha'), {'email': email}, **extra)

    def test_login_tem_link_de_esqueci_a_senha(self):
        self.assertContains(self.client.get(reverse('login')), reverse('esqueci_senha'))

    def test_envia_link_para_conta_existente(self):
        resp = self._pedir('maria@example.com')
        self.assertRedirects(resp, reverse('login'))
        self.assertEqual([m.to for m in mail.outbox], [['maria@example.com']])
        self.assertIn('/conta/redefinir-senha/', mail.outbox[0].body)
        self.assertIn('Criar nova senha', mail.outbox[0].alternatives[0][0])

    def test_resposta_identica_para_conta_inexistente(self):
        existente = self._pedir('maria@example.com')
        inexistente = self._pedir('ninguem@example.com')
        self.assertEqual(existente.status_code, inexistente.status_code)
        self.assertEqual(existente.url, inexistente.url)
        msgs = [str(m) for m in self.client.get(reverse('login')).context['messages']]
        self.assertEqual(len(mail.outbox), 1)  # só a conta existente recebeu
        self.assertTrue(all('Se este e-mail estiver cadastrado' in m for m in msgs))

    def test_email_em_maiusculas_funciona(self):
        self._pedir('MARIA@Example.com')
        self.assertEqual(len(mail.outbox), 1)

    def test_conta_inativa_nao_recebe(self):
        User.objects.filter(pk=self.usuario.pk).update(is_active=False)
        self._pedir('maria@example.com')
        self.assertEqual(mail.outbox, [])

    def test_limite_por_usuario(self):
        for _ in range(6):
            self._pedir('maria@example.com')
        self.assertEqual(len(mail.outbox), 3)

    def test_limite_por_ip_vale_para_qualquer_email(self):
        for i in range(15):
            criar_usuario(f'u{i}', email=f'u{i}@example.com')
        for i in range(15):
            self._pedir(f'u{i}@example.com')
        self.assertEqual(len(mail.outbox), 10)

    def test_limite_libera_depois_da_janela(self):
        for _ in range(3):
            self._pedir('maria@example.com')
        LimiteSolicitacao.objects.update(criado_em=timezone.now() - timedelta(hours=2))
        mail.outbox.clear()
        self._pedir('maria@example.com')
        self.assertEqual(len(mail.outbox), 1)

    def test_email_invalido_nao_envia(self):
        resp = self.client.post(reverse('esqueci_senha'), {'email': 'isso-nao-e-email'})
        self.assertContains(resp, 'Informe um e-mail válido')
        self.assertEqual(mail.outbox, [])

    def test_usuario_logado_vai_para_alterar_senha(self):
        self.client.force_login(self.usuario)
        self.assertRedirects(self.client.get(reverse('esqueci_senha')), reverse('alterar_senha'))


class RedefinirSenhaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.usuario = criar_usuario('joao', email='joao@example.com')
        self.admin = criar_usuario('adm_r', tipo='ADMIN', email='adm@example.com')

    def _link(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('esqueci_senha'), {'email': 'joao@example.com'})
        caminho = link_do_email(mail.outbox[-1])
        mail.outbox.clear()
        return caminho

    def _abrir(self, caminho):
        """Abre o link do e-mail e segue o redirecionamento que tira o token da URL."""
        resp = self.client.get(caminho)
        return self.client.get(resp.url) if resp.status_code == 302 else resp

    def _trocar(self, caminho, senha=SENHA_NOVA, confirmar=None):
        tela = self.client.get(self.client.get(caminho).url)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(tela.request['PATH_INFO'], {
                'new_password1': senha, 'new_password2': confirmar or senha,
            })

    def test_fluxo_completo_e_login_com_a_nova_senha(self):
        caminho = self._link()
        self.assertContains(self._abrir(caminho), 'Criar nova senha')
        resp = self._trocar(caminho)
        self.assertRedirects(resp, reverse('login'))
        self.assertFalse(entrar(self.client, 'joao', 'senha-de-teste-123'))
        self.assertTrue(entrar(self.client, 'joao', SENHA_NOVA))

    def test_token_sai_da_url_depois_do_primeiro_acesso(self):
        caminho = self._link()
        resp = self.client.get(caminho)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.endswith('/definir-senha/'))
        self.assertNotIn(caminho.split('/')[-2], resp.url)

    def test_link_de_uso_unico(self):
        caminho = self._link()
        self._trocar(caminho)
        self.client.logout()
        resp = self.client.get(caminho)
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, 'Link inválido ou expirado', status_code=400)

    def test_link_expira(self):
        caminho = self._link()
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            resp = self.client.get(caminho)
        self.assertEqual(resp.status_code, 400)

    def test_novo_pedido_nao_e_afetado_pelo_antigo_apos_uso(self):
        caminho = self._link()
        self._trocar(caminho)
        self.assertEqual(self.client.get(caminho).status_code, 400)

    def test_token_adulterado_e_uid_invalido(self):
        caminho = self._link()
        self.assertEqual(self.client.get(caminho[:-2] + 'x/').status_code, 400)
        self.assertEqual(self.client.get('/conta/redefinir-senha/zzz/abc-123/').status_code, 400)

    def test_nao_aceita_definir_senha_sem_passar_pelo_link(self):
        uid = self._link().split('/')[-3]
        resp = self.client.post(reverse('redefinir_senha', args=[uid, 'definir-senha']), {
            'new_password1': SENHA_NOVA, 'new_password2': SENHA_NOVA,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(entrar(self.client, 'joao', 'senha-de-teste-123'))

    def test_senha_fraca_ou_diferente_e_recusada(self):
        caminho = self._link()
        fraca = self._trocar(caminho, senha='12345678')
        self.assertEqual(fraca.status_code, 200)
        diferente = self._trocar(caminho, senha=SENHA_NOVA, confirmar='Outra-Senha-123')
        self.assertEqual(diferente.status_code, 200)
        self.assertTrue(entrar(self.client, 'joao', 'senha-de-teste-123'))

    def test_trocar_senha_invalida_sessoes_abertas(self):
        outro = self.client_class()
        outro.force_login(self.usuario)
        self.assertEqual(outro.get(reverse('home')).status_code, 200)
        self._trocar(self._link())
        self.assertEqual(outro.get(reverse('home')).status_code, 302)  # sessão antiga caiu

    def test_envia_alerta_de_senha_alterada(self):
        self._trocar(self._link())
        self.assertEqual([m.to for m in mail.outbox], [['joao@example.com']])
        self.assertIn('alterada', mail.outbox[0].subject.lower())
        self.assertNotIn(SENHA_NOVA, mail.outbox[0].body)

    def test_libera_login_travado_por_tentativas(self):
        from axes.models import AccessAttempt
        AccessAttempt.objects.create(username='joao', ip_address='127.0.0.1', failures_since_start=5)
        self._trocar(self._link())
        self.assertFalse(AccessAttempt.objects.filter(username='joao').exists())

    def test_usuario_aprovado_continua_aprovado_sem_novo_aval(self):
        self._trocar(self._link())
        entrar(self.client, 'joao', SENHA_NOVA)
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_conta_nova_continua_exigindo_aprovacao(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cadastrar'), {
                'username': 'novata', 'email': 'novata@example.com',
                'password1': 'Senha-Forte-123', 'password2': 'Senha-Forte-123',
            })
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('esqueci_senha'), {'email': 'novata@example.com'})
        caminho = link_do_email(mail.outbox[-1])
        mail.outbox.clear()
        self._trocar(caminho)
        perfil = Perfil.objects.get(usuario__username='novata')
        self.assertTrue(perfil.email_verificado)   # abriu o link no e-mail: comprovou que é dono
        self.assertFalse(perfil.aprovado)          # mas o administrador ainda precisa liberar
        entrar(self.client, 'novata', SENHA_NOVA)
        self.assertEqual(self.client.get(reverse('home')).status_code, 403)
        # o administrador foi avisado do cadastro (e o usuário recebeu o alerta de senha alterada)
        self.assertIn(['adm@example.com'], [m.to for m in mail.outbox])

    def test_paginas_sensiveis_nao_ficam_em_cache(self):
        caminho = self._link()
        self.assertIn('no-store', self.client.get(reverse('esqueci_senha'))['Cache-Control'])
        self.assertIn('no-store', self.client.get(caminho)['Cache-Control'])

    def test_formularios_nao_usam_referrer_no_referrer(self):
        """`no-referrer` faz o navegador enviar `Origin: null` no POST e o CSRF recusa o formulário."""
        caminho = self._link()
        pagina_senha = self.client.get(self.client.get(caminho).url)
        for resposta in (self.client.get(reverse('esqueci_senha')), pagina_senha):
            self.assertNotContains(resposta, 'no-referrer')
            self.assertEqual(resposta['Referrer-Policy'], 'same-origin')

    def test_post_com_origem_do_proprio_site_passa_na_verificacao_csrf(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        pagina = cliente.get(reverse('esqueci_senha'))
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina.content.decode()).group(1)
        resp = cliente.post(reverse('esqueci_senha'), {'email': 'joao@example.com', 'csrfmiddlewaretoken': token},
                            HTTP_ORIGIN='http://testserver')
        self.assertEqual(resp.status_code, 302)

    @override_settings(SITE_URL='https://lab.exemplo.com.br', ALLOWED_HOSTS=['testserver', 'evil.example.com'])
    def test_link_usa_site_url_e_nao_o_cabecalho_host(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('esqueci_senha'), {'email': 'joao@example.com'}, HTTP_HOST='evil.example.com')
        self.assertIn('https://lab.exemplo.com.br/conta/redefinir-senha/', mail.outbox[0].body)
        self.assertNotIn('evil.example.com', mail.outbox[0].body)
