from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Agendamento, Computador, Laboratorio, Perfil, Software, SolicitacaoInstalacao, TipoAgendamento,
)


def _com_classe_form_control(fields):
    for field in fields.values():
        field.widget.attrs.update({'class': 'form-control'})



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
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
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
            'capacidade': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'Ex: 30'}),
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
        fields = ['identificador', 'laboratorio', 'status', 'softwares', 'observacoes']
        labels = {
            'identificador': 'Identificador da Máquina',
            'laboratorio': 'Laboratório',
            'status': 'Status da Máquina',
            'observacoes': 'Observações',
        }
        widgets = {
            'identificador': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: PC-01'}),
            'laboratorio': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        lab = cleaned.get('laboratorio')
        # capacidade 0 = sem limite definido
        if lab and lab.capacidade:
            outras = lab.computadores.exclude(pk=self.instance.pk).count()
            if outras + 1 > lab.capacidade:
                self.add_error(
                    'laboratorio',
                    f'O laboratório "{lab.nome}" já atingiu a capacidade de {lab.capacidade} máquinas.'
                )
        return cleaned


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

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Este e-mail já pertence a outro usuário.')
        return email


class AgendamentoForm(forms.ModelForm):
    class Meta:
        model = Agendamento
        fields = ['tipo', 'data_hora_inicio', 'data_hora_fim']
        labels = {
            'tipo': 'Tipo de Agendamento',
            'data_hora_inicio': 'Início do Agendamento',
            'data_hora_fim': 'Fim do Agendamento',
        }
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'data_hora_inicio': forms.DateTimeInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'data_hora_fim': forms.DateTimeInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].queryset = TipoAgendamento.objects.filter(ativo=True)
        self.fields['tipo'].empty_label = None

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        inicio = cleaned_data.get('data_hora_inicio')
        fim = cleaned_data.get('data_hora_fim')

        if inicio and fim:
            agora = timezone.now()

            minima = timezone.timedelta(minutes=settings.AGENDAMENTO_DURACAO_MINIMA_MIN)
            maxima = timezone.timedelta(minutes=tipo.duracao_maxima() if tipo else settings.AGENDAMENTO_DURACAO_MAXIMA_MIN)
            antecedencia = timezone.timedelta(days=settings.AGENDAMENTO_ANTECEDENCIA_MAXIMA_DIAS)
            bloco = settings.AGENDAMENTO_BLOCO_MIN

            # 5 min de tolerância para o tempo gasto preenchendo o formulário.
            if inicio < agora - timezone.timedelta(minutes=5):
                raise forms.ValidationError('A data de início do agendamento não pode ser no passado.')

            if inicio > agora + antecedencia:
                raise forms.ValidationError(
                    f'Só é possível reservar com até {settings.AGENDAMENTO_ANTECEDENCIA_MAXIMA_DIAS} dias de antecedência.'
                )

            if fim <= inicio:
                raise forms.ValidationError('A data/hora de término deve ser posterior ao horário de início.')

            for rotulo, dt in (('início', inicio), ('término', fim)):
                local = timezone.localtime(dt)
                if local.second or local.microsecond or local.minute % bloco:
                    raise forms.ValidationError(
                        f'O {rotulo} deve estar alinhado a blocos de {bloco} minutos (ex.: 14:00, 14:30).'
                    )

            if fim - inicio < minima:
                raise forms.ValidationError(f'A duração mínima da reserva é de {settings.AGENDAMENTO_DURACAO_MINIMA_MIN} minutos.')

            if fim - inicio > maxima:
                horas = maxima.total_seconds() / 3600
                raise forms.ValidationError(f'O tempo máximo permitido por reserva é de {horas:g} hora(s).')

            abertura, fechamento = settings.AGENDAMENTO_HORA_ABERTURA, settings.AGENDAMENTO_HORA_FECHAMENTO
            if (abertura, fechamento) != (0, 24):
                li, lf = timezone.localtime(inicio), timezone.localtime(fim)
                minutos_ini = li.hour * 60 + li.minute
                # término à meia-noite do dia seguinte conta como 24h
                virou_dia = lf.date() > li.date()
                minutos_fim = 24 * 60 if virou_dia and lf.hour == lf.minute == 0 else lf.hour * 60 + lf.minute
                if (virou_dia and minutos_fim != 24 * 60) or minutos_ini < abertura * 60 or minutos_fim > fechamento * 60:
                    raise forms.ValidationError(
                        f'Os laboratórios funcionam das {abertura:02d}h às {fechamento:02d}h.'
                    )

        return cleaned_data


class SolicitacaoInstalacaoForm(forms.ModelForm):
    """Solicitação de instalação de software.

    O campo `laboratorio` passou a fazer parte do formulário: o model já o
    usava em `destino_display()`, mas ele nunca era preenchido porque ficava
    fora de `fields` — toda solicitação era gravada como "Qualquer máquina".
    """

    class Meta:
        model = SolicitacaoInstalacao
        fields = ['laboratorio', 'software_nome', 'justificativa']
        labels = {
            'laboratorio': 'Laboratório de Destino',
            'software_nome': 'Nome e Versão do Software Desejado',
            'justificativa': 'Justificativa / Finalidade de Uso',
        }
        help_texts = {
            'laboratorio': 'Deixe em branco para solicitar em qualquer laboratório.',
        }
        widgets = {
            'laboratorio': forms.Select(attrs={'class': 'form-control'}),
            'software_nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Docker Desktop, Oracle SQL Developer'}),
            'justificativa': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Explique por que precisa deste programa'}),
        }

    def __init__(self, *args, computador=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['laboratorio'].required = False
        self.fields['laboratorio'].empty_label = 'Qualquer laboratório'

        # Ao solicitar a partir de uma máquina específica, o laboratório é
        # determinado por ela e não deve ser escolhido pelo usuário.
        if computador is not None:
            self.fields['laboratorio'].disabled = True
            self.fields['laboratorio'].initial = computador.laboratorio_id

    def clean_justificativa(self):
        justificativa = self.cleaned_data.get('justificativa', '').strip()
        if len(justificativa) < 10:
            raise forms.ValidationError('Descreva a justificativa com pelo menos 10 caracteres.')
        return justificativa


class AlterarSenhaForm(PasswordChangeForm):
    """Troca de senha pelo próprio usuário logado (pede a senha atual)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _com_classe_form_control(self.fields)


class ResetarSenhaForm(SetPasswordForm):
    """Redefinição de senha por um administrador.

    Não pede a senha atual: é exatamente o caso de um usuário que a esqueceu
    e não tem como informá-la.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _com_classe_form_control(self.fields)


class TipoAgendamentoForm(forms.ModelForm):
    class Meta:
        model = TipoAgendamento
        fields = ['nome', 'descricao', 'modo', 'valor_hora', 'duracao_maxima_min', 'ordem', 'ativo']
        labels = {
            'nome': 'Nome do tipo',
            'descricao': 'Descrição',
            'modo': 'Como cobrar',
            'valor_hora': 'Valor por hora (R$)',
            'duracao_maxima_min': 'Duração máxima (minutos)',
            'ordem': 'Ordem de exibição',
            'ativo': 'Ativo (disponível para novas reservas)',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
            'modo': forms.Select(attrs={'class': 'form-control'}),
            'valor_hora': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50', 'min': '0'}),
            'duracao_maxima_min': forms.NumberInput(attrs={'class': 'form-control', 'step': '30', 'min': '30'}),
            'ordem': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'ativo': forms.CheckboxInput(),
        }

    def clean(self):
        cleaned = super().clean()
        modo = cleaned.get('modo')
        if modo == TipoAgendamento.MODO_FIXO:
            valor = cleaned.get('valor_hora')
            if valor is None or valor < 0:
                self.add_error('valor_hora', 'Informe o valor por hora (zero ou maior).')
        bloco = settings.AGENDAMENTO_BLOCO_MIN
        dur = cleaned.get('duracao_maxima_min')
        if dur is not None and (dur < settings.AGENDAMENTO_DURACAO_MINIMA_MIN or dur % bloco):
            self.add_error('duracao_maxima_min', f'Use múltiplos de {bloco} minutos, no mínimo {settings.AGENDAMENTO_DURACAO_MINIMA_MIN}.')
        return cleaned
