from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='agendamentos/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('cadastrar/', views.cadastrar, name='cadastrar'),
    path('laboratorios/novo/', views.cadastrar_laboratorio, name='cadastrar_laboratorio'),
    path('computadores/novo/', views.cadastrar_computador, name='cadastrar_computador'),
    path('computadores/editar/<int:computador_id>/', views.editar_computador, name='editar_computador'),
    path('agendar/<int:computador_id>/', views.criar_agendamento, name='criar_agendamento'),
    path('meus-agendamentos/', views.meus_agendamentos, name='meus_agendamentos'),
    path('gestao/agendamentos/', views.gerenciar_agendamentos, name='gerenciar_agendamentos'),
    path('agendamentos/cancelar/<int:agendamento_id>/', views.cancelar_agendamento, name='cancelar_agendamento'),
    path('gestao/liberar-usuarios/', views.liberar_usuarios, name='liberar_usuarios'),
    path('gestao/aprovar/<int:perfil_id>/', views.aprovar_usuario, name='aprovar_usuario'),
    path('gestao/usuarios/', views.gerenciar_usuarios, name='gerenciar_usuarios'),
    path('gestao/usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('gestao/usuarios/deletar/<int:user_id>/', views.deletar_usuario, name='deletar_usuario'),
    path('laboratorios/', views.listar_laboratorios, name='listar_laboratorios'),
    path('laboratorios/cadastrar/', views.cadastrar_laboratorio, name='cadastrar_laboratorio'),
    path('laboratorios/<int:laboratorio_id>/editar/', views.editar_laboratorio, name='editar_laboratorio'),
    path('computadores/', views.listar_computadores, name='listar_computadores'),
    path('permissoes/', views.permissoes_acesso, name='permissoes_acesso'),
]