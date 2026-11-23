"""Confirmação de e-mail e recuperação de senha com código numérico de 6 dígitos."""

import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CodigoVerificacao, LimiteSolicitacao, Perfil
from .servicos import codigos
from .tests import criar_usuario

SENHA_NOVA = 'Nova-Senha-Forte-987'


def entrar(cliente, username, senha):
    """Login real pela tela (o `client.login` do Django não funciona com o django-axes)."""
    cliente.post(reverse('login'), {'username': username, 'password': senha})
    return '_auth_user_id' in cliente.session


def codigo_do_email(mensagem):
    """Código de 6 dígitos que o e-mail traz (texto simples)."""
    return re.search(r'Seu código:\n(\d{6})', mensagem.body).group(1)


def codigo_errado(certo):
    return f'{(int(certo) + 1) % 10 ** 6:06d}'


class BaseContas(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()

    def _cadastrar(self, username='novato', email='novato@example.com'):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('cadastrar'), {
                'username': username, 'email': email,
                'password1': 'Senha-Forte-123', 'password2': 'Senha-Forte-123',
            })

    def _pedir_recuperacao(self, email, cliente=None):
        with self.captureOnCommitCallbacks(execute=True):
            return (cliente or self.client).post(reverse('esqueci_senha'), {'email': email})


class CodigoDeConfirmacaoTests(BaseContas):
    def setUp(self):
        super().setUp()
        self.admin = criar_usuario('adm_c', tipo='ADMIN', email='adm@example.com')

    def test_cadastro_envia_codigo_so_ao_novo_usuario_e_abre_a_tela_do_codigo(self):
        resp = self._cadastrar()
        self.assertRedirects(resp, reverse('confirmar_email'))
        perfil = Perfil.objects.get(usuario__username='novato')
        self.assertFalse(perfil.email_verificado)
        self.assertFalse(perfil.aprovado)
        self.assertEqual([m.to for m in mail.outbox], [['novato@example.com']])

    def test_email_traz_codigo_curto_e_nenhum_link(self):
        self._cadastrar()
        mensagem = mail.outbox[0]
        self.assertRegex(codigo_do_email(mensagem), r'^\d{6}$')
        self.assertIn(codigo_do_email(mensagem), mensagem.alternatives[0][0])
        self.assertNotIn('http', mensagem.body)
        self.assertNotIn('localhost', mensagem.body + mensagem.alternatives[0][0])

    def test_tela_do_codigo_vem_com_o_email_preenchido(self):
        self._cadastrar()
        self.assertContains(self.client.get(reverse('confirmar_email')), 'value="novato@example.com"')

    def _confirmar(self, email, codigo, cliente=None):
        with self.captureOnCommitCallbacks(execute=True):
            return (cliente or self.client).post(reverse('confirmar_email'), {'email': email, 'codigo': codigo})

    def test_codigo_certo_confirma_e_avisa_o_admin_uma_unica_vez(self):
        self._cadastrar()
        codigo = codigo_do_email(mail.outbox[0])
        mail.outbox.clear()
        resp = self._confirmar('novato@example.com', codigo)
        self.assertContains(resp, 'E-mail confirmado')
        self.assertTrue(Perfil.objects.get(usuario__username='novato').email_verificado)
        self.assertEqual([m.to for m in mail.outbox], [['adm@example.com']])
        mail.outbox.clear()
        again = self._confirmar('novato@example.com', codigo)  # código já usado
        self.assertContains(again, 'Código inválido ou expirado')
        self.assertEqual(mail.outbox, [])

    def test_aceita_espacos_e_traco_ao_digitar(self):
        self._cadastrar()
        codigo = codigo_do_email(mail.outbox[0])
        resp = self._confirmar('NOVATO@Example.com', f' {codigo[:3]} {codigo[3:]} ')
        self.assertContains(resp, 'E-mail confirmado')

    def test_codigo_errado_nao_confirma(self):
        self._cadastrar()
        certo = codigo_do_email(mail.outbox[0])
        resp = self._confirmar('novato@example.com', codigo_errado(certo))
        self.assertContains(resp, 'Código inválido ou expirado')
        self.assertFalse(Perfil.objects.get(usuario__username='novato').email_verificado)

    def test_formato_invalido_e_email_inexistente_dao_a_mesma_mensagem(self):
        self._cadastrar()
        for email, codigo in (('novato@example.com', 'abc'), ('novato@example.com', '12345'),
                              ('novato@example.com', '1234567'), ('ninguem@example.com', '123456')):
            self.assertContains(self._confirmar(email, codigo), 'Código inválido ou expirado')

    def test_codigo_expira(self):
        self._cadastrar()
        codigo = codigo_do_email(mail.outbox[0])
        CodigoVerificacao.objects.update(expira_em=timezone.now() - timedelta(seconds=1))
        self.assertContains(self._confirmar('novato@example.com', codigo), 'Código inválido ou expirado')

    def test_cinco_erros_invalidam_o_codigo_ate_o_certo(self):
        self._cadastrar()
        certo = codigo_do_email(mail.outbox[0])
        for _ in range(5):
            self._confirmar('novato@example.com', codigo_errado(certo))
        resp = self._confirmar('novato@example.com', certo)
        self.assertContains(resp, 'Código inválido ou expirado')
        self.assertFalse(Perfil.objects.get(usuario__username='novato').email_verificado)

    def test_quatro_erros_ainda_deixam_usar_o_certo(self):
        self._cadastrar()
        certo = codigo_do_email(mail.outbox[0])
        for _ in range(4):
            self._confirmar('novato@example.com', codigo_errado(certo))
        self.assertContains(self._confirmar('novato@example.com', certo), 'E-mail confirmado')

    def test_codigo_novo_invalida_o_anterior(self):
        self._cadastrar()
        antigo = codigo_do_email(mail.outbox[0])
        self.client.post(reverse('login'), {'username': 'novato', 'password': 'Senha-Forte-123'})
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('reenviar_confirmacao'))
        novo = codigo_do_email(mail.outbox[-1])
        self.assertNotEqual(antigo, novo)
        self.assertContains(self._confirmar('novato@example.com', antigo), 'Código inválido ou expirado')
        self.assertContains(self._confirmar('novato@example.com', novo), 'E-mail confirmado')

    def test_so_o_hash_do_codigo_fica_no_banco(self):
        self._cadastrar()
        codigo = codigo_do_email(mail.outbox[0])
        registro = CodigoVerificacao.objects.get()
        self.assertNotIn(codigo, registro.codigo_hash)
        self.assertEqual(len(registro.codigo_hash), 64)

    def test_codigo_de_um_usuario_nao_serve_para_outro(self):
        self._cadastrar('a1', 'a1@example.com')
        codigo_a1 = codigo_do_email(mail.outbox[0])
        self._cadastrar('a2', 'a2@example.com')
        self.assertContains(self._confirmar('a2@example.com', codigo_a1), 'Código inválido ou expirado')

    def test_codigo_de_recuperacao_nao_serve_para_confirmar_email(self):
        self._cadastrar()
        mail.outbox.clear()
        self._pedir_recuperacao('novato@example.com')
        codigo_senha = codigo_do_email(mail.outbox[0])
        resp = self._confirmar('novato@example.com', codigo_senha)
        self.assertContains(resp, 'Código inválido ou expirado')

    def test_tentativas_limitadas_por_ip(self):
        for _ in range(20):
            self.client.post(reverse('confirmar_email'), {'email': 'x@example.com', 'codigo': '123456'})
        resp = self.client.post(reverse('confirmar_email'), {'email': 'x@example.com', 'codigo': '123456'})
        self.assertContains(resp, 'Muitas tentativas')

    def test_confirmar_nao_libera_o_acesso(self):
        self._cadastrar()
        self._confirmar('novato@example.com', codigo_do_email(mail.outbox[0]))
        entrar(self.client, 'novato', 'Senha-Forte-123')
        resp = self.client.get(reverse('home'))
        self.assertContains(resp, 'Cadastro pendente de liberação', status_code=403)

    def test_aprovado_mas_sem_confirmar_o_email_nao_entra(self):
        self._cadastrar()
        Perfil.objects.filter(usuario__username='novato').update(aprovado=True)
        entrar(self.client, 'novato', 'Senha-Forte-123')
        self.assertContains(self.client.get(reverse('home')), 'Confirme o seu e-mail', status_code=403)

    def test_aprovado_e_confirmado_entra(self):
        self._cadastrar()
        self._confirmar('novato@example.com', codigo_do_email(mail.outbox[0]))
        Perfil.objects.filter(usuario__username='novato').update(aprovado=True)
        entrar(self.client, 'novato', 'Senha-Forte-123')
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_pagina_pendente_leva_a_tela_do_codigo(self):
        self._cadastrar()
        entrar(self.client, 'novato', 'Senha-Forte-123')
        self.assertContains(self.client.get(reverse('home')), reverse('confirmar_email'), status_code=403)

    def test_reenvio_logado_tem_limite_por_usuario(self):
        self._cadastrar()
        entrar(self.client, 'novato', 'Senha-Forte-123')
        mail.outbox.clear()
        for _ in range(5):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('reenviar_confirmacao'))
        self.assertEqual(len(mail.outbox), 2)  # 1 do cadastro + 2 reenvios = 3 por hora

    def test_reenvio_anonimo_responde_igual_e_so_envia_para_conta_pendente(self):
        self._cadastrar()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            pendente = self.client.post(reverse('reenviar_confirmacao'), {'email': 'novato@example.com'})
            inexistente = self.client.post(reverse('reenviar_confirmacao'), {'email': 'ninguem@example.com'})
            confirmada = self.client.post(reverse('reenviar_confirmacao'), {'email': 'adm@example.com'})
        self.assertEqual({pendente.url, inexistente.url, confirmada.url}, {reverse('confirmar_email')})
        self.assertEqual([m.to for m in mail.outbox], [['novato@example.com']])

    def test_reenvio_exige_post(self):
        self.assertEqual(self.client.get(reverse('reenviar_confirmacao')).status_code, 405)

    def test_usuarios_existentes_continuam_confirmados(self):
        self.assertTrue(Perfil.objects.get(usuario=self.admin).email_verificado)

    def test_lista_de_aprovacao_mostra_se_o_email_foi_confirmado(self):
        self._cadastrar()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('liberar_usuarios')), 'e-mail ainda não confirmado')

    def test_pagina_do_codigo_nao_fica_em_cache(self):
        self.assertIn('no-store', self.client.get(reverse('confirmar_email'))['Cache-Control'])


class RecuperarSenhaTests(BaseContas):
    def setUp(self):
        super().setUp()
        self.admin = criar_usuario('adm_r', tipo='ADMIN', email='adm@example.com')
        self.usuario = criar_usuario('maria', email='maria@example.com')

    def _redefinir(self, email, codigo, senha=SENHA_NOVA, confirmar=None, cliente=None):
        with self.captureOnCommitCallbacks(execute=True):
            return (cliente or self.client).post(reverse('redefinir_senha'), {
                'email': email, 'codigo': codigo, 'new_password1': senha, 'new_password2': confirmar or senha,
            })

    def _pedir_e_pegar_codigo(self, email='maria@example.com'):
        self._pedir_recuperacao(email)
        codigo = codigo_do_email(mail.outbox[-1])
        mail.outbox.clear()
        return codigo

    def test_login_tem_link_de_esqueci_a_senha(self):
        self.assertContains(self.client.get(reverse('login')), reverse('esqueci_senha'))

    def test_pedido_envia_codigo_curto_e_abre_a_tela_de_redefinir(self):
        resp = self._pedir_recuperacao('maria@example.com')
        self.assertRedirects(resp, reverse('redefinir_senha'))
        self.assertEqual([m.to for m in mail.outbox], [['maria@example.com']])
        self.assertRegex(codigo_do_email(mail.outbox[0]), r'^\d{6}$')
        self.assertNotIn('http', mail.outbox[0].body)

    def test_fluxo_completo(self):
        codigo = self._pedir_e_pegar_codigo()
        resp = self._redefinir('maria@example.com', codigo)
        self.assertRedirects(resp, reverse('login'))
        self.assertFalse(entrar(self.client, 'maria', 'senha-de-teste-123'))
        self.assertTrue(entrar(self.client, 'maria', SENHA_NOVA))
        self.assertEqual([m.to for m in mail.outbox], [['maria@example.com']])  # alerta de senha alterada
        self.assertNotIn(SENHA_NOVA, mail.outbox[0].body)

    def test_resposta_identica_exista_ou_nao_a_conta(self):
        existente = self._pedir_recuperacao('maria@example.com')
        inexistente = self._pedir_recuperacao('ninguem@example.com')
        self.assertEqual((existente.status_code, existente.url), (inexistente.status_code, inexistente.url))
        self.assertEqual(len(mail.outbox), 1)
        mensagens = [str(m) for m in self.client.get(reverse('redefinir_senha')).context['messages']]
        self.assertTrue(all('Se este e-mail estiver cadastrado' in m for m in mensagens))

    def test_email_em_maiusculas_funciona(self):
        self._pedir_recuperacao('MARIA@Example.com')
        self.assertEqual(len(mail.outbox), 1)

    def test_conta_inativa_nao_recebe(self):
        User.objects.filter(pk=self.usuario.pk).update(is_active=False)
        self._pedir_recuperacao('maria@example.com')
        self.assertEqual(mail.outbox, [])

    def test_codigo_so_vale_uma_vez(self):
        codigo = self._pedir_e_pegar_codigo()
        self._redefinir('maria@example.com', codigo)
        resp = self._redefinir('maria@example.com', codigo, senha='Outra-Senha-Forte-123', cliente=Client())
        self.assertContains(resp, 'Código inválido ou expirado')
        self.assertTrue(entrar(self.client, 'maria', SENHA_NOVA))

    def test_codigo_expira(self):
        codigo = self._pedir_e_pegar_codigo()
        CodigoVerificacao.objects.update(expira_em=timezone.now() - timedelta(seconds=1))
        self.assertContains(self._redefinir('maria@example.com', codigo), 'Código inválido ou expirado')

    def test_validade_padrao_do_codigo_de_senha_e_curta(self):
        self._pedir_e_pegar_codigo()
        registro = CodigoVerificacao.objects.get()
        self.assertLessEqual(registro.expira_em - registro.criado_em, timedelta(minutes=16))

    def test_cinco_erros_invalidam_o_codigo(self):
        codigo = self._pedir_e_pegar_codigo()
        for _ in range(5):
            self._redefinir('maria@example.com', codigo_errado(codigo))
        self.assertContains(self._redefinir('maria@example.com', codigo), 'Código inválido ou expirado')
        self.assertTrue(entrar(self.client, 'maria', 'senha-de-teste-123'))  # senha antiga intacta

    def test_codigo_de_outro_usuario_nao_serve(self):
        criar_usuario('bia', email='bia@example.com')
        codigo_maria = self._pedir_e_pegar_codigo('maria@example.com')
        self._pedir_e_pegar_codigo('bia@example.com')
        self.assertContains(self._redefinir('bia@example.com', codigo_maria), 'Código inválido ou expirado')

    def test_senha_fraca_ou_diferente_nao_gasta_o_codigo(self):
        codigo = self._pedir_e_pegar_codigo()
        fraca = self._redefinir('maria@example.com', codigo, senha='12345678')
        self.assertEqual(fraca.status_code, 200)
        diferente = self._redefinir('maria@example.com', codigo, confirmar='Outra-Senha-123')
        self.assertEqual(diferente.status_code, 200)
        self.assertTrue(entrar(self.client, 'maria', 'senha-de-teste-123'))
        self.client.logout()
        ok = self._redefinir('maria@example.com', codigo)  # o mesmo código ainda vale
        self.assertRedirects(ok, reverse('login'))

    def test_trocar_senha_invalida_sessoes_abertas(self):
        outro = self.client_class()
        outro.force_login(self.usuario)
        self.assertEqual(outro.get(reverse('home')).status_code, 200)
        self._redefinir('maria@example.com', self._pedir_e_pegar_codigo())
        self.assertEqual(outro.get(reverse('home')).status_code, 302)

    def test_libera_login_travado_por_tentativas(self):
        from axes.models import AccessAttempt
        AccessAttempt.objects.create(username='maria', ip_address='127.0.0.1', failures_since_start=5)
        self._redefinir('maria@example.com', self._pedir_e_pegar_codigo())
        self.assertFalse(AccessAttempt.objects.filter(username='maria').exists())

    def test_usuario_aprovado_continua_aprovado_sem_novo_aval(self):
        self._redefinir('maria@example.com', self._pedir_e_pegar_codigo())
        entrar(self.client, 'maria', SENHA_NOVA)
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_conta_nova_continua_exigindo_aprovacao(self):
        self._cadastrar('novata', 'novata@example.com')
        mail.outbox.clear()
        codigo = self._pedir_e_pegar_codigo('novata@example.com')
        self._redefinir('novata@example.com', codigo)
        perfil = Perfil.objects.get(usuario__username='novata')
        self.assertTrue(perfil.email_verificado)   # recebeu o código no e-mail: comprovou que é dono
        self.assertFalse(perfil.aprovado)          # mas o administrador ainda precisa liberar
        entrar(self.client, 'novata', SENHA_NOVA)
        self.assertEqual(self.client.get(reverse('home')).status_code, 403)
        self.assertIn(['adm@example.com'], [m.to for m in mail.outbox])

    def test_limites_de_pedido_por_usuario_e_por_ip(self):
        for _ in range(6):
            self._pedir_recuperacao('maria@example.com')
        self.assertEqual(len(mail.outbox), 3)
        mail.outbox.clear()
        for i in range(15):
            criar_usuario(f'u{i}', email=f'u{i}@example.com')
        LimiteSolicitacao.objects.all().delete()
        for i in range(15):
            self._pedir_recuperacao(f'u{i}@example.com')
        self.assertEqual(len(mail.outbox), 10)

    def test_limite_libera_depois_da_janela(self):
        for _ in range(3):
            self._pedir_recuperacao('maria@example.com')
        LimiteSolicitacao.objects.update(criado_em=timezone.now() - timedelta(hours=2))
        mail.outbox.clear()
        self._pedir_recuperacao('maria@example.com')
        self.assertEqual(len(mail.outbox), 1)

    def test_tentativas_de_codigo_limitadas_por_ip(self):
        for _ in range(20):
            self.client.post(reverse('redefinir_senha'), {
                'email': 'x@example.com', 'codigo': '123456', 'new_password1': 'a', 'new_password2': 'a'})
        resp = self.client.post(reverse('redefinir_senha'), {
            'email': 'x@example.com', 'codigo': '123456', 'new_password1': 'a', 'new_password2': 'a'})
        self.assertContains(resp, 'Muitas tentativas')

    def test_email_invalido_nao_envia(self):
        resp = self.client.post(reverse('esqueci_senha'), {'email': 'isso-nao-e-email'})
        self.assertContains(resp, 'Informe um e-mail válido')
        self.assertEqual(mail.outbox, [])

    def test_usuario_logado_vai_para_alterar_senha(self):
        self.client.force_login(self.usuario)
        self.assertRedirects(self.client.get(reverse('esqueci_senha')), reverse('alterar_senha'))
        self.assertRedirects(self.client.get(reverse('redefinir_senha')), reverse('alterar_senha'))

    def test_paginas_sensiveis_nao_ficam_em_cache(self):
        for nome in ('esqueci_senha', 'redefinir_senha'):
            self.assertIn('no-store', self.client.get(reverse(nome))['Cache-Control'])

    def test_formularios_nao_usam_referrer_no_referrer(self):
        """`no-referrer` faz o navegador enviar `Origin: null` no POST e o CSRF recusa o formulário."""
        for nome in ('esqueci_senha', 'redefinir_senha', 'confirmar_email'):
            resposta = self.client.get(reverse(nome))
            self.assertNotContains(resposta, 'no-referrer')
            self.assertEqual(resposta['Referrer-Policy'], 'same-origin')

    def test_post_com_origem_do_proprio_site_passa_na_verificacao_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        pagina = cliente.get(reverse('esqueci_senha'))
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina.content.decode()).group(1)
        resp = cliente.post(reverse('esqueci_senha'), {'email': 'maria@example.com', 'csrfmiddlewaretoken': token},
                            HTTP_ORIGIN='http://testserver')
        self.assertEqual(resp.status_code, 302)


class ServicoDeCodigosTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario('svc', email='svc@example.com')

    def test_codigo_tem_6_digitos_e_e_aleatorio(self):
        gerados = {codigos.gerar(self.usuario, CodigoVerificacao.EMAIL, 10) for _ in range(20)}
        self.assertTrue(all(re.fullmatch(r'\d{6}', c) for c in gerados))
        self.assertGreater(len(gerados), 15)

    def test_normalizar(self):
        self.assertEqual(codigos.normalizar(' 123 456 '), '123456')
        self.assertEqual(codigos.normalizar('123-456'), '123456')
        for ruim in ('', None, '12345', '1234567', 'abcdef'):
            self.assertEqual(codigos.normalizar(ruim), '')

    def test_hash_depende_da_secret_key(self):
        codigo = codigos.gerar(self.usuario, CodigoVerificacao.EMAIL, 10)
        guardado = CodigoVerificacao.objects.get().codigo_hash
        with override_settings(SECRET_KEY='outra-chave'):
            self.assertNotEqual(codigos._hash(self.usuario.pk, 'EMAIL', codigo), guardado)

    def test_consumir_e_uso_unico(self):
        codigo = codigos.gerar(self.usuario, CodigoVerificacao.EMAIL, 10)
        registro = codigos.conferir(self.usuario, CodigoVerificacao.EMAIL, codigo)
        self.assertTrue(codigos.consumir(registro))
        self.assertFalse(codigos.consumir(registro))
        self.assertIsNone(codigos.conferir(self.usuario, CodigoVerificacao.EMAIL, codigo))

    def test_limpar_antigos(self):
        codigos.gerar(self.usuario, CodigoVerificacao.EMAIL, 10)
        CodigoVerificacao.objects.update(expira_em=timezone.now() - timedelta(days=3))
        codigos.limpar_antigos()
        self.assertEqual(CodigoVerificacao.objects.count(), 0)
