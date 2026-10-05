from django.contrib import admin

from .models import Agendamento, Computador, Laboratorio, Perfil, Software, SolicitacaoInstalacao, TipoAgendamento


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'tipo', 'aprovado')
    list_filter = ('tipo', 'aprovado')
    search_fields = ('usuario__username', 'usuario__email')
    list_editable = ('tipo', 'aprovado')


@admin.register(Laboratorio)
class LaboratorioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'capacidade')
    search_fields = ('nome',)


@admin.register(Software)
class SoftwareAdmin(admin.ModelAdmin):
    list_display = ('nome', 'versao', 'categoria')
    list_filter = ('categoria',)
    search_fields = ('nome',)


@admin.register(Computador)
class ComputadorAdmin(admin.ModelAdmin):
    list_display = ('identificador', 'laboratorio', 'status')
    list_filter = ('status', 'laboratorio')
    search_fields = ('identificador',)
    filter_horizontal = ('softwares',)


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'computador', 'data_hora_inicio', 'data_hora_fim', 'tipo', 'status', 'valor_total')
    list_filter = ('status', 'tipo', 'computador__laboratorio')
    search_fields = ('usuario__username', 'computador__identificador')
    date_hierarchy = 'data_hora_inicio'
    autocomplete_fields = ('computador',)


@admin.register(SolicitacaoInstalacao)
class SolicitacaoInstalacaoAdmin(admin.ModelAdmin):
    list_display = ('software_nome', 'usuario', 'destino_display', 'status', 'data_criacao')
    list_filter = ('status', 'laboratorio')
    search_fields = ('software_nome', 'usuario__username')


@admin.register(TipoAgendamento)
class TipoAgendamentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'modo', 'valor_hora', 'ativo', 'ordem')
    list_filter = ('modo', 'ativo')
