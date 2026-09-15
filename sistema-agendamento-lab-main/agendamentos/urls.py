from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # --- PÁGINAS PRINCIPAIS E AUTENTICAÇÃO ---
    path('', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(
        template_name='agendamentos/login.html',
        redirect_authenticated_user=True,
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('cadastrar/', views.cadastrar, name='cadastrar'),
    path('conta/alterar-senha/', views.alterar_senha, name='alterar_senha'),

    # --- GESTÃO DE LABORATÓRIOS ---
    path('laboratorios/', views.listar_laboratorios, name='listar_laboratorios'),
    path('laboratorios/novo/', views.cadastrar_laboratorio, name='cadastrar_laboratorio'),
    path('laboratorios/<int:laboratorio_id>/editar/', views.editar_laboratorio, name='editar_laboratorio'),
    path('laboratorios/<int:laboratorio_id>/excluir/', views.excluir_laboratorio, name='excluir_laboratorio'),

    # --- GESTÃO DE COMPUTADORES ---
    path('computadores/', views.listar_computadores, name='listar_computadores'),
    path('computadores/novo/', views.cadastrar_computador, name='cadastrar_computador'),
    path('computadores/<int:computador_id>/editar/', views.editar_computador, name='editar_computador'),

    # --- INVENTÁRIO DE SOFTWARES ---
    path('softwares/', views.listar_softwares, name='listar_softwares'),
    path('softwares/<int:software_id>/excluir/', views.excluir_software, name='excluir_software'),

    # --- SOLICITAÇÕES DE INSTALAÇÃO DE SOFTWARES ---
    path('solicitacoes/', views.listar_solicitacoes, name='listar_solicitacoes'),
    path('solicitacoes/nova/', views.criar_solicitacao_instalacao, name='criar_solicitacao_global'),
    path('computadores/<int:computador_id>/solicitar-software/', views.criar_solicitacao_instalacao, name='criar_solicitacao_instalacao'),
    path('solicitacoes/<int:solicitacao_id>/status/', views.atualizar_status_solicitacao, name='atualizar_status_solicitacao'),
    path('solicitacoes/<int:solicitacao_id>/retirar/', views.cancelar_solicitacao, name='cancelar_solicitacao'),

    # --- RESERVAS E AGENDAMENTOS ---
    path('agendar/<int:computador_id>/', views.criar_agendamento, name='criar_agendamento'),
    path('meus-agendamentos/', views.meus_agendamentos, name='meus_agendamentos'),
    path('agendamentos/<int:agendamento_id>/cancelar/', views.cancelar_agendamento, name='cancelar_agendamento'),
    path('gestao/agendamentos/', views.gerenciar_agendamentos, name='gerenciar_agendamentos'),
    path('gestao/dashboard/', views.dashboard_financeiro, name='dashboard_financeiro'),

    # --- GESTÃO DE USUÁRIOS E PERMISSÕES ---
    path('gestao/liberar-usuarios/', views.liberar_usuarios, name='liberar_usuarios'),
    path('gestao/perfis/<int:perfil_id>/aprovar/', views.aprovar_usuario, name='aprovar_usuario'),
    path('gestao/perfis/<int:perfil_id>/revogar/', views.revogar_usuario, name='revogar_usuario'),
    path('gestao/usuarios/', views.gerenciar_usuarios, name='gerenciar_usuarios'),
    path('gestao/usuarios/<int:user_id>/editar/', views.editar_usuario, name='editar_usuario'),
    path('gestao/usuarios/<int:user_id>/resetar-senha/', views.resetar_senha_usuario, name='resetar_senha_usuario'),
    path('gestao/usuarios/<int:user_id>/excluir/', views.deletar_usuario, name='deletar_usuario'),
    path('permissoes/', views.permissoes_acesso, name='permissoes_acesso'),
]
