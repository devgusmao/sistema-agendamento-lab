from . import menu
from .models import perfil_e_admin, perfil_e_gestor


def papeis(request):
    """Expõe os papéis (já considerando aprovação) e o menu lateral para todos os templates."""
    is_admin = perfil_e_admin(request.user)
    is_gestor = perfil_e_gestor(request.user)
    contexto = {'is_admin': is_admin, 'is_gestor': is_gestor, 'menu': []}
    if request.user.is_authenticated:
        url_name = request.resolver_match.url_name if request.resolver_match else ''
        contexto['menu'] = menu.montar(url_name, is_gestor, is_admin)
    return contexto
