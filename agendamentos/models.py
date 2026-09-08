from django.db import models

class Computador(models.Model):
    STATUS_CHOICES = [
        ('DISPONIVEL', 'Disponível'),
        ('MANUTENCAO', 'Em Manutenção'),
        ('INATIVO', 'Inativo'),
    ]

    identificador = models.CharField(max_length=50, unique=True) # Ex: PC-01
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DISPONIVEL')
    observacoes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.identificador} ({self.get_status_display()})"