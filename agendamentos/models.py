from django.db import models
from django.contrib.auth.models import User

class Perfil(models.Model):
    TIPO_CHOICES = [
        ('ALUNO', 'Aluno / Comunidade'),
        ('TECNICO', 'Técnico'),
        ('ADMIN', 'Administrador'),
    ]
    
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='ALUNO')
    aprovado = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.usuario.username} - {self.get_tipo_display()}"


class Laboratorio(models.Model):
    nome = models.CharField(max_length=100)
    capacidade = models.PositiveIntegerField(default=0, help_text="Capacidade máxima de pessoas/computadores")
    descricao = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nome


class Software(models.Model):
    nome = models.CharField(max_length=100)
    versao = models.CharField(max_length=50, blank=True, null=True)
    categoria = models.CharField(max_length=50, choices=[
        ('DEV', 'Desenvolvimento'),
        ('BD', 'Banco de Dados'),
        ('UTIL', 'Utilitários'),
        ('JOGOS', 'Jogos / Lazer'),
    ], default='DEV')

    def __str__(self):
        return f"{self.nome} {self.versao if self.versao else ''}"


class Computador(models.Model):
    STATUS_CHOICES = [
        ('DISPONIVEL', 'Disponível'),
        ('MANUTENCAO', 'Em Manutenção'),
        ('INATIVO', 'Inativo'),
    ]

    identificador = models.CharField(max_length=50)
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.CASCADE, related_name='computadores')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DISPONIVEL')
    observacoes = models.TextField(blank=True, null=True)
    
    # Novas funcionalidades de Co-working & Inventário
    softwares = models.ManyToManyField(Software, blank=True, related_name='computadores')
    valor_hora = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, help_text="Tarifa por hora de uso")

    def __str__(self):
        return f"{self.identificador} ({self.laboratorio.nome})"


class Agendamento(models.Model):
    STATUS_CHOICES = [
        ('CONFIRMADO', 'Confirmado'),
        ('CANCELADO', 'Cancelado'),
    ]

    FINALIDADE_CHOICES = [
        ('ESTUDO', 'Estudo / Pesquisa'),
        ('PROGRAMACAO', 'Desenvolvimento / Programação'),
        ('ADMINISTRATIVO', 'Atividades Administrativas'),
        ('JOGOS', 'Jogos / Eventos'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agendamentos')
    computador = models.ForeignKey(Computador, on_delete=models.CASCADE, related_name='agendamentos')
    data_hora_inicio = models.DateTimeField()
    data_hora_fim = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONFIRMADO')
    
    # Novas funcionalidades
    finalidade = models.CharField(max_length=20, choices=FINALIDADE_CHOICES, default='PROGRAMACAO')
    valor_total = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.usuario.username} - {self.computador.identificador}"


class SolicitacaoInstalacao(models.Model):
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('EM_ANDAMENTO', 'Em Andamento'),
        ('CONCLUIDO', 'Concluído'),
        ('REJEITADO', 'Rejeitado'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solicitacoes_instalacao')
    computador = models.ForeignKey(Computador, on_delete=models.CASCADE, related_name='solicitacoes_instalacao')
    software_nome = models.CharField(max_length=150, help_text="Nome e versão do software desejado")
    justificativa = models.TextField(help_text="Motivo ou finalidade do uso")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    data_criacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Solicitação: {self.software_nome} para {self.computador.identificador}"