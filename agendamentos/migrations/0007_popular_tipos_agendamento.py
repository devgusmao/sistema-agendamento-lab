from django.db import migrations

TIPOS = [
    ('ESTUDO', 'Estudo / Pesquisa', 10),
    ('PROGRAMACAO', 'Desenvolvimento / Programação', 20),
    ('ADMINISTRATIVO', 'Atividades Administrativas', 30),
    ('JOGOS', 'Jogos / Eventos', 40),
]


def popular(apps, schema_editor):
    Tipo = apps.get_model('agendamentos', 'TipoAgendamento')
    Agendamento = apps.get_model('agendamentos', 'Agendamento')
    por_codigo = {}
    for codigo, nome, ordem in TIPOS:
        por_codigo[codigo], _ = Tipo.objects.get_or_create(nome=nome, defaults={'ordem': ordem})
    for codigo, tipo in por_codigo.items():
        Agendamento.objects.filter(finalidade=codigo, tipo__isnull=True).update(tipo=tipo)
    # valores legados desconhecidos caem em "Desenvolvimento / Programação"
    Agendamento.objects.filter(tipo__isnull=True).update(tipo=por_codigo['PROGRAMACAO'])


class Migration(migrations.Migration):
    dependencies = [('agendamentos', '0006_tipo_agendamento')]
    operations = [migrations.RunPython(popular, migrations.RunPython.noop)]
