from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone


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


@receiver(post_save, sender=User)
def criar_perfil_do_usuario(sender, instance, created, **kwargs):
    """Garante que todo usuário tenha um Perfil desde o cadastro.

    Sem isso, `user.perfil` só passava a existir quando um admin abria a tela de
    liberação de usuários, o que deixava as telas com `hasattr(user, 'perfil')`
    em estados inconsistentes.
    """
    if created:
        Perfil.objects.get_or_create(
            usuario=instance,
            defaults={
                'tipo': 'ADMIN' if instance.is_superuser else 'ALUNO',
                'aprovado': instance.is_superuser,
            },
        )


class Laboratorio(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    capacidade = models.PositiveIntegerField(default=0, help_text="Capacidade máxima de pessoas/computadores")
    descricao = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Software(models.Model):
    CATEGORIA_CHOICES = [
        ('DEV', 'Desenvolvimento'),
        ('BD', 'Banco de Dados'),
        ('UTIL', 'Utilitários'),
        ('JOGOS', 'Jogos / Lazer'),
    ]

    nome = models.CharField(max_length=100)
    versao = models.CharField(max_length=50, blank=True, null=True)
    categoria = models.CharField(max_length=50, choices=CATEGORIA_CHOICES, default='DEV')

    class Meta:
        ordering = ['categoria', 'nome']
        constraints = [
            models.UniqueConstraint(fields=['nome', 'versao'], name='software_nome_versao_unico'),
        ]

    def __str__(self):
        return f"{self.nome} {self.versao if self.versao else ''}".strip()


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

    # Co-working & Inventário
    softwares = models.ManyToManyField(Software, blank=True, related_name='computadores')
    valor_hora = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, help_text="Tarifa por hora de uso")

    class Meta:
        ordering = ['laboratorio__nome', 'identificador']
        constraints = [
            models.UniqueConstraint(
                fields=['laboratorio', 'identificador'],
                name='computador_identificador_unico_por_lab',
            ),
        ]

    @property
    def disponivel(self):
        return self.status == 'DISPONIVEL'

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

    finalidade = models.CharField(max_length=20, choices=FINALIDADE_CHOICES, default='PROGRAMACAO')
    valor_total = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    criado_em = models.DateTimeField(auto_now_add=True, null=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='agendamentos_cancelados'
    )

    class Meta:
        ordering = ['-data_hora_inicio']
        indexes = [
            models.Index(fields=['computador', 'status', 'data_hora_inicio']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(data_hora_fim__gt=models.F('data_hora_inicio')),
                name='agendamento_fim_depois_do_inicio',
            ),
        ]

    @property
    def em_andamento(self):
        return self.status == 'CONFIRMADO' and self.data_hora_inicio <= timezone.now() < self.data_hora_fim

    @property
    def encerrado(self):
        return self.data_hora_fim <= timezone.now()

    def pode_ser_cancelado_por(self, user):
        """Regras de cancelamento.

        - Apenas reservas CONFIRMADAS e que ainda não terminaram podem ser canceladas.
        - O dono cancela a própria reserva; administradores cancelam qualquer uma.
        """
        if self.status != 'CONFIRMADO' or self.encerrado:
            return False
        return self.usuario_id == user.id or perfil_e_admin(user)

    def cancelar(self, por_usuario):
        self.status = 'CANCELADO'
        self.cancelado_em = timezone.now()
        self.cancelado_por = por_usuario
        self.save(update_fields=['status', 'cancelado_em', 'cancelado_por'])

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
    computador = models.ForeignKey(Computador, on_delete=models.CASCADE, related_name='solicitacoes_instalacao', null=True, blank=True)
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.SET_NULL, related_name='solicitacoes_instalacao', null=True, blank=True)
    software_nome = models.CharField(max_length=150, help_text="Nome e versão do software desejado")
    justificativa = models.TextField(help_text="Motivo ou finalidade do uso")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    data_criacao = models.DateTimeField(auto_now_add=True)
    atendido_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='solicitacoes_atendidas'
    )
    data_atualizacao = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['-data_criacao']

    def destino_display(self):
        if self.computador:
            return f"{self.computador.identificador} ({self.computador.laboratorio.nome})"
        if self.laboratorio:
            return f"Qualquer máquina do laboratório {self.laboratorio.nome}"
        return "Qualquer máquina"

    def __str__(self):
        return f"Solicitação: {self.software_nome} para {self.destino_display()}"


# --- Helpers de papel (uma única fonte de verdade para as checagens de acesso) ---

def perfil_e_admin(user):
    """Administrador: superusuário do Django ou perfil do tipo ADMIN."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or getattr(getattr(user, 'perfil', None), 'tipo', None) == 'ADMIN'


def perfil_e_gestor(user):
    """Gestor: administrador ou técnico (acesso às telas de TI)."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or getattr(getattr(user, 'perfil', None), 'tipo', None) in ('ADMIN', 'TECNICO')


def perfil_aprovado(user):
    """Usuário liberado para usar o sistema."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or getattr(getattr(user, 'perfil', None), 'aprovado', False)
