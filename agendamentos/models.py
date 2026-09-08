from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Perfil(models.Model):
    TIPO_PERFIL = [
        ('ALUNO', 'Aluno / Comunidade'),
        ('TECNICO', 'Técnico / Gestor de Máquinas'),
        ('ADMIN', 'Administrador'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    tipo = models.CharField(max_length=20, choices=TIPO_PERFIL, default='ALUNO')
    aprovado = models.BooleanField(default=False, help_text="Indica se o usuário foi liberado pelo administrador para usar o sistema.")

    def __str__(self):
        return f"{self.usuario.username} - {self.get_tipo_display()} ({'Aprovado' if self.aprovado else 'Pendente'})"

# Cria automaticamente o Perfil quando um User for cadastrado
@receiver(post_save, sender=User)
def criar_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        # Se for o primeiro superuser criado via terminal, já deixa aprovado e como ADMIN
        is_admin = instance.is_superuser
        Perfil.objects.create(
            usuario=instance,
            tipo='ADMIN' if is_admin else 'ALUNO',
            aprovado=is_admin
        )

class Laboratorio(models.Model):
    nome = models.CharField(max_length=100)
    capacidade = models.IntegerField()

    def __str__(self):
        return f"{self.nome} (Capacidade: {self.capacidade})"

class Computador(models.Model):
    STATUS_CHOICES = [
        ('DISPONIVEL', 'Disponível'),
        ('MANUTENCAO', 'Em Manutenção'),
        ('INATIVO', 'Inativo'),
    ]

    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.CASCADE, related_name='computadores', null=True, blank=True)
    identificador = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DISPONIVEL')
    observacoes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.identificador} ({self.get_status_display()})"

class Agendamento(models.Model):
    STATUS_CHOICES = [
        ('CONFIRMADO', 'Confirmado'),
        ('CANCELADO', 'Cancelado'),
        ('CONCLUIDO', 'Concluído'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    computador = models.ForeignKey(Computador, on_delete=models.CASCADE)
    data_hora_inicio = models.DateTimeField()
    data_hora_fim = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONFIRMADO')

    def __str__(self):
        return f"Reserva de {self.usuario.username} - {self.computador.identificador}"