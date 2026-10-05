from .models import perfil_e_admin, perfil_e_gestor


def papeis(request):
    """Expõe os papéis (já considerando aprovação) para todos os templates."""
    return {
        'is_admin': perfil_e_admin(request.user),
        'is_gestor': perfil_e_gestor(request.user),
    }
