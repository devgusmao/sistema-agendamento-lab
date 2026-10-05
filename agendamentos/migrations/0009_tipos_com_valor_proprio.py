from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations


def converter(apps, schema_editor):
    """Tipos 'tarifa da máquina × multiplicador' viram valor próprio por hora.

    Usa a média das tarifas das máquinas cadastradas × multiplicador, para que os
    preços praticados até aqui sejam preservados (ajustáveis depois na tela).
    """
    Tipo = apps.get_model('agendamentos', 'TipoAgendamento')
    Computador = apps.get_model('agendamentos', 'Computador')
    tarifas = list(Computador.objects.values_list('valor_hora', flat=True))
    media = (sum(tarifas, Decimal('0')) / len(tarifas)) if tarifas else Decimal('0')
    for tipo in Tipo.objects.filter(modo='MAQUINA'):
        tipo.valor_hora = (media * tipo.multiplicador).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tipo.modo = 'FIXO'
        tipo.save(update_fields=['valor_hora', 'modo'])


class Migration(migrations.Migration):
    dependencies = [('agendamentos', '0008_remove_finalidade_tipo_obrigatorio')]
    operations = [migrations.RunPython(converter, migrations.RunPython.noop)]
