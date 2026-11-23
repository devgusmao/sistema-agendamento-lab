"""O banco garante um e-mail por conta, mesmo fora dos formulários."""

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .tests import criar_usuario


class EmailUnicoNoBancoTests(TestCase):
    def test_banco_recusa_e_mail_repetido(self):
        criar_usuario('a1', email='dup@example.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('a2', email='dup@example.com', password='x')

    def test_banco_ignora_maiusculas(self):
        criar_usuario('b1', email='Misto@Example.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('b2', email='misto@example.COM', password='x')

    def test_e_mail_vazio_pode_repetir(self):
        User.objects.create_user('c1', email='', password='x')
        User.objects.create_user('c2', email='', password='x')
        self.assertEqual(User.objects.filter(email='').count(), 2)

    def test_cadastro_pelo_formulario_continua_com_mensagem_amigavel(self):
        criar_usuario('d1', email='ja@example.com')
        resp = self.client.post(reverse('cadastrar'), {
            'username': 'novo_d', 'email': 'JA@example.com',
            'password1': 'Senha-Forte-123', 'password2': 'Senha-Forte-123',
        })
        self.assertContains(resp, 'já está cadastrado')
        self.assertFalse(User.objects.filter(username='novo_d').exists())

    def test_corrida_no_cadastro_vira_erro_de_formulario_e_nao_500(self):
        from unittest import mock
        criar_usuario('e1', email='corrida@example.com')
        # Simula a janela entre a validação do formulário e a gravação: o banco barra o duplicado.
        with mock.patch('agendamentos.forms.CustomUserCreationForm.clean_email', lambda self: self.cleaned_data['email'].lower()):
            resp = self.client.post(reverse('cadastrar'), {
                'username': 'novo_e', 'email': 'corrida@example.com',
                'password1': 'Senha-Forte-123', 'password2': 'Senha-Forte-123',
            })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'já está cadastrado')
        self.assertFalse(User.objects.filter(username='novo_e').exists())
