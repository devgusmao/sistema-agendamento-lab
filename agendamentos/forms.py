from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Computador, Perfil

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