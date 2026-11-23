from django.db import migrations

NOME = 'auth_user_email_lower_unico'


def checar_duplicados(apps, schema_editor):
    """Falha com uma mensagem clara se já existirem e-mails repetidos (corrija-os antes de migrar)."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT LOWER(email), COUNT(*) FROM auth_user WHERE email <> '' "
            "GROUP BY LOWER(email) HAVING COUNT(*) > 1"
        )
        repetidos = cursor.fetchall()
    if repetidos:
        lista = ', '.join(f'{email} ({n} contas)' for email, n in repetidos)
        raise RuntimeError(
            f'Existem usuários com o mesmo e-mail: {lista}. Corrija em Gerenciar Usuários e rode a migração de novo.'
        )


class Migration(migrations.Migration):
    """Um e-mail por conta, sem diferenciar maiúsculas (vale também para o painel /admin/ e o shell).

    O e-mail vazio continua permitido (contas criadas sem e-mail). Requer PostgreSQL.
    """

    dependencies = [
        ('agendamentos', '0013_confirmacao_email_e_limites'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(checar_duplicados, migrations.RunPython.noop),
        migrations.RunSQL(
            sql=f"CREATE UNIQUE INDEX {NOME} ON auth_user (LOWER(email)) WHERE email <> '';",
            reverse_sql=f'DROP INDEX IF EXISTS {NOME};',
        ),
    ]
