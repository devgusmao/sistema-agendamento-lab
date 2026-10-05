import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('agendamentos', '0007_popular_tipos_agendamento')]

    operations = [
        migrations.RemoveField(model_name='agendamento', name='finalidade'),
        migrations.AlterField(
            model_name='agendamento',
            name='tipo',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='agendamentos',
                to='agendamentos.tipoagendamento',
            ),
        ),
    ]
