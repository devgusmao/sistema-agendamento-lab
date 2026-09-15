from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import admin_required, aprovado_required, gestor_required
from .forms import (
    AgendamentoForm,
    AlterarSenhaForm,
    ComputadorForm,
    CustomUserCreationForm,
    EditarUsuarioForm,
    LaboratorioForm,
    ResetarSenhaForm,
    SoftwareForm,
    SolicitacaoInstalacaoForm,
)
from .models import (
    Agendamento,
    Computador,
    Laboratorio,
    Perfil,
    Software,
    SolicitacaoInstalacao,
    perfil_e_admin,
    perfil_e_gestor,
)

ITENS_POR_PAGINA = 20


def _paginar(request, queryset, por_pagina=ITENS_POR_PAGINA):
    paginator = Paginator(queryset, por_pagina)
    return paginator.get_page(request.GET.get('page'))


# --- AUTENTICAÇÃO E CADASTRO ---

def cadastrar(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Conta criada com sucesso! Aguarde a aprovação do administrador para acessar o sistema.')
            return redirect('login')
    else:
        form = CustomUserCreationForm()

    return render(request, 'agendamentos/cadastrar.html', {'form': form})


# --- HOME / DASHBOARD ---

@aprovado_required
def home(request):
    busca = request.GET.get('busca', '').strip()
    lab_id = request.GET.get('laboratorio', '')
    status_filtro = request.GET.get('status', '')
    software_id = request.GET.get('software', '')

    agendamentos_futuros = Agendamento.objects.filter(
        status='CONFIRMADO',
        data_hora_fim__gte=timezone.now()
    ).order_by('data_hora_inicio')

    computadores = Computador.objects.select_related('laboratorio').prefetch_related(
        'softwares',
        Prefetch('agendamentos', queryset=agendamentos_futuros, to_attr='reservas_ativas')
    )

    if busca:
        computadores = computadores.filter(
            Q(identificador__icontains=busca) | Q(laboratorio__nome__icontains=busca)
        )
    if lab_id.isdigit():
        computadores = computadores.filter(laboratorio_id=lab_id)
    if status_filtro in dict(Computador.STATUS_CHOICES):
        computadores = computadores.filter(status=status_filtro)
    if software_id.isdigit():
        # O join com softwares duplica linhas quando a máquina tem mais de um
        # software; distinct() evita a mesma máquina aparecer várias vezes.
        computadores = computadores.filter(softwares__id=software_id).distinct()

    context = {
        'computadores': _paginar(request, computadores),
        'laboratorios': Laboratorio.objects.all(),
        'softwares': Software.objects.all(),
        'status_choices': Computador.STATUS_CHOICES,
        'is_gestor': perfil_e_gestor(request.user),
        'busca': busca,
        'lab_id': lab_id,
        'status_filtro': status_filtro,
        'software_id': software_id,
    }
    return render(request, 'agendamentos/home.html', context)


# --- GESTÃO DE LABORATÓRIOS ---

@gestor_required
def cadastrar_laboratorio(request):
    if request.method == 'POST':
        form = LaboratorioForm(request.POST)
        if form.is_valid():
            laboratorio = form.save()
            messages.success(request, f'Laboratório "{laboratorio.nome}" cadastrado com sucesso!')
            return redirect('listar_laboratorios')
    else:
        form = LaboratorioForm()

    return render(request, 'agendamentos/cadastrar_laboratorio.html', {'form': form})


@gestor_required
def listar_laboratorios(request):
    laboratorios = Laboratorio.objects.annotate(total_maquinas=Count('computadores')).order_by('nome')
    return render(request, 'agendamentos/laboratorios.html', {'laboratorios': laboratorios})


@gestor_required
def editar_laboratorio(request, laboratorio_id):
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


@admin_required
@require_POST
def excluir_laboratorio(request, laboratorio_id):
    laboratorio = get_object_or_404(Laboratorio, id=laboratorio_id)

    if laboratorio.computadores.exists():
        messages.error(
            request,
            f'O laboratório "{laboratorio.nome}" ainda possui máquinas cadastradas e não pode ser excluído.'
        )
        return redirect('listar_laboratorios')

    nome = laboratorio.nome
    laboratorio.delete()
    messages.success(request, f'Laboratório "{nome}" excluído.')
    return redirect('listar_laboratorios')


# --- GESTÃO DE COMPUTADORES ---

@gestor_required
def cadastrar_computador(request):
    if request.method == 'POST':
        form = ComputadorForm(request.POST)
        if form.is_valid():
            computador = form.save()
            messages.success(request, f'Máquina {computador.identificador} cadastrada com sucesso!')
            return redirect('listar_computadores')
    else:
        form = ComputadorForm()

    return render(request, 'agendamentos/cadastrar_computador.html', {'form': form})


@gestor_required
def editar_computador(request, computador_id):
    computador = get_object_or_404(Computador, id=computador_id)

    if request.method == 'POST':
        form = ComputadorForm(request.POST, instance=computador)
        if form.is_valid():
            form.save()
            messages.success(request, f'Máquina {computador.identificador} atualizada com sucesso!')
            return redirect('listar_computadores')
    else:
        form = ComputadorForm(instance=computador)

    return render(request, 'agendamentos/editar_computador.html', {'form': form, 'computador': computador})


@gestor_required
def listar_computadores(request):
    computadores = Computador.objects.select_related('laboratorio').prefetch_related('softwares')
    return render(request, 'agendamentos/computadores.html', {
        'computadores': _paginar(request, computadores),
    })


# --- INVENTÁRIO DE SOFTWARES ---

@gestor_required
def listar_softwares(request):
    if request.method == 'POST':
        form = SoftwareForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Software cadastrado com sucesso!')
            return redirect('listar_softwares')
    else:
        form = SoftwareForm()

    softwares = Software.objects.annotate(total_maquinas=Count('computadores'))
    return render(request, 'agendamentos/softwares.html', {'softwares': softwares, 'form': form})


@admin_required
@require_POST
def excluir_software(request, software_id):
    software = get_object_or_404(Software, id=software_id)
    nome = str(software)
    software.delete()
    messages.success(request, f'Software "{nome}" removido do inventário.')
    return redirect('listar_softwares')


# --- SOLICITAÇÕES DE INSTALAÇÃO DE PROGRAMAS ---

@aprovado_required
def criar_solicitacao_instalacao(request, computador_id=None):
    computador = get_object_or_404(Computador, id=computador_id) if computador_id else None

    if request.method == 'POST':
        form = SolicitacaoInstalacaoForm(request.POST, computador=computador)
        if form.is_valid():
            solicitacao = form.save(commit=False)
            solicitacao.usuario = request.user
            solicitacao.computador = computador
            if computador:
                solicitacao.laboratorio = computador.laboratorio
            solicitacao.save()
            messages.success(
                request,
                f'Solicitação enviada para a equipe técnica ({solicitacao.destino_display()}).'
            )
            return redirect('listar_solicitacoes')
    else:
        form = SolicitacaoInstalacaoForm(computador=computador)

    return render(request, 'agendamentos/solicitar_instalacao.html', {'form': form, 'computador': computador})


@aprovado_required
def listar_solicitacoes(request):
    is_gestor = perfil_e_gestor(request.user)
    status_filtro = request.GET.get('status', '')

    solicitacoes = SolicitacaoInstalacao.objects.select_related(
        'usuario', 'computador', 'computador__laboratorio', 'laboratorio', 'atendido_por'
    )
    if not is_gestor:
        solicitacoes = solicitacoes.filter(usuario=request.user)

    # Uma única query agregada no lugar dos cinco COUNT separados.
    contagens = solicitacoes.aggregate(
        total=Count('id'),
        pendente=Count('id', filter=Q(status='PENDENTE')),
        andamento=Count('id', filter=Q(status='EM_ANDAMENTO')),
        concluido=Count('id', filter=Q(status='CONCLUIDO')),
        rejeitado=Count('id', filter=Q(status='REJEITADO')),
    )

    if status_filtro in dict(SolicitacaoInstalacao.STATUS_CHOICES):
        solicitacoes = solicitacoes.filter(status=status_filtro)

    return render(request, 'agendamentos/solicitacoes_list.html', {
        'solicitacoes': _paginar(request, solicitacoes),
        'is_gestor': is_gestor,
        'status_counts': contagens,
        'status_filtro': status_filtro,
        'status_choices': SolicitacaoInstalacao.STATUS_CHOICES,
    })


@gestor_required
@require_POST
def atualizar_status_solicitacao(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoInstalacao, id=solicitacao_id)
    novo_status = request.POST.get('novo_status', '')

    # Sem esta validação qualquer string vinda do cliente era gravada no banco.
    if novo_status not in dict(SolicitacaoInstalacao.STATUS_CHOICES):
        messages.error(request, 'Status inválido.')
        return redirect('listar_solicitacoes')

    solicitacao.status = novo_status
    solicitacao.atendido_por = request.user
    solicitacao.save(update_fields=['status', 'atendido_por', 'data_atualizacao'])
    messages.success(
        request,
        f'Solicitação de "{solicitacao.software_nome}" marcada como {solicitacao.get_status_display()}.'
    )
    return redirect('listar_solicitacoes')


@aprovado_required
@require_POST
def cancelar_solicitacao(request, solicitacao_id):
    """Permite ao próprio solicitante retirar uma solicitação ainda não atendida."""
    solicitacao = get_object_or_404(SolicitacaoInstalacao, id=solicitacao_id, usuario=request.user)

    if solicitacao.status != 'PENDENTE':
        messages.error(request, 'Esta solicitação já está sendo atendida e não pode mais ser retirada.')
        return redirect('listar_solicitacoes')

    software = solicitacao.software_nome
    solicitacao.delete()
    messages.success(request, f'Solicitação de "{software}" retirada.')
    return redirect('listar_solicitacoes')


# --- RESERVAS E AGENDAMENTOS ---

@aprovado_required
def criar_agendamento(request, computador_id):
    computador = get_object_or_404(Computador.objects.select_related('laboratorio'), id=computador_id)

    if not computador.disponivel:
        messages.error(
            request,
            f'A máquina {computador.identificador} está "{computador.get_status_display()}" e não aceita reservas.'
        )
        return redirect('home')

    reservas_existentes = Agendamento.objects.filter(
        computador=computador,
        status='CONFIRMADO',
        data_hora_fim__gte=timezone.now()
    ).order_by('data_hora_inicio')

    reservas_json = [
        {
            'from': timezone.localtime(r.data_hora_inicio).strftime('%Y-%m-%d %H:%M'),
            'to': timezone.localtime(r.data_hora_fim).strftime('%Y-%m-%d %H:%M'),
        }
        for r in reservas_existentes
    ]

    if request.method == 'POST':
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            inicio = form.cleaned_data['data_hora_inicio']
            fim = form.cleaned_data['data_hora_fim']

            # A verificação de conflito e a gravação precisam acontecer sob o
            # mesmo lock: sem isso, duas reservas simultâneas para o mesmo
            # horário passavam as duas pela checagem e ambas eram gravadas.
            with transaction.atomic():
                computador_travado = Computador.objects.select_for_update().get(pk=computador.pk)

                conflito = Agendamento.objects.filter(
                    computador=computador_travado,
                    status='CONFIRMADO',
                    data_hora_inicio__lt=fim,
                    data_hora_fim__gt=inicio,
                ).exists()

                if conflito:
                    messages.error(request, 'Este computador já está reservado nesse horário. Escolha outro intervalo.')
                else:
                    agendamento = form.save(commit=False)
                    agendamento.usuario = request.user
                    agendamento.computador = computador_travado

                    horas = Decimal((fim - inicio).total_seconds()) / Decimal(3600)
                    agendamento.valor_total = (horas * computador_travado.valor_hora).quantize(
                        Decimal('0.01'), rounding=ROUND_HALF_UP
                    )
                    agendamento.save()

                    messages.success(
                        request,
                        f'Agendamento confirmado para {computador.identificador}! '
                        f'Valor total: R$ {agendamento.valor_total}'
                    )
                    return redirect('meus_agendamentos')
    else:
        form = AgendamentoForm()

    return render(request, 'agendamentos/agendar.html', {
        'form': form,
        'computador': computador,
        'reservas_existentes': reservas_existentes,
        'reservas_json': reservas_json,
    })


@aprovado_required
def meus_agendamentos(request):
    agora = timezone.now()
    base = Agendamento.objects.filter(usuario=request.user).select_related('computador', 'computador__laboratorio')

    proximos = base.filter(status='CONFIRMADO', data_hora_fim__gte=agora).order_by('data_hora_inicio')
    historico = base.filter(Q(status='CANCELADO') | Q(data_hora_fim__lt=agora)).order_by('-data_hora_inicio')

    total_gasto = base.filter(status='CONFIRMADO').aggregate(t=Sum('valor_total'))['t'] or Decimal('0.00')

    return render(request, 'agendamentos/meus_agendamentos.html', {
        'proximos': proximos,
        'historico': _paginar(request, historico),
        'total_gasto': total_gasto,
        'agora': agora,
    })


@admin_required
def gerenciar_agendamentos(request):
    busca = request.GET.get('busca', '').strip()
    status_filtro = request.GET.get('status', '')
    periodo = request.GET.get('periodo', '')
    agora = timezone.now()

    agendamentos = Agendamento.objects.select_related(
        'usuario', 'computador', 'computador__laboratorio'
    ).order_by('-data_hora_inicio')

    if busca:
        agendamentos = agendamentos.filter(
            Q(usuario__username__icontains=busca) |
            Q(usuario__email__icontains=busca) |
            Q(computador__identificador__icontains=busca)
        )

    if status_filtro in dict(Agendamento.STATUS_CHOICES):
        agendamentos = agendamentos.filter(status=status_filtro)

    if periodo == 'futuros':
        agendamentos = agendamentos.filter(data_hora_fim__gte=agora)
    elif periodo == 'passados':
        agendamentos = agendamentos.filter(data_hora_fim__lt=agora)

    return render(request, 'agendamentos/gerenciar_agendamentos.html', {
        'agendamentos': _paginar(request, agendamentos),
        'busca': busca,
        'status_filtro': status_filtro,
        'periodo': periodo,
        'agora': agora,
    })


@admin_required
def dashboard_financeiro(request):
    # Uma query agregada por laboratório, no lugar de duas queries por
    # laboratório dentro de um laço (N+1).
    summary = Laboratorio.objects.annotate(
        maquinas=Count('computadores', distinct=True),
        agendamentos=Count(
            'computadores__agendamentos',
            filter=Q(computadores__agendamentos__status='CONFIRMADO'),
            distinct=True,
        ),
        receita=Sum(
            'computadores__agendamentos__valor_total',
            filter=Q(computadores__agendamentos__status='CONFIRMADO'),
        ),
    ).order_by('nome')

    maquinas = Computador.objects.select_related('laboratorio').annotate(
        total_agendamentos=Count('agendamentos', filter=Q(agendamentos__status='CONFIRMADO')),
        receita=Sum('agendamentos__valor_total', filter=Q(agendamentos__status='CONFIRMADO')),
    ).order_by('-receita', 'laboratorio__nome', 'identificador')

    confirmados = Agendamento.objects.filter(status='CONFIRMADO')
    totais = confirmados.aggregate(
        receita=Sum('valor_total'),
        reservas=Count('id'),
    )

    horas_reservadas = sum(
        ((a.data_hora_fim - a.data_hora_inicio).total_seconds() / 3600)
        for a in confirmados.only('data_hora_inicio', 'data_hora_fim')
    )

    por_finalidade = (
        confirmados.values('finalidade')
        .annotate(total=Count('id'), receita=Sum('valor_total'))
        .order_by('-total')
    )
    rotulos_finalidade = dict(Agendamento.FINALIDADE_CHOICES)
    for linha in por_finalidade:
        linha['rotulo'] = rotulos_finalidade.get(linha['finalidade'], linha['finalidade'])

    return render(request, 'agendamentos/dashboard_financeiro.html', {
        'summary': summary,
        'maquinas': maquinas,
        'total_geral': totais['receita'] or Decimal('0.00'),
        'total_reservas': totais['reservas'] or 0,
        'horas_reservadas': horas_reservadas,
        'por_finalidade': por_finalidade,
    })


@login_required
@require_POST
def cancelar_agendamento(request, agendamento_id):
    """Cancela uma reserva.

    Era uma view GET acessível por link, o que a tornava disparável por
    CSRF (bastava fazer a vítima carregar a URL). Agora exige POST com token.
    """
    agendamento = get_object_or_404(
        Agendamento.objects.select_related('computador', 'usuario'), id=agendamento_id
    )
    destino = 'gerenciar_agendamentos' if request.POST.get('origem') == 'admin' else 'meus_agendamentos'

    if agendamento.usuario_id != request.user.id and not perfil_e_admin(request.user):
        messages.error(request, 'Você não tem permissão para cancelar este agendamento.')
        return redirect('meus_agendamentos')

    if not agendamento.pode_ser_cancelado_por(request.user):
        if agendamento.status == 'CANCELADO':
            messages.error(request, 'Este agendamento já estava cancelado.')
        else:
            messages.error(request, 'Reservas que já terminaram não podem ser canceladas.')
        return redirect(destino)

    agendamento.cancelar(request.user)
    messages.success(
        request,
        f'Reserva de {agendamento.computador.identificador} '
        f'({timezone.localtime(agendamento.data_hora_inicio).strftime("%d/%m/%Y %H:%M")}) cancelada.'
    )
    return redirect(destino)


# --- GERENCIAMENTO DE USUÁRIOS E PERMISSÕES ---

@admin_required
def liberar_usuarios(request):
    perfis = Perfil.objects.select_related('usuario')
    return render(request, 'agendamentos/liberar_usuarios.html', {
        'pendentes': perfis.filter(aprovado=False).order_by('-usuario__date_joined'),
        'aprovados': perfis.filter(aprovado=True).order_by('usuario__username'),
    })


@admin_required
@require_POST
def aprovar_usuario(request, perfil_id):
    perfil = get_object_or_404(Perfil.objects.select_related('usuario'), id=perfil_id)
    perfil.aprovado = True
    perfil.save(update_fields=['aprovado'])
    messages.success(request, f'Usuário {perfil.usuario.username} liberado com sucesso!')
    return redirect('liberar_usuarios')


@admin_required
@require_POST
def revogar_usuario(request, perfil_id):
    perfil = get_object_or_404(Perfil.objects.select_related('usuario'), id=perfil_id)

    if perfil.usuario_id == request.user.id:
        messages.error(request, 'Você não pode revogar o próprio acesso.')
        return redirect('liberar_usuarios')

    if perfil.usuario.is_superuser:
        messages.error(request, 'O acesso de um superusuário não pode ser revogado por aqui.')
        return redirect('liberar_usuarios')

    perfil.aprovado = False
    perfil.save(update_fields=['aprovado'])
    messages.success(request, f'Acesso de {perfil.usuario.username} revogado.')
    return redirect('liberar_usuarios')


@admin_required
def gerenciar_usuarios(request):
    busca = request.GET.get('busca', '').strip()
    usuarios = User.objects.select_related('perfil').order_by('-date_joined')

    if busca:
        usuarios = usuarios.filter(
            Q(username__icontains=busca) |
            Q(email__icontains=busca) |
            Q(first_name__icontains=busca) |
            Q(last_name__icontains=busca)
        )

    return render(request, 'agendamentos/gerenciar_usuarios.html', {
        'usuarios': _paginar(request, usuarios),
        'busca': busca,
    })


@admin_required
def editar_usuario(request, user_id):
    usuario_obj = get_object_or_404(User, id=user_id)
    perfil, _ = Perfil.objects.get_or_create(usuario=usuario_obj)

    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario_obj)
        if form.is_valid():
            novo_tipo = form.cleaned_data['tipo']
            aprovado = form.cleaned_data['aprovado']

            # Evita que o administrador logado se rebaixe e perca o acesso.
            if usuario_obj.id == request.user.id and not request.user.is_superuser:
                if novo_tipo != 'ADMIN' or not aprovado:
                    messages.error(request, 'Você não pode remover o próprio acesso de administrador.')
                    return redirect('editar_usuario', user_id=user_id)

            user_saved = form.save()
            perfil.tipo = novo_tipo
            perfil.aprovado = aprovado
            perfil.save(update_fields=['tipo', 'aprovado'])
            messages.success(request, f'Usuário {user_saved.username} atualizado com sucesso!')
            return redirect('gerenciar_usuarios')
    else:
        form = EditarUsuarioForm(instance=usuario_obj, initial={
            'tipo': perfil.tipo,
            'aprovado': perfil.aprovado,
        })

    return render(request, 'agendamentos/editar_usuario.html', {'form': form, 'usuario_obj': usuario_obj})


@admin_required
@require_POST
def deletar_usuario(request, user_id):
    usuario_obj = get_object_or_404(User, id=user_id)

    if usuario_obj.id == request.user.id:
        messages.error(request, 'Você não pode excluir sua própria conta.')
        return redirect('gerenciar_usuarios')

    if usuario_obj.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Apenas um superusuário pode excluir outro superusuário.')
        return redirect('gerenciar_usuarios')

    username = usuario_obj.username
    usuario_obj.delete()
    messages.success(request, f'Usuário {username} removido com sucesso.')
    return redirect('gerenciar_usuarios')


@login_required
def alterar_senha(request):
    """Troca de senha pelo próprio usuário logado."""
    if request.method == 'POST':
        form = AlterarSenhaForm(request.user, request.POST)
        if form.is_valid():
            usuario = form.save()
            # Sem isto, trocar a própria senha derruba a sessão atual (o hash
            # de autenticação da sessão muda junto com a senha).
            update_session_auth_hash(request, usuario)
            messages.success(request, 'Senha alterada com sucesso!')
            return redirect('home')
    else:
        form = AlterarSenhaForm(request.user)

    return render(request, 'agendamentos/alterar_senha.html', {'form': form})


@admin_required
def resetar_senha_usuario(request, user_id):
    """Permite a um administrador redefinir a senha de outro usuário.

    Não exige a senha atual: é justamente o caso de alguém que a esqueceu e
    não tem mais como informá-la.
    """
    usuario_obj = get_object_or_404(User, id=user_id)

    if usuario_obj.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Apenas um superusuário pode redefinir a senha de outro superusuário.')
        return redirect('gerenciar_usuarios')

    if request.method == 'POST':
        form = ResetarSenhaForm(usuario_obj, request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Senha de {usuario_obj.username} redefinida com sucesso. '
                'Informe a nova senha a essa pessoa por um canal seguro.'
            )
            return redirect('editar_usuario', user_id=usuario_obj.id)
    else:
        form = ResetarSenhaForm(usuario_obj)

    return render(request, 'agendamentos/resetar_senha.html', {'form': form, 'usuario_obj': usuario_obj})


@admin_required
def permissoes_acesso(request):
    if request.method == 'POST':
        perfil = get_object_or_404(
            Perfil.objects.select_related('usuario'), id=request.POST.get('perfil_id')
        )
        novo_tipo = request.POST.get('novo_tipo', '')

        # Sem validação, qualquer valor enviado pelo cliente era gravado no
        # campo `tipo` — inclusive valores fora de TIPO_CHOICES.
        if novo_tipo not in dict(Perfil.TIPO_CHOICES):
            messages.error(request, 'Tipo de perfil inválido.')
            return redirect('permissoes_acesso')

        if perfil.usuario_id == request.user.id and not request.user.is_superuser:
            messages.error(request, 'Você não pode alterar o próprio nível de permissão.')
            return redirect('permissoes_acesso')

        if perfil.usuario.is_superuser and not request.user.is_superuser:
            messages.error(request, 'Apenas um superusuário pode alterar o perfil de outro superusuário.')
            return redirect('permissoes_acesso')

        perfil.tipo = novo_tipo
        perfil.save(update_fields=['tipo'])
        messages.success(request, f'Permissão de {perfil.usuario.username} atualizada para {perfil.get_tipo_display()}.')
        return redirect('permissoes_acesso')

    perfis = Perfil.objects.select_related('usuario').order_by('tipo', 'usuario__username')
    return render(request, 'agendamentos/permissoes_acesso.html', {
        'perfis': _paginar(request, perfis),
        'tipo_choices': Perfil.TIPO_CHOICES,
    })
