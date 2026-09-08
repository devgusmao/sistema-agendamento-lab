from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='agendamentos/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('cadastrar/', views.cadastrar, name='cadastrar'),
    path('computadores/novo/', views.cadastrar_computador, name='cadastrar_computador'),
    path('gestao/liberar-usuarios/', views.liberar_usuarios, name='liberar_usuarios'),
    path('gestao/aprovar/<int:perfil_id>/', views.aprovar_usuario, name='aprovar_usuario'),
    path('gestao/usuarios/', views.gerenciar_usuarios, name='gerenciar_usuarios'),
    path('gestao/usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('gestao/usuarios/deletar/<int:user_id>/', views.deletar_usuario, name='deletar_usuario'),
]