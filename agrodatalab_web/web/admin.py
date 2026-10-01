from django.contrib import admin
from .models import RegistroEnviroPro, Alerta, Recomendacion


@admin.register(RegistroEnviroPro)
class RegistroEnviroProAdmin(admin.ModelAdmin):
    list_display = (
        'fecha_hora',
        'humedad_media',
        'temperatura_media',
        'temperatura_maxima',
        'temperatura_minima',
        'bateria_mv',
        'panel_solar_mv',
    )
    search_fields = ('fecha_hora',)
    list_filter = ('fecha_hora',)


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ('fecha_hora', 'tipo', 'nivel', 'descripcion', 'variable_afectada', 'atendida')
    search_fields = ('tipo', 'descripcion', 'variable_afectada')
    list_filter = ('tipo', 'nivel', 'atendida', 'fecha_hora')


@admin.register(Recomendacion)
class RecomendacionAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'alerta', 'prioridad', 'estado')
    search_fields = ('titulo', 'descripcion')
    list_filter = ('prioridad', 'estado')