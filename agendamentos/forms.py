from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Computador, Perfil, Agendamento, Laboratorio, Software, SolicitacaoInstalacao


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
        fields = ['nome', 'capacidade', 'descricao']
        labels = {
            'nome': 'Nome do Laboratório',
            'capacidade': 'Capacidade Máxima',
            'descricao': 'Descrição',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Laboratório de Informática 01'}),
            'capacidade': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 30'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descrição opcional'}),
        }


class SoftwareForm(forms.ModelForm):
    class Meta:
        model = Software
        fields = ['nome', 'versao', 'categoria']
        labels = {
            'nome': 'Nome do Software',
            'versao': 'Versão',
            'categoria': 'Categoria',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Java JDK, PostgreSQL, VS Code'}),
            'versao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 17 LTS, 15.2'}),
            'categoria': forms.Select(attrs={'class': 'form-control'}),
        }


class ComputadorForm(forms.ModelForm):
    softwares = forms.ModelMultipleChoiceField(
        queryset=Software.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="Softwares Instalados"
    )

    class Meta:
        model = Computador
        fields = ['identificador', 'laboratorio', 'status', 'valor_hora', 'softwares', 'observacoes']
        labels = {
            'identificador': 'Identificador da Máquina',
            'laboratorio': 'Laboratório',
            'status': 'Status da Máquina',
            'valor_hora': 'Valor/Hora (R$)',
            'observacoes': 'Observações',
        }
        widgets = {
            'identificador': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: PC-01'}),
            'laboratorio': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'valor_hora': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50', 'value': '0.00', 'placeholder': '0.00'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class EditarUsuarioForm(forms.ModelForm):
    tipo = forms.ChoiceField(
        choices=Perfil.TIPO_CHOICES,
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
        fields = ['finalidade', 'data_hora_inicio', 'data_hora_fim']
        labels = {
            'finalidade': 'Finalidade do Uso',
            'data_hora_inicio': 'Início do Agendamento',
            'data_hora_fim': 'Fim do Agendamento',
        }
        widgets = {
            'finalidade': forms.Select(attrs={'class': 'form-control'}),
            'data_hora_inicio': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'data_hora_fim': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get('data_hora_inicio')
        fim = cleaned_data.get('data_hora_fim')

        if inicio and fim:
            agora_com_tolerancia = timezone.now() - timezone.timedelta(minutes=5)

            if inicio < agora_com_tolerancia:
                raise forms.ValidationError('A data de início do agendamento não pode ser no passado.')

            if fim <= inicio:
                raise forms.ValidationError('A data/hora de término deve ser posterior ao horário de início.')

            duracao = fim - inicio
            if duracao > timezone.timedelta(hours=2):
                raise forms.ValidationError('O tempo máximo permitido por reserva é de 2 horas.')

        return cleaned_data


class SolicitacaoInstalacaoForm(forms.ModelForm):
    class Meta:
        model = SolicitacaoInstalacao
        fields = ['software_nome', 'justificativa']
        labels = {
            'software_nome': 'Nome e Versão do Software Desejado',
            'justificativa': 'Justificativa / Finalidade de Uso',
        }
        widgets = {
            'software_nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Docker Desktop, Oracle SQL Developer'}),
            'justificativa': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Explique por que precisa deste programa para uso geral'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)