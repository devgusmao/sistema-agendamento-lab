from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import emails, usuarios
from .servicos import catalogo, financeiro, pagamentos, reservas, solicitacoes
from .decorators import admin_required, aprovado_required, gestor_required
from .forms import (
    AgendamentoForm,
    AlterarSenhaForm,
    ComputadorForm,
    ConfiguracaoEmailForm,
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
    ConfiguracaoEmail,
    ConfiguracaoNotificacao,
    Laboratorio,
    LogNotificacao,
    Perfil,
    Software,
    SolicitacaoInstalacao,
    TipoAgendamento,
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
            novo = form.save()
            emails.notificar_novo_cadastro(novo)
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

    computadores = catalogo.buscar_computadores(busca, lab_id, status_filtro, software_id)

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
            with transaction.atomic():
                computador = form.save()
                canceladas = 0
                if not computador.disponivel:
                    canceladas = reservas.cancelar_futuras_da_maquina(computador, request.user)
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
            emails.notificar_solicitacao_nova(solicitacao)
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

    pedidos = SolicitacaoInstalacao.objects.select_related(
        'usuario', 'computador', 'computador__laboratorio', 'laboratorio', 'atendido_por'
    )
    if not is_gestor:
        pedidos = pedidos.filter(usuario=request.user)

    # Uma única query agregada no lugar dos cinco COUNT separados.
    contagens = pedidos.aggregate(
        total=Count('id'),
        pendente=Count('id', filter=Q(status='PENDENTE')),
        andamento=Count('id', filter=Q(status='EM_ANDAMENTO')),
        concluido=Count('id', filter=Q(status='CONCLUIDO')),
        rejeitado=Count('id', filter=Q(status='REJEITADO')),
        cancelado=Count('id', filter=Q(status='CANCELADO')),
    )

    if status_filtro in dict(SolicitacaoInstalacao.STATUS_CHOICES):
        pedidos = pedidos.filter(status=status_filtro)

    return render(request, 'agendamentos/solicitacoes_list.html', {
        'solicitacoes': _paginar(request, pedidos),
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

    try:
        aviso = solicitacoes.atualizar_status(solicitacao, novo_status, request.user)
    except solicitacoes.SolicitacaoRecusada as erro:
        messages.error(request, str(erro))
        return redirect('listar_solicitacoes')

    messages.success(
        request,
        f'Solicitação de "{solicitacao.software_nome}" marcada como {solicitacao.get_status_display()}.{aviso}'
    )
    return redirect('listar_solicitacoes')


@aprovado_required
@require_POST
def cancelar_solicitacao(request, solicitacao_id):
    """Permite ao próprio solicitante retirar uma solicitação ainda não atendida."""
    solicitacao = get_object_or_404(SolicitacaoInstalacao, id=solicitacao_id, usuario=request.user)

    try:
        solicitacoes.retirar(solicitacao)
    except solicitacoes.SolicitacaoRecusada as erro:
        messages.error(request, str(erro))
        return redirect('listar_solicitacoes')
    messages.success(request, f'Solicitação de "{solicitacao.software_nome}" retirada.')
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

    if request.method == 'POST':
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            try:
                agendamento = reservas.reservar(
                    request.user, computador,
                    form.cleaned_data['tipo'], form.cleaned_data['data_hora_inicio'], form.cleaned_data['data_hora_fim'],
                )
            except reservas.ReservaRecusada as erro:
                messages.error(request, str(erro))
            else:
                messages.success(
                    request,
                    f'Agendamento confirmado para {computador.identificador}! '
                    f'Valor total: R$ {agendamento.valor_total}'
                )
                return redirect('meus_agendamentos')
    else:
        form = AgendamentoForm()

    # Calculado depois do POST para refletir reservas feitas por outros enquanto o form era preenchido.
    reservas_existentes = reservas.reservas_futuras_da_maquina(computador)
    reservas_json = [
        {
            'from': timezone.localtime(r.data_hora_inicio).strftime('%Y-%m-%d %H:%M'),
            'to': timezone.localtime(r.data_hora_fim).strftime('%Y-%m-%d %H:%M'),
        }
        for r in reservas_existentes
    ]

    tipos_ativos = TipoAgendamento.objects.filter(ativo=True)
    return render(request, 'agendamentos/agendar.html', {
        'taxas_json': {str(t.pk): str(t.taxa_hora()) for t in tipos_ativos},
        'duracoes_json': {str(t.pk): t.duracao_maxima() for t in tipos_ativos},
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
    totais = financeiro.totais_do_usuario(request.user, agora)

    return render(request, 'agendamentos/meus_agendamentos.html', {
        'proximos': proximos,
        'historico': _paginar(request, historico),
        'total_gasto': totais['gasto'],
        'total_previsto': totais['previsto'],
        'total_a_pagar': totais['a_pagar'],
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


@admin_required
def dashboard_financeiro(request):
    de = financeiro.parse_data(request.GET.get('de'))
    ate = financeiro.parse_data(request.GET.get('ate'))
    lab_id = request.GET.get('laboratorio', '')

    contexto = financeiro.dashboard(de, ate, lab_id)
    contexto.update({
        'laboratorios': Laboratorio.objects.all(),
        'de': de.isoformat() if de else '',
        'ate': ate.isoformat() if ate else '',
        'lab_id': lab_id,
    })
    return render(request, 'agendamentos/dashboard_financeiro.html', contexto)


@aprovado_required
@require_POST
def cancelar_agendamento(request, agendamento_id):
    """Cancela uma reserva. Exige POST com token CSRF (antes era um link GET)."""
    agendamento = get_object_or_404(
        Agendamento.objects.select_related('computador', 'usuario'), id=agendamento_id
    )
    destino = 'gerenciar_agendamentos' if request.POST.get('origem') == 'admin' else 'meus_agendamentos'

    try:
        reservas.cancelar(agendamento, request.user)
    except reservas.CancelamentoRecusado as erro:
        messages.error(request, str(erro))
        return redirect('meus_agendamentos' if erro.sem_permissao else destino)

    texto = (
        f'Reserva de {agendamento.computador.identificador} '
        f'({timezone.localtime(agendamento.data_hora_inicio).strftime("%d/%m/%Y %H:%M")}) cancelada.'
    )
    if agendamento.multa > 0:
        texto += f' Multa por cancelamento fora do prazo: R$ {agendamento.multa}.'
    messages.success(request, texto)
    return redirect(destino)


def _registrar_cobranca(request, agendamento_id, operacao, sucesso):
    agendamento = get_object_or_404(Agendamento.objects.select_related('computador', 'usuario'), id=agendamento_id)
    try:
        operacao(agendamento, request.user)
    except pagamentos.PagamentoRecusado as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, sucesso)
    return redirect('gerenciar_agendamentos')


@admin_required
@require_POST
def registrar_pagamento(request, agendamento_id):
    return _registrar_cobranca(request, agendamento_id, pagamentos.registrar_pagamento, 'Pagamento registrado.')


@admin_required
@require_POST
def registrar_estorno(request, agendamento_id):
    return _registrar_cobranca(request, agendamento_id, pagamentos.registrar_estorno, 'Estorno registrado.')


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
    usuarios.aplicar(perfil, aprovado=True)
    messages.success(request, f'Usuário {perfil.usuario.username} liberado com sucesso!')
    return redirect('liberar_usuarios')


@admin_required
@require_POST
def revogar_usuario(request, perfil_id):
    perfil = get_object_or_404(Perfil.objects.select_related('usuario'), id=perfil_id)

    erro = usuarios.erro_ao_alterar(request.user, perfil.usuario, aprovado=False)
    if erro:
        messages.error(request, erro)
        return redirect('liberar_usuarios')

    usuarios.aplicar(perfil, aprovado=False)
    messages.success(request, f'Acesso de {perfil.usuario.username} revogado.')
    return redirect('liberar_usuarios')


@admin_required
def gerenciar_usuarios(request):
    busca = request.GET.get('busca', '').strip()
    lista = User.objects.select_related('perfil').order_by('-date_joined')

    if busca:
        lista = lista.filter(
            Q(username__icontains=busca) |
            Q(email__icontains=busca) |
            Q(first_name__icontains=busca) |
            Q(last_name__icontains=busca)
        )

    return render(request, 'agendamentos/gerenciar_usuarios.html', {
        'usuarios': _paginar(request, lista),
        'busca': busca,
    })


@admin_required
def editar_usuario(request, user_id):
    usuario_obj = get_object_or_404(User, id=user_id)

    erro = usuarios.erro_superusuario(request.user, usuario_obj, 'editar')
    if erro:
        messages.error(request, erro)
        return redirect('gerenciar_usuarios')

    perfil, _ = Perfil.objects.get_or_create(usuario=usuario_obj)

    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario_obj)
        if form.is_valid():
            novo_tipo = form.cleaned_data['tipo']
            aprovado = form.cleaned_data['aprovado']

            erro = usuarios.erro_ao_alterar(request.user, usuario_obj, tipo=novo_tipo, aprovado=aprovado)
            if erro:
                messages.error(request, erro)
                return redirect('editar_usuario', user_id=user_id)

            with transaction.atomic():
                user_saved = form.save()
                usuarios.aplicar(perfil, tipo=novo_tipo, aprovado=aprovado)
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

    username = usuario_obj.username
    try:
        usuarios.excluir(request.user, usuario_obj)
    except usuarios.ExclusaoRecusada as erro:
        messages.error(request, str(erro))
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

    erro = usuarios.erro_superusuario(request.user, usuario_obj, 'redefinir a senha de')
    if erro:
        messages.error(request, erro)
        return redirect('gerenciar_usuarios')

    if request.method == 'POST':
        form = ResetarSenhaForm(usuario_obj, request.POST)
        if form.is_valid():
            form.save()
            emails.notificar_senha_redefinida(usuario_obj)
            messages.success(
                request,
                f'Senha de {usuario_obj.username} redefinida com sucesso. '
                'Informe a nova senha a essa pessoa por um canal seguro.'
            )
            return redirect('editar_usuario', user_id=usuario_obj.id)
    else:
        form = ResetarSenhaForm(usuario_obj)

    return render(request, 'agendamentos/resetar_senha.html', {'form': form, 'usuario_obj': usuario_obj})


# --- NOTIFICAÇÕES E E-MAIL ---

@admin_required
def notificacoes(request):
    if request.method == 'POST':
        ativos = set(request.POST.getlist('ativos'))
        for slug in emails.EVENTOS:
            ConfiguracaoNotificacao.objects.update_or_create(evento=slug, defaults={'ativo': slug in ativos})
        messages.success(request, 'Preferências de notificação salvas.')
        return redirect('notificacoes')

    eventos = [
        {'slug': slug, 'ev': ev, 'ativo': emails.evento_ativo(slug)}
        for slug, ev in emails.EVENTOS.items()
    ]
    titulos = {slug: ev.titulo for slug, ev in emails.EVENTOS.items()}
    logs = _paginar(request, LogNotificacao.objects.select_related('usuario'))
    for item in logs:
        item.titulo_evento = titulos.get(item.evento, item.evento)
    return render(request, 'agendamentos/notificacoes.html', {
        'eventos': eventos,
        'logs': logs,
        'email_configurado': ConfiguracaoEmail.obter().configurada or bool(settings.EMAIL_HOST_USER),
        'lembrete_horas': settings.AGENDAMENTO_LEMBRETE_HORAS,
    })


@admin_required
def configurar_email(request):
    cfg = ConfiguracaoEmail.obter()
    if request.method == 'POST':
        form = ConfiguracaoEmailForm(request.POST, instance=cfg)
        if form.is_valid():
            cfg = form.save(commit=False)
            if form.cleaned_data['remover_senha']:
                cfg.definir_senha('')
            elif form.cleaned_data['senha']:
                cfg.definir_senha(form.cleaned_data['senha'])
            cfg.atualizado_por = request.user
            cfg.save()
            messages.success(request, 'Configuração de e-mail salva. Use "Enviar e-mail de teste" para validar.')
            return redirect('configurar_email')
    else:
        form = ConfiguracaoEmailForm(instance=cfg)
    return render(request, 'agendamentos/configurar_email.html', {
        'form': form,
        'cfg': cfg,
        'usa_env': not cfg.configurada and bool(settings.EMAIL_HOST_USER),
    })


@admin_required
@require_POST
def testar_email(request):
    if not request.user.email:
        messages.error(request, 'Seu usuário não tem e-mail cadastrado para receber o teste.')
        return redirect('configurar_email')
    ok, erro = emails.enviar_teste(request.user.email)
    if ok:
        messages.success(request, 'E-mail de teste enviado para o seu endereço. Confira a caixa de entrada.')
    else:
        messages.error(request, f'Falha ao enviar ({erro}). Confira a conta, a senha de app e a verificação em duas etapas.')
    return redirect('configurar_email')


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
