from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Prefetch
from django.utils import timezone  
from .forms import CustomUserCreationForm, ComputadorForm, EditarUsuarioForm, AgendamentoForm, LaboratorioForm
from .models import Computador, Laboratorio, Perfil, Agendamento


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


from django.db.models import Prefetch

@login_required
def home(request):
    if not request.user.is_superuser:
        if not hasattr(request.user, 'perfil') or not request.user.perfil.aprovado:
            return render(request, 'agendamentos/pendente.html')

    busca = request.GET.get('busca', '').strip()
    lab_id = request.GET.get('laboratorio', '')
    status_filtro = request.GET.get('status', '')

    # Traz apenas agendamentos confirmados a partir de agora
    agendamentos_futuros = Agendamento.objects.filter(
        status='CONFIRMADO',
        data_hora_fim__gte=timezone.now()
    ).order_by('data_hora_inicio')

    computadores = Computador.objects.all().select_related('laboratorio').prefetch_related(
        Prefetch('agendamento_set', queryset=agendamentos_futuros, to_attr='reservas_ativas')
    )

    if busca:
        computadores = computadores.filter(identificador__icontains=busca)
    if lab_id:
        computadores = computadores.filter(laboratorio_id=lab_id)
    if status_filtro:
        computadores = computadores.filter(status=status_filtro)

    laboratorios = Laboratorio.objects.all()
    
    is_gestor = request.user.is_superuser or (
        hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO']
    )
    
    context = {
        'computadores': computadores,
        'laboratorios': laboratorios,
        'is_gestor': is_gestor,
        'busca': busca,
        'lab_id': lab_id,
        'status_filtro': status_filtro,
    }
    return render(request, 'agendamentos/home.html', context)

@login_required
def cadastrar_laboratorio(request):
    is_gestor = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO'])
    if not is_gestor:
        messages.error(request, 'Acesso restrito para técnicos e administradores.')
        return redirect('home')

    if request.method == 'POST':
        form = LaboratorioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Laboratório cadastrado com sucesso!')
            return redirect('home')
    else:
        form = LaboratorioForm()

    return render(request, 'agendamentos/cadastrar_laboratorio.html', {'form': form})


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


@login_required
def editar_computador(request, computador_id):
    is_gestor = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO'])
    if not is_gestor:
        messages.error(request, 'Acesso restrito para técnicos e administradores.')
        return redirect('home')

    computador = get_object_or_404(Computador, id=computador_id)

    if request.method == 'POST':
        form = ComputadorForm(request.POST, instance=computador)
        if form.is_valid():
            form.save()
            messages.success(request, f'Máquina {computador.identificador} atualizada com sucesso!')
            return redirect('home')
    else:
        form = ComputadorForm(instance=computador)

    return render(request, 'agendamentos/editar_computador.html', {'form': form, 'computador': computador})


@login_required
def criar_agendamento(request, computador_id):
    if not request.user.is_superuser:
        if not hasattr(request.user, 'perfil') or not request.user.perfil.aprovado:
            return render(request, 'agendamentos/pendente.html')

    computador = get_object_or_404(Computador, id=computador_id)

    if computador.status != 'DISPONIVEL':
        messages.error(request, 'Esta máquina não está disponível para agendamento.')
        return redirect('home')

    reservas_existentes = Agendamento.objects.filter(
        computador=computador,
        status='CONFIRMADO',
        data_hora_fim__gte=timezone.now()
    ).order_by('data_hora_inicio')

    # Prepara a lista em formato serializável para JSON
    reservas_json = [
        {
            'from': r.data_hora_inicio.strftime('%Y-%m-%d %H:%M'),
            'to': r.data_hora_fim.strftime('%Y-%m-%d %H:%M')
        }
        for r in reservas_existentes
    ]

    if request.method == 'POST':
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            inicio = form.cleaned_data['data_hora_inicio']
            fim = form.cleaned_data['data_hora_fim']

            conflito = Agendamento.objects.filter(
                computador=computador,
                status='CONFIRMADO',
                data_hora_inicio__lt=fim,
                data_hora_fim__gt=inicio
            ).exists()

            if conflito:
                messages.error(request, 'Este computador já está reservado nesse horário. Escolha outro intervalo.')
            else:
                agendamento = form.save(commit=False)
                agendamento.usuario = request.user
                agendamento.computador = computador
                agendamento.save()
                messages.success(request, f'Agendamento confirmado para {computador.identificador}!')
                return redirect('home')
    else:
        form = AgendamentoForm()

    return render(request, 'agendamentos/agendar.html', {
        'form': form, 
        'computador': computador,
        'reservas_existentes': reservas_existentes,
        'reservas_json': reservas_json
    })

@login_required
def listar_laboratorios(request):
    is_gestor = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO'])
    if not is_gestor:
        messages.error(request, 'Acesso restrito para técnicos e administradores.')
        return redirect('home')

    laboratorios = Laboratorio.objects.all().order_by('nome')
    return render(request, 'agendamentos/laboratorios.html', {'laboratorios': laboratorios})


@login_required
def editar_laboratorio(request, laboratorio_id):
    is_gestor = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO'])
    if not is_gestor:
        messages.error(request, 'Acesso restrito.')
        return redirect('home')

    laboratorio = get_object_or_404(Laboratorio, id=laboratorio_id)

    if request.method == 'POST':
        form = LaboratorioForm(request.POST, instance=laboratorio)
        if form.is_valid():
            form.save()
            messages.success(request, f'Laboratório "{laboratorio.nome}" atualizado com sucesso!')
            return redirect('listar_laboratorios')
    else:
        form = LaboratorioForm(instance=laboratorio)

    return render(request, 'agendamentos/cadastrar_laboratorio.html', {'form': form, 'laboratorio': laboratorio})

@login_required
def meus_agendamentos(request):
    agendamentos = Agendamento.objects.filter(usuario=request.user).order_by('-data_hora_inicio')
    return render(request, 'agendamentos/meus_agendamentos.html', {'agendamentos': agendamentos})


from django.db.models import Q

@login_required
def gerenciar_agendamentos(request):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')
    if not is_admin:
        messages.error(request, 'Acesso restrito para administradores.')
        return redirect('home')

    busca = request.GET.get('busca', '')
    status_filtro = request.GET.get('status', '')

    agendamentos = Agendamento.objects.all().select_related('usuario', 'computador').order_by('-data_hora_inicio')

    if busca:
        agendamentos = agendamentos.filter(
            Q(usuario__username__icontains=busca) |
            Q(usuario__email__icontains=busca) |
            Q(computador__identificador__icontains=busca)
        )

    if status_filtro:
        agendamentos = agendamentos.filter(status=status_filtro)

    return render(request, 'agendamentos/gerenciar_agendamentos.html', {
        'agendamentos': agendamentos,
        'busca': busca,
        'status_filtro': status_filtro
    })


@login_required
def cancelar_agendamento(request, agendamento_id):
    agendamento = get_object_or_404(Agendamento, id=agendamento_id)
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')

    if agendamento.usuario == request.user or is_admin:
        agendamento.status = 'CANCELADO'
        agendamento.save()
        messages.success(request, f'Agendamento de {agendamento.computador.identificador} foi cancelado.')
    else:
        messages.error(request, 'Você não tem permissão para cancelar este agendamento.')

    if is_admin and request.GET.get('from') == 'admin':
        return redirect('gerenciar_agendamentos')
    return redirect('meus_agendamentos')


@login_required
def liberar_usuarios(request):
    is_admin = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo == 'ADMIN')
    if not is_admin:
        messages.error(request, 'Acesso negado. Apenas administradores podem acessar esta página.')
        return redirect('home')

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
    if usuario_obj == request.user:
        messages.error(request, 'Você não pode excluir sua própria conta.')
        return redirect('gerenciar_usuarios')

    usuario_obj.delete()
    messages.success(request, 'Usuário removido com sucesso.')
    return redirect('gerenciar_usuarios')

@login_required
def listar_computadores(request):
    is_gestor = request.user.is_superuser or (hasattr(request.user, 'perfil') and request.user.perfil.tipo in ['ADMIN', 'TECNICO'])
    if not is_gestor:
        messages.error(request, 'Acesso restrito para técnicos e administradores.')
        return redirect('home')

    computadores = Computador.objects.all().select_related('laboratorio').order_by('identificador')
    return render(request, 'agendamentos/computadores.html', {'computadores': computadores})