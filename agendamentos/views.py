from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .forms import CustomUserCreationForm, ComputadorForm, EditarUsuarioForm
from .models import Computador, Laboratorio, Perfil

def cadastrar(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Conta criada com sucesso! Aguarde a aprovação do administrador para acessar o sistema.')
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'agendamentos/cadastrar.html', {'form': form})

@login_required
def home(request):
    if not request.user.is_superuser:
        if not hasattr(request.user, 'perfil') or not request.user.perfil.aprovado:
            return render(request, 'agendamentos/pendente.html')

    computadores = Computador.objects.all()
    laboratorios = Laboratorio.objects.all()
    
    is_gestor = request.user.is_superuser or (
        hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO']
    )
    
    context = {
        'computadores': computadores,
        'laboratorios': laboratorios,
        'is_gestor': is_gestor
    }
    return render(request, 'agendamentos/home.html', context)

@login_required
def liberar_usuarios(request):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')
    if not is_admin:
        messages.error(request, 'Acesso negado. Apenas administradores podem acessar esta página.')
        return redirect('home')

    # Garante que todos os usuarios cadastrados tenham um Perfil criado
    for user_obj in User.objects.all():
        Perfil.objects.get_or_create(usuario=user_obj)

    perfis_pendentes = Perfil.objects.filter(aprovado=False)
    perfis_aprovados = Perfil.objects.filter(aprovado=True)

    return render(request, 'agendamentos/liberar_usuarios.html', {
        'pendentes': perfis_pendentes,
        'aprovados': perfis_aprovados
    })

@login_required
def aprovar_usuario(request, perfil_id):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')
    if not is_admin:
        return redirect('home')
    
    perfil = get_object_or_404(Perfil, id=perfil_id)
    perfil.aprovado = True
    perfil.save()
    messages.success(request, f'Usuário {perfil.usuario.username} liberado com sucesso!')
    return redirect('liberar_usuarios')

@login_required
def cadastrar_computador(request):
    is_gestor = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO'])
    if not is_gestor:
        messages.error(request, 'Acesso restrito para técnicos e administradores.')
        return redirect('home')

    if request.method == 'POST':
        form = ComputadorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Computador cadastrado com sucesso!')
            return redirect('home')
    else:
        form = ComputadorForm()

    return render(request, 'agendamentos/cadastrar_computador.html', {'form': form})

# --- GESTÃO DE USUÁRIOS ---

@login_required
def gerenciar_usuarios(request):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')
    if not is_admin:
        messages.error(request, 'Acesso restrito a administradores.')
        return redirect('home')

    usuarios = User.objects.all().select_related('perfil').order_by('-date_joined')
    return render(request, 'agendamentos/gerenciar_usuarios.html', {'usuarios': usuarios})

@login_required
def editar_usuario(request, user_id):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')
    if not is_admin:
        messages.error(request, 'Acesso restrito a administradores.')
        return redirect('home')

    usuario_obj = get_object_or_404(User, id=user_id)
    perfil, _ = Perfil.objects.get_or_create(usuario=usuario_obj)

    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario_obj)
        if form.is_valid():
            user_saved = form.save()
            perfil.tipo = form.cleaned_data['tipo']
            perfil.aprovado = form.cleaned_data['aprovado']
            perfil.save()
            messages.success(request, f'Usuário {user_saved.username} atualizado com sucesso!')
            return redirect('gerenciar_usuarios')
    else:
        form = EditarUsuarioForm(instance=usuario_obj, initial={
            'tipo': perfil.tipo,
            'aprovado': perfil.aprovado
        })

    return render(request, 'agendamentos/editar_usuario.html', {'form': form, 'usuario_obj': usuario_obj})

@login_required
def deletar_usuario(request, user_id):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')
    if not is_admin:
        return redirect('home')

    usuario_obj = get_object_or_404(User, id=user_id)
    
    # Evita que o admin apague a si mesmo
    if usuario_obj == request.user:
        messages.error(request, 'Você não pode excluir sua própria conta.')
        return redirect('gerenciar_usuarios')

    usuario_obj.delete()
    messages.success(request, 'Usuário removido com sucesso.')
    return redirect('gerenciar_usuarios')