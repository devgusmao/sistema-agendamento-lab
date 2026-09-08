from django.contrib import admin
from .models import Computador

@admin.register(Computador)
class ComputadorAdmin(admin.ModelAdmin):
    list_display = ('identificador', 'status', 'observacoes')
    list_filter = ('status',)
    search_fields = ('identificador',)