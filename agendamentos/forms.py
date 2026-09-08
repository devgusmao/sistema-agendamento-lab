from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Computador, Perfil, Agendamento, Laboratorio

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label='E-mail Institucional',
        help_text='Digite seu e-mail institucional'
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Este e-mail já está cadastrado no sistema.')
        return email

class LaboratorioForm(forms.ModelForm):
    class Meta:
        model = Laboratorio
        fields = ['nome', 'capacidade']
        labels = {
            'nome': 'Nome do Laboratório',
            'capacidade': 'Capacidade Máxima',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Laboratório de Informática 01'}),
            'capacidade': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 30'}),
        }

class ComputadorForm(forms.ModelForm):
    class Meta:
        model = Computador
        fields = ['identificador', 'laboratorio', 'status', 'observacoes']
        widgets = {
            'identificador': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: PC-01'}),
            'laboratorio': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class EditarUsuarioForm(forms.ModelForm):
    tipo = forms.ChoiceField(
        choices=Perfil.TIPO_PERFIL, 
        label="Tipo de Perfil", 
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    aprovado = forms.BooleanField(
        required=False, 
        label="Acesso Liberado no Sistema", 
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        labels = {
            'username': 'Usuário / Matrícula',
            'first_name': 'Nome',
            'last_name': 'Sobrenome',
            'email': 'E-mail',
        }
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class AgendamentoForm(forms.ModelForm):
    class Meta:
        model = Agendamento
        fields = ['data_hora_inicio', 'data_hora_fim']
        labels = {
            'data_hora_inicio': 'Início do Agendamento',
            'data_hora_fim': 'Fim do Agendamento',
        }
        widgets = {
            'data_hora_inicio': forms.DateTimeInput(attrs={'class': 'form-control', 'placeholder': 'Selecione a data e hora de início'}),
            'data_hora_fim': forms.DateTimeInput(attrs={'class': 'form-control', 'placeholder': 'Selecione a data e hora de término'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get('data_hora_inicio')
        fim = cleaned_data.get('data_hora_fim')

        if inicio and fim:
            # 1. Tolerância de 5 minutos para trás para evitar problemas de fuso/envio
            agora_com_tolerancia = timezone.now() - timezone.timedelta(minutes=5)

            if inicio < agora_com_tolerancia:
                raise forms.ValidationError('A data de início do agendamento não pode ser no passado.')

            # 2. Valida se o término é posterior ao início
            if fim <= inicio:
                raise forms.ValidationError('A data/hora de término deve ser posterior ao horário de início.')

            # 3. VALIDAÇÃO DE LIMITE MÁXIMO DE 2 HORAS
            duracao = fim - inicio
            if duracao > timezone.timedelta(hours=2):
                raise forms.ValidationError('O tempo máximo permitido por reserva é de 2 horas.')

        return cleaned_data