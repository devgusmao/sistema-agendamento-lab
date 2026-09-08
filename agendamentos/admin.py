from django.contrib import admin
from .models import Laboratorio, Computador, Agendamento

@admin.register(Laboratorio)
class LaboratorioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'capacidade')

@admin.register(Computador)
class ComputadorAdmin(admin.ModelAdmin):
    list_display = ('identificador', 'laboratorio', 'status')
    list_filter = ('status', 'laboratorio')
    search_fields = ('identificador',)

@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'computador', 'data_hora_inicio', 'data_hora_fim', 'status')
    list_filter = ('status', 'data_hora_inicio')