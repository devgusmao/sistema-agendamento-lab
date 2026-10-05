from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, DurationField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import emails
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
    TipoAgendamentoForm,
)
from .models import (
    Agendamento,
    Computador,
    Laboratorio,
    Perfil,
    Software,
    SolicitacaoInstalacao,
    TipoAgendamento,
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


def _cancelar_reservas_futuras(computador, por_usuario):
    """Cancela reservas confirmadas que ainda não terminaram (máquina fora de operação)."""
    pendentes = list(
        Agendamento.objects.select_for_update()
        .select_related('usuario', 'computador__laboratorio')
        .filter(computador=computador, status='CONFIRMADO', data_hora_fim__gt=timezone.now())
    )
    for ag in pendentes:
        ag.cancelar(por_usuario)
        emails.notificar_reserva_cancelada(
            ag, f'a máquina entrou em "{computador.get_status_display()}".'
        )
    return len(pendentes)


@gestor_required
def editar_computador(request, computador_id):
    computador = get_object_or_404(Computador, id=computador_id)

    if request.method == 'POST':
        form = ComputadorForm(request.POST, instance=computador)
        if form.is_valid():
            with transaction.atomic():
                computador = form.save()
                canceladas = 0
                if not computador.disponivel:
                    canceladas = _cancelar_reservas_futuras(computador, request.user)
            msg = f'Máquina {computador.identificador} atualizada com sucesso!'
            if canceladas:
                msg += f' {canceladas} reserva(s) futura(s) cancelada(s) e usuários avisados.'
            messages.success(request, msg)
            return redirect('listar_computadores')
    else:
        form = ComputadorForm(instance=computador)

    return render(request, 'agendamentos/editar_computador.html', {'form': form, 'computador': computador})


@admin_required
@require_POST
def excluir_computador(request, computador_id):
    computador = get_object_or_404(Computador, id=computador_id)

    if computador.agendamentos.exists():
        messages.error(
            request,
            f'A máquina {computador.identificador} possui reservas no histórico e não pode ser excluída. '
            'Marque-a como "Inativo" para retirá-la de uso.'
        )
        return redirect('listar_computadores')

    identificador = computador.identificador
    computador.delete()
    messages.success(request, f'Máquina {identificador} excluída.')
    return redirect('listar_computadores')


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

    if computador is not None and computador.status == 'INATIVO':
        messages.error(request, f'A máquina {computador.identificador} está inativa e não recebe solicitações.')
        return redirect('home')

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
        cancelado=Count('id', filter=Q(status='CANCELADO')),
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

    if not solicitacao.pode_mudar_para(novo_status):
        messages.error(
            request,
            f'Não é possível mudar uma solicitação "{solicitacao.get_status_display()}" '
            f'para "{dict(SolicitacaoInstalacao.STATUS_CHOICES)[novo_status]}".'
        )
        return redirect('listar_solicitacoes')

    aviso = ''
    with transaction.atomic():
        solicitacao.status = novo_status
        solicitacao.atendido_por = request.user
        solicitacao.save(update_fields=['status', 'atendido_por', 'data_atualizacao'])
        if novo_status == 'CONCLUIDO':
            aviso = _registrar_instalacao_no_inventario(solicitacao)

    messages.success(
        request,
        f'Solicitação de "{solicitacao.software_nome}" marcada como {solicitacao.get_status_display()}.{aviso}'
    )
    return redirect('listar_solicitacoes')


def _registrar_instalacao_no_inventario(solicitacao):
    """Ao concluir, vincula o software à máquina solicitada, se ele existir no inventário."""
    if not solicitacao.computador_id:
        return ' Atualize o inventário da máquina onde o software foi instalado.'
    nome = solicitacao.software_nome.strip().lower()
    software = next((sw for sw in Software.objects.all() if str(sw).lower() == nome), None)
    if software is None:
        return ' Software não encontrado no inventário: cadastre-o e vincule à máquina.'
    solicitacao.computador.softwares.add(software)
    return f' "{software}" adicionado ao inventário de {solicitacao.computador.identificador}.'


@aprovado_required
@require_POST
def cancelar_solicitacao(request, solicitacao_id):
    """Permite ao próprio solicitante retirar uma solicitação ainda não atendida."""
    solicitacao = get_object_or_404(SolicitacaoInstalacao, id=solicitacao_id, usuario=request.user)

    if solicitacao.status != 'PENDENTE':
        messages.error(request, 'Esta solicitação já está sendo atendida e não pode mais ser retirada.')
        return redirect('listar_solicitacoes')

    solicitacao.status = 'CANCELADO'
    solicitacao.save(update_fields=['status', 'data_atualizacao'])
    messages.success(request, f'Solicitação de "{solicitacao.software_nome}" retirada.')
    return redirect('listar_solicitacoes')


# --- RESERVAS E AGENDAMENTOS ---

def _reservas_do_computador(computador):
    return Agendamento.objects.filter(
        computador=computador, status='CONFIRMADO', data_hora_fim__gte=timezone.now()
    ).order_by('data_hora_inicio')


@aprovado_required
def criar_agendamento(request, computador_id):
    computador = get_object_or_404(Computador.objects.select_related('laboratorio'), id=computador_id)

    if not computador.disponivel:
        messages.error(
            request,
            f'A máquina {computador.identificador} está "{computador.get_status_display()}" e não aceita reservas.'
        )
        return redirect('home')

    if request.method == 'POST':
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            inicio = form.cleaned_data['data_hora_inicio']
            fim = form.cleaned_data['data_hora_fim']

            # A verificação de conflito e a gravação precisam acontecer sob o
            # mesmo lock: sem isso, duas reservas simultâneas para o mesmo
            # horário passavam as duas pela checagem e ambas eram gravadas.
            with transaction.atomic():
                computador_travado = Computador.objects.select_for_update(of=('self',)).select_related('laboratorio').get(pk=computador.pk)
                # Trava também o usuário, para serializar as checagens por usuário.
                User.objects.select_for_update().get(pk=request.user.pk)

                erro = None
                if not computador_travado.disponivel:
                    erro = 'Esta máquina deixou de estar disponível para reservas.'
                elif Agendamento.objects.filter(
                    computador=computador_travado, status='CONFIRMADO',
                    data_hora_inicio__lt=fim, data_hora_fim__gt=inicio,
                ).exists():
                    erro = 'Este computador já está reservado nesse horário. Escolha outro intervalo.'
                elif Agendamento.objects.filter(
                    usuario=request.user, status='CONFIRMADO',
                    data_hora_inicio__lt=fim, data_hora_fim__gt=inicio,
                ).exists():
                    erro = 'Você já tem outra reserva nesse mesmo horário.'
                elif Agendamento.objects.filter(
                    usuario=request.user, status='CONFIRMADO', data_hora_fim__gt=timezone.now(),
                ).count() >= settings.AGENDAMENTO_MAX_RESERVAS_ATIVAS:
                    erro = (
                        f'Limite de {settings.AGENDAMENTO_MAX_RESERVAS_ATIVAS} reservas ativas atingido. '
                        'Cancele ou aguarde o término de uma reserva para agendar outra.'
                    )

                if erro:
                    messages.error(request, erro)
                else:
                    agendamento = form.save(commit=False)
                    agendamento.usuario = request.user
                    agendamento.computador = computador_travado
                    agendamento.valor_hora_aplicado, agendamento.valor_total = agendamento.tipo.calcular_valor(
                        inicio, fim
                    )
                    agendamento.save()
                    emails.notificar_reserva_confirmada(agendamento)

                    messages.success(
                        request,
                        f'Agendamento confirmado para {computador.identificador}! '
                        f'Valor total: R$ {agendamento.valor_total}'
                    )
                    return redirect('meus_agendamentos')
    else:
        form = AgendamentoForm()

    # Calculado depois do POST para refletir reservas feitas por outros enquanto o form era preenchido.
    reservas_existentes = _reservas_do_computador(computador)
    reservas_json = [
        {
            'from': timezone.localtime(r.data_hora_inicio).strftime('%Y-%m-%d %H:%M'),
            'to': timezone.localtime(r.data_hora_fim).strftime('%Y-%m-%d %H:%M'),
        }
        for r in reservas_existentes
    ]

    taxas = {str(t.pk): str(t.taxa_hora()) for t in TipoAgendamento.objects.filter(ativo=True)}
    duracoes = {str(t.pk): t.duracao_maxima() for t in TipoAgendamento.objects.filter(ativo=True)}

    return render(request, 'agendamentos/agendar.html', {
        'taxas_json': taxas,
        'duracoes_json': duracoes,
        'form': form,
        'computador': computador,
        'reservas_existentes': reservas_existentes,
        'reservas_json': reservas_json,
    })


@aprovado_required
def meus_agendamentos(request):
    agora = timezone.now()
    base = Agendamento.objects.filter(usuario=request.user).select_related('computador', 'computador__laboratorio', 'tipo')

    proximos = base.filter(status='CONFIRMADO', data_hora_fim__gte=agora).order_by('data_hora_inicio')
    historico = base.filter(Q(status='CANCELADO') | Q(data_hora_fim__lt=agora)).order_by('-data_hora_inicio')

    confirmadas = base.filter(status='CONFIRMADO')
    total_gasto = confirmadas.filter(data_hora_fim__lte=agora).aggregate(t=Sum('valor_total'))['t'] or Decimal('0.00')
    total_previsto = confirmadas.filter(data_hora_fim__gt=agora).aggregate(t=Sum('valor_total'))['t'] or Decimal('0.00')

    return render(request, 'agendamentos/meus_agendamentos.html', {
        'proximos': proximos,
        'historico': _paginar(request, historico),
        'total_gasto': total_gasto,
        'total_previsto': total_previsto,
        'agora': agora,
    })


@admin_required
def gerenciar_agendamentos(request):
    busca = request.GET.get('busca', '').strip()
    status_filtro = request.GET.get('status', '')
    periodo = request.GET.get('periodo', '')
    agora = timezone.now()

    agendamentos = Agendamento.objects.select_related(
        'usuario', 'computador', 'computador__laboratorio', 'tipo'
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


def _parse_data(valor):
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


@admin_required
def dashboard_financeiro(request):
    agora = timezone.now()
    de = _parse_data(request.GET.get('de'))
    ate = _parse_data(request.GET.get('ate'))
    lab_id = request.GET.get('laboratorio', '')

    # Período aplicado sobre o início da reserva, no fuso local.
    def periodo_q(prefixo=''):
        q = Q()
        if de:
            q &= Q(**{f'{prefixo}data_hora_inicio__date__gte': de})
        if ate:
            q &= Q(**{f'{prefixo}data_hora_inicio__date__lte': ate})
        return q

    confirmado = Q(status='CONFIRMADO')
    realizada_q = confirmado & Q(data_hora_fim__lte=agora)
    prevista_q = confirmado & Q(data_hora_fim__gt=agora)

    base = Agendamento.objects.filter(periodo_q())
    if lab_id.isdigit():
        base = base.filter(computador__laboratorio_id=lab_id)

    totais = base.aggregate(
        realizada=Sum('valor_total', filter=realizada_q),
        prevista=Sum('valor_total', filter=prevista_q),
        cancelado=Sum('valor_total', filter=Q(status='CANCELADO')),
        reservas=Count('id', filter=confirmado),
        canceladas=Count('id', filter=Q(status='CANCELADO')),
        duracao=Sum(
            ExpressionWrapper(F('data_hora_fim') - F('data_hora_inicio'), output_field=DurationField()),
            filter=confirmado,
        ),
    )
    zero = Decimal('0.00')
    receita_realizada = totais['realizada'] or zero
    receita_prevista = totais['prevista'] or zero
    total_geral = receita_realizada + receita_prevista
    total_reservas = totais['reservas'] or 0
    total_canceladas = totais['canceladas'] or 0
    horas_reservadas = round(totais['duracao'].total_seconds() / 3600, 1) if totais['duracao'] else 0
    ticket_medio = (total_geral / total_reservas).quantize(Decimal('0.01')) if total_reservas else zero
    solicitadas = total_reservas + total_canceladas
    taxa_cancelamento = round(100 * total_canceladas / solicitadas, 1) if solicitadas else 0

    ag = 'computadores__agendamentos__'
    periodo_lab = periodo_q(ag)
    por_lab = Laboratorio.objects.annotate(
        maquinas=Count('computadores', distinct=True),
        agendamentos=Count(f'{ag}id', filter=periodo_lab & Q(**{f'{ag}status': 'CONFIRMADO'}), distinct=True),
        receita=Sum(f'{ag}valor_total', filter=periodo_lab & Q(**{f'{ag}status': 'CONFIRMADO'})),
    ).order_by('nome')
    if lab_id.isdigit():
        por_lab = por_lab.filter(id=lab_id)

    ag_pc = 'agendamentos__'
    maquinas = Computador.objects.select_related('laboratorio').annotate(
        total_agendamentos=Count(f'{ag_pc}id', filter=periodo_q(ag_pc) & Q(**{f'{ag_pc}status': 'CONFIRMADO'})),
        receita=Sum(f'{ag_pc}valor_total', filter=periodo_q(ag_pc) & Q(**{f'{ag_pc}status': 'CONFIRMADO'})),
    ).order_by(F('receita').desc(nulls_last=True), 'laboratorio__nome', 'identificador')
    if lab_id.isdigit():
        maquinas = maquinas.filter(laboratorio_id=lab_id)

    confirmados = base.filter(confirmado)
    por_finalidade = list(
        confirmados.values('tipo__nome').annotate(total=Count('id'), receita=Sum('valor_total')).order_by('-total')
    )
    for linha in por_finalidade:
        linha['rotulo'] = linha['tipo__nome']

    por_mes = list(
        confirmados.annotate(mes=TruncMonth('data_hora_inicio'))
        .values('mes').annotate(total=Count('id'), receita=Sum('valor_total')).order_by('-mes')[:12]
    )

    return render(request, 'agendamentos/dashboard_financeiro.html', {
        'summary': por_lab,
        'maquinas': maquinas,
        'total_geral': total_geral,
        'receita_realizada': receita_realizada,
        'receita_prevista': receita_prevista,
        'valor_cancelado': totais['cancelado'] or zero,
        'total_reservas': total_reservas,
        'total_canceladas': total_canceladas,
        'taxa_cancelamento': taxa_cancelamento,
        'ticket_medio': ticket_medio,
        'horas_reservadas': horas_reservadas,
        'por_finalidade': por_finalidade,
        'por_mes': por_mes,
        'laboratorios': Laboratorio.objects.all(),
        'de': de.isoformat() if de else '',
        'ate': ate.isoformat() if ate else '',
        'lab_id': lab_id,
    })


@aprovado_required
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
    if agendamento.usuario_id != request.user.id:
        emails.notificar_reserva_cancelada(agendamento, 'cancelada pela administração.')
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

    if perfil.tipo == 'ADMIN' and not request.user.is_superuser:
        messages.error(request, 'Apenas um superusuário pode revogar o acesso de um administrador.')
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

    if usuario_obj.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Apenas um superusuário pode editar outro superusuário.')
        return redirect('gerenciar_usuarios')

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
    try:
        usuario_obj.delete()
    except ProtectedError:
        messages.error(
            request,
            f'{username} possui reservas no histórico financeiro e não pode ser excluído. '
            'Revogue o acesso em vez de excluir.'
        )
        return redirect('gerenciar_usuarios')
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



# --- TIPOS DE AGENDAMENTO (regras de preço) ---

@admin_required
def listar_tipos_agendamento(request):
    tipos = TipoAgendamento.objects.annotate(total_reservas=Count('agendamentos'))
    return render(request, 'agendamentos/tipos_agendamento.html', {'tipos': tipos})


@admin_required
def salvar_tipo_agendamento(request, tipo_id=None):
    tipo = get_object_or_404(TipoAgendamento, id=tipo_id) if tipo_id else None

    if request.method == 'POST':
        form = TipoAgendamentoForm(request.POST, instance=tipo)
        if form.is_valid():
            salvo = form.save()
            messages.success(
                request,
                f'Tipo "{salvo.nome}" salvo. Reservas já feitas mantêm o valor original.'
            )
            return redirect('listar_tipos_agendamento')
    else:
        form = TipoAgendamentoForm(instance=tipo)

    return render(request, 'agendamentos/form_tipo_agendamento.html', {'form': form, 'tipo': tipo})


@admin_required
@require_POST
def excluir_tipo_agendamento(request, tipo_id):
    tipo = get_object_or_404(TipoAgendamento, id=tipo_id)

    if tipo.agendamentos.exists():
        messages.error(
            request,
            f'O tipo "{tipo.nome}" já foi usado em reservas e não pode ser excluído. Desative-o para retirá-lo de uso.'
        )
        return redirect('listar_tipos_agendamento')

    nome = tipo.nome
    tipo.delete()
    messages.success(request, f'Tipo "{nome}" excluído.')
    return redirect('listar_tipos_agendamento')
