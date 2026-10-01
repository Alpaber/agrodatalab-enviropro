from django.db import models


class RegistroEnviroPro(models.Model):
    fecha_hora = models.DateTimeField()
    humedad_media = models.FloatField()
    temperatura_media = models.FloatField()
    temperatura_maxima = models.FloatField()
    temperatura_minima = models.FloatField()
    bateria_mv = models.FloatField()
    panel_solar_mv = models.FloatField()
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.fecha_hora} | Humedad: {self.humedad_media} | Temp: {self.temperatura_media}"


class Alerta(models.Model):
    TIPO_ALERTA = [
        ('humedad_baja', 'Humedad baja'),
        ('temperatura_alta', 'Temperatura alta'),
        ('temperatura_incoherente', 'Temperatura incoherente'),
        ('bateria_baja', 'Batería baja'),
        ('panel_bajo', 'Panel solar bajo'),
    ]

    NIVEL_ALERTA = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    ]

    fecha_hora = models.DateTimeField()
    tipo = models.CharField(max_length=50, choices=TIPO_ALERTA)
    nivel = models.CharField(max_length=20, choices=NIVEL_ALERTA, default='media')
    descripcion = models.TextField()
    variable_afectada = models.CharField(max_length=100)
    atendida = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.tipo} - {self.fecha_hora}"


class Recomendacion(models.Model):
    PRIORIDAD = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    ]

    ESTADO = [
        ('pendiente', 'Pendiente'),
        ('revisada', 'Revisada'),
        ('descartada', 'Descartada'),
    ]

    titulo = models.CharField(max_length=150)
    descripcion = models.TextField()
    alerta = models.ForeignKey(Alerta, on_delete=models.CASCADE, related_name='recomendaciones')
    prioridad = models.CharField(max_length=20, choices=PRIORIDAD, default='media')
    estado = models.CharField(max_length=20, choices=ESTADO, default='pendiente')

    def __str__(self):
        return self.titulo