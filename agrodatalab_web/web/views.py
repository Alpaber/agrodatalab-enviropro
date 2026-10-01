import base64
import csv
import io
from datetime import datetime
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Max, Min
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import LoginUsuarioForm, RecomendacionForm, RegistroUsuarioForm
from .models import Alerta, Recomendacion, RegistroEnviroPro


def media_campos(fila, claves):
    valores = []
    for clave in claves:
        valor = fila.get(clave)
        if valor not in (None, ''):
            try:
                valores.append(float(valor))
            except ValueError:
                pass
    return sum(valores) / len(valores) if valores else 0.0


def max_campos(fila, claves):
    valores = []
    for clave in claves:
        valor = fila.get(clave)
        if valor not in (None, ''):
            try:
                valores.append(float(valor))
            except ValueError:
                pass
    return max(valores) if valores else 0.0


def min_campos(fila, claves):
    valores = []
    for clave in claves:
        valor = fila.get(clave)
        if valor not in (None, ''):
            try:
                valores.append(float(valor))
            except ValueError:
                pass
    return min(valores) if valores else 0.0


def obtener_tipo_alerta(fila):
    try:
        temp_min = float(fila.get('temp_suelo_min', 0) or 0)
        temp_avg = float(fila.get('temp_global_avg', 0) or 0)
        temp_max = float(fila.get('temp_suelo_max', 0) or 0)

        if not (temp_min <= temp_avg <= temp_max):
            return 'temperatura_incoherente'
    except Exception:
        pass

    if str(fila.get('alerta_sequedad_relativa', fila.get('alseqrelativa', '0'))).strip() == '1':
        return 'humedad_baja'
    elif str(fila.get('alerta_calor_suelo', fila.get('alcalorsuelo', '0'))).strip() == '1':
        return 'temperatura_alta'
    elif float(fila.get('bateria_mv', 9999) or 9999) < 6000:
        return 'bateria_baja'
    elif float(fila.get('panel_solar_mv', 9999) or 9999) < 100:
        return 'panel_bajo'

    return 'humedad_baja'


def obtener_nivel_alerta(prediccion_riesgo):
    try:
        valor = float(prediccion_riesgo)
        if valor >= 0.75:
            return 'alta'
        elif valor >= 0.40:
            return 'media'
        return 'baja'
    except Exception:
        return 'media'


def inicio(request):
    return render(request, 'web/index.html')


def usuarios(request):
    return render(request, 'web/usuarios.html')


def acerca(request):
    return render(request, 'web/acerca.html')


def registro_usuario(request):
    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            es_primer_usuario = User.objects.count() == 0
            user = form.save()

            if es_primer_usuario:
                user.is_staff = True
                user.is_superuser = True
                user.save()
                messages.success(request, 'Primer usuario creado como administrador.')
            else:
                messages.success(request, 'Usuario registrado correctamente.')

            login(request, user)
            return redirect('dashboard')
    else:
        form = RegistroUsuarioForm()

    return render(request, 'web/registro.html', {'form': form})


def login_usuario(request):
    if request.method == 'POST':
        form = LoginUsuarioForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = LoginUsuarioForm()

    return render(request, 'web/login.html', {'form': form})


def logout_usuario(request):
    if request.method == 'POST':
        logout(request)
    return redirect('usuarios')


@login_required
def dashboard(request):
    registros = RegistroEnviroPro.objects.all().order_by('fecha_hora')
    alertas_qs = Alerta.objects.all().order_by('-fecha_hora')

    total_registros = registros.count()
    primera_lectura = registros.first()
    ultima_lectura = registros.last()

    medias = registros.aggregate(
        humedad_media_general=Avg('humedad_media'),
        temperatura_media_general=Avg('temperatura_media'),
        bateria_media=Avg('bateria_mv'),
        panel_solar_medio=Avg('panel_solar_mv'),
    )

    alertas_sequedad = alertas_qs.filter(tipo='humedad_baja').count()
    alertas_energeticas = alertas_qs.filter(tipo__in=['bateria_baja', 'panel_bajo']).count()

    temperaturas_altas = registros.filter(temperatura_media__gt=30).count()
    temperaturas_bajas = registros.filter(temperatura_media__lt=10).count()

    ultima_recomendacion = Recomendacion.objects.select_related('alerta').order_by('-id').first()

    contexto = {
        'total_registros': total_registros,
        'primera_lectura': primera_lectura,
        'ultima_lectura': ultima_lectura,
        'humedad_media_general': medias['humedad_media_general'],
        'temperatura_media_general': medias['temperatura_media_general'],
        'bateria_media': medias['bateria_media'],
        'panel_solar_medio': medias['panel_solar_medio'],
        'alertas_sequedad': alertas_sequedad,
        'alertas_energeticas': alertas_energeticas,
        'temperaturas_altas': temperaturas_altas,
        'temperaturas_bajas': temperaturas_bajas,
        'ultima_recomendacion': ultima_recomendacion,
    }

    return render(request, 'web/dashboard.html', contexto)


@login_required
def alertas(request):
    lista_alertas = Alerta.objects.prefetch_related('recomendaciones').all().order_by('-fecha_hora')
    return render(request, 'web/alertas.html', {'alertas': lista_alertas})


@login_required
def importacion(request):
    if request.method == 'POST' and request.FILES.get('archivo_csv'):
        archivo = request.FILES['archivo_csv']

        if not archivo.name.endswith('.csv'):
            messages.error(request, 'Debes subir un archivo CSV válido.')
            return redirect('importacion')

        try:
            contenido = archivo.read().decode('utf-8-sig')
            lector = csv.DictReader(io.StringIO(contenido), delimiter=';')

            if lector.fieldnames:
                lector.fieldnames = [fn.strip().lower() for fn in lector.fieldnames]

            registros_creados = 0
            alertas_creadas = 0
            recomendaciones_creadas = 0

            for fila in lector:
                try:
                    fila = {
                        k.strip().lower(): (v.strip() if isinstance(v, str) else v)
                        for k, v in fila.items()
                    }

                    valor_fecha = (fila.get('fecha_hora') or '').strip()
                    if not valor_fecha:
                        continue

                    fecha_naive = datetime.strptime(valor_fecha, '%Y-%m-%d %H:%M:%S')
                    fecha_hora = timezone.make_aware(
                        fecha_naive,
                        timezone.get_current_timezone()
                    )

                    # --- cálculos ---
                    humedad_media_raw = fila.get('humedad_global_avg')
                    if humedad_media_raw not in (None, ''):
                        humedad_media = float(humedad_media_raw)
                    else:
                        humedad_media = media_campos(fila, [
                            'humedad_s1_avg', 'humedad_s2_avg', 'humedad_s3_avg', 'humedad_s4_avg',
                            'humedad_s5_avg', 'humedad_s6_avg', 'humedad_s7_avg', 'humedad_s8_avg'
                        ])

                    temperatura_media_raw = fila.get('temp_global_avg')
                    if temperatura_media_raw not in (None, ''):
                        temperatura_media = float(temperatura_media_raw)
                    else:
                        temperatura_media = media_campos(fila, [
                            'temp_s1_avg', 'temp_s2_avg', 'temp_s3_avg', 'temp_s4_avg',
                            'temp_s5_avg', 'temp_s6_avg', 'temp_s7_avg', 'temp_s8_avg'
                        ])

                    temperatura_maxima_raw = fila.get('temp_suelo_max')
                    if temperatura_maxima_raw not in (None, ''):
                        temperatura_maxima = float(temperatura_maxima_raw)
                    else:
                        temperatura_maxima = max_campos(fila, [
                            'temp_s1_max', 'temp_s2_max', 'temp_s3_max', 'temp_s4_max',
                            'temp_s5_max', 'temp_s6_max', 'temp_s7_max', 'temp_s8_max'
                        ])

                    temperatura_minima_raw = fila.get('temp_suelo_min')
                    if temperatura_minima_raw not in (None, ''):
                        temperatura_minima = float(temperatura_minima_raw)
                    else:
                        temperatura_minima = min_campos(fila, [
                            'temp_s1_min', 'temp_s2_min', 'temp_s3_min', 'temp_s4_min',
                            'temp_s5_min', 'temp_s6_min', 'temp_s7_min', 'temp_s8_min'
                        ])

                    bateria_mv = float(fila.get('bateria_mv', 0) or 0)
                    panel_solar_mv = float(fila.get('panel_solar_mv', 0) or 0)

                    observaciones = (
                        fila.get('mensaje_alerta')
                        or fila.get('mensajealerta')
                        or ''
                    ).strip()

                    # --- guardar registro ---
                    registro, creado = RegistroEnviroPro.objects.get_or_create(
                        fecha_hora=fecha_hora,
                        defaults={
                            'humedad_media': humedad_media,
                            'temperatura_media': temperatura_media,
                            'temperatura_maxima': temperatura_maxima,
                            'temperatura_minima': temperatura_minima,
                            'bateria_mv': bateria_mv,
                            'panel_solar_mv': panel_solar_mv,
                            'observaciones': observaciones,
                        }
                    )

                    if creado:
                        registros_creados += 1

                    # =========================
                    # 🔥 ALERTAS (SIEMPRE)
                    # =========================

                    disparar_alerta = str(
                        fila.get('disparar_alerta', fila.get('dispararalerta', '0'))
                    ).strip()

                    recomendacion_texto = (
                        fila.get('recomendacion_tecnica')
                        or fila.get('recomendaciontecnica')
                        or ''
                    ).strip()

                    mensaje_alerta = (
                        fila.get('mensaje_alerta')
                        or fila.get('mensajealerta')
                        or ''
                    ).strip()

                    prediccion_riesgo = (
                        fila.get('prediccion_riesgo')
                        or fila.get('prediccionriesgo')
                        or ''
                    ).strip()

                    if disparar_alerta == '1':
                        tipo_alerta = obtener_tipo_alerta(fila)
                        nivel_alerta = obtener_nivel_alerta(prediccion_riesgo)

                        alerta = Alerta.objects.create(
                            fecha_hora=fecha_hora,
                            tipo=tipo_alerta,
                            nivel=nivel_alerta,
                            descripcion=mensaje_alerta or 'Alerta generada automáticamente desde CSV',
                            variable_afectada=tipo_alerta,
                            atendida=False,
                        )

                        alertas_creadas += 1

                        if recomendacion_texto:
                            Recomendacion.objects.create(
                                titulo=f"Recomendación {fecha_hora.strftime('%d/%m/%Y %H:%M')}",
                                descripcion=recomendacion_texto,
                                alerta=alerta,
                                prioridad=nivel_alerta,
                                estado='pendiente',
                            )
                            recomendaciones_creadas += 1

                except Exception:
                    continue

            messages.success(
                request,
                f'Importación completada: {registros_creados} registros, '
                f'{alertas_creadas} alertas y {recomendaciones_creadas} recomendaciones.'
            )

        except Exception as e:
            messages.error(request, f'Error al importar el archivo: {e}')

        return redirect('importacion')

    total_registros = RegistroEnviroPro.objects.count()
    total_alertas = Alerta.objects.count()
    total_recomendaciones = Recomendacion.objects.count()
    ultimo_registro = RegistroEnviroPro.objects.order_by('-fecha_hora').first()

    contexto = {
        'total_registros': total_registros,
        'total_alertas': total_alertas,
        'total_recomendaciones': total_recomendaciones,
        'ultimo_registro': ultimo_registro,
    }

    return render(request, 'web/importacion.html', contexto)

@login_required
def recomendaciones(request):
    lista_recomendaciones = Recomendacion.objects.select_related('alerta').all().order_by('-id')
    return render(request, 'web/recomendaciones.html', {'recomendaciones': lista_recomendaciones})


@login_required
def crear_recomendacion(request):
    if request.method == 'POST':
        form = RecomendacionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Recomendación creada correctamente.')
            return redirect('recomendaciones')
    else:
        form = RecomendacionForm()

    return render(request, 'web/recomendacion_form.html', {
        'form': form,
        'titulo_pagina': 'Crear recomendación'
    })


@login_required
def editar_recomendacion(request, pk):
    recomendacion = get_object_or_404(Recomendacion, pk=pk)

    if request.method == 'POST':
        form = RecomendacionForm(request.POST, instance=recomendacion)
        if form.is_valid():
            form.save()
            messages.success(request, 'Recomendación actualizada correctamente.')
            return redirect('recomendaciones')
    else:
        form = RecomendacionForm(instance=recomendacion)

    return render(request, 'web/recomendacion_form.html', {
        'form': form,
        'titulo_pagina': 'Editar recomendación'
    })


@login_required
def eliminar_recomendacion(request, pk):
    recomendacion = get_object_or_404(Recomendacion, pk=pk)

    if request.method == 'POST':
        recomendacion.delete()
        messages.success(request, 'Recomendación eliminada correctamente.')
        return redirect('recomendaciones')

    return render(request, 'web/recomendacion_confirm_delete.html', {
        'recomendacion': recomendacion
    })


@login_required
def marcar_revisada(request, pk):
    if request.method == 'POST':
        recomendacion = get_object_or_404(Recomendacion, pk=pk)
        recomendacion.estado = 'revisada'
        recomendacion.save()
        messages.success(request, 'Recomendación marcada como revisada.')
    return redirect('recomendaciones')


@login_required
def marcar_descartada(request, pk):
    if request.method == 'POST':
        recomendacion = get_object_or_404(Recomendacion, pk=pk)
        recomendacion.estado = 'descartada'
        recomendacion.save()
        messages.success(request, 'Recomendación marcada como descartada.')
    return redirect('recomendaciones')


@login_required
def grafico_humedad(request):
    registros = RegistroEnviroPro.objects.all().order_by('-fecha_hora')[:200]
    registros = list(registros)[::-1]

    fechas = [r.fecha_hora for r in registros]
    valores = [r.humedad_media for r in registros]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(fechas, valores, color='teal', linewidth=2)
    ax.set_title('Evolución de la humedad media')
    ax.set_xlabel('Fecha')
    ax.set_ylabel('Humedad (%)')
    ax.grid(True, alpha=0.3)

    buffer = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buffer, format='png')
    plt.close(fig)
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type='image/png')


@login_required
def grafico_temperatura(request):
    registros = RegistroEnviroPro.objects.all().order_by('-fecha_hora')[:200]
    registros = list(registros)[::-1]

    fechas = [r.fecha_hora for r in registros]
    valores = [r.temperatura_media for r in registros]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(fechas, valores, color='orangered', linewidth=2)
    ax.set_title('Evolución de la temperatura media')
    ax.set_xlabel('Fecha')
    ax.set_ylabel('Temperatura (ºC)')
    ax.grid(True, alpha=0.3)

    buffer = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buffer, format='png')
    plt.close(fig)
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type='image/png')


@login_required
def registros(request):
    lista_registros = RegistroEnviroPro.objects.all().order_by('-fecha_hora')

    paginator = Paginator(lista_registros, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'web/registros.html', {
        'page_obj': page_obj
    })


@login_required
def humedad(request):
    registros = RegistroEnviroPro.objects.exclude(humedad_media__isnull=True).order_by('-fecha_hora')

    estadisticas = registros.aggregate(
        promedio_humedad=Avg('humedad_media', default=0),
        max_humedad=Max('humedad_media', default=0),
        min_humedad=Min('humedad_media', default=0)
    )

    ultima_lectura = registros.first()

    registros_mensuales = (
        RegistroEnviroPro.objects
        .exclude(humedad_media__isnull=True)
        .annotate(mes=TruncMonth('fecha_hora'))
        .values('mes')
        .annotate(promedio=Avg('humedad_media'))
        .order_by('mes')
    )

    labels_humedad = [r['mes'].strftime("%m/%Y") for r in registros_mensuales if r['mes']]
    datos_humedad = [float(r['promedio'] or 0) for r in registros_mensuales]

    grafica_humedad = None

    if labels_humedad and datos_humedad:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(labels_humedad, datos_humedad, color='green', marker='o', linewidth=2)
        ax.fill_between(labels_humedad, datos_humedad, color='green', alpha=0.15)

        ax.set_title('Evolución mensual de la humedad media')
        ax.set_xlabel('Mes')
        ax.set_ylabel('Humedad media (%)')
        ax.grid(True, alpha=0.3)

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buffer = BytesIO()
        fig.savefig(buffer, format='png')
        buffer.seek(0)
        grafica_humedad = base64.b64encode(buffer.getvalue()).decode('utf-8')
        buffer.close()
        plt.close(fig)

    context = {
        'humedad_media': estadisticas['promedio_humedad'],
        'humedad_maxima': estadisticas['max_humedad'],
        'humedad_minima': estadisticas['min_humedad'],
        'ultima_lectura': ultima_lectura,
        'grafica_humedad': grafica_humedad,
    }

    return render(request, 'web/humedad.html', context)


@login_required
def temperatura(request):
    registros = RegistroEnviroPro.objects.exclude(temperatura_media__isnull=True).order_by('-fecha_hora')

    estadisticas = registros.aggregate(
        promedio_temperatura=Avg('temperatura_media', default=0),
        max_temperatura=Max('temperatura_media', default=0),
        min_temperatura=Min('temperatura_media', default=0)
    )

    ultima_lectura = registros.first()

    registros_mensuales = (
        RegistroEnviroPro.objects
        .exclude(temperatura_media__isnull=True)
        .annotate(mes=TruncMonth('fecha_hora'))
        .values('mes')
        .annotate(promedio=Avg('temperatura_media'))
        .order_by('mes')
    )

    labels_temperatura = [r['mes'].strftime("%m/%Y") for r in registros_mensuales if r['mes']]
    datos_temperatura = [float(r['promedio'] or 0) for r in registros_mensuales]

    grafica_temperatura = None

    if labels_temperatura and datos_temperatura:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(labels_temperatura, datos_temperatura, color='red', marker='o', linewidth=2)
        ax.fill_between(labels_temperatura, datos_temperatura, color='red', alpha=0.15)

        ax.set_title('Evolución mensual de la temperatura media')
        ax.set_xlabel('Mes')
        ax.set_ylabel('Temperatura media (°C)')
        ax.grid(True, alpha=0.3)

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buffer = BytesIO()
        fig.savefig(buffer, format='png')
        buffer.seek(0)
        grafica_temperatura = base64.b64encode(buffer.getvalue()).decode('utf-8')
        buffer.close()
        plt.close(fig)

    context = {
        'temperatura_media': estadisticas['promedio_temperatura'],
        'temperatura_maxima': estadisticas['max_temperatura'],
        'temperatura_minima': estadisticas['min_temperatura'],
        'ultima_lectura': ultima_lectura,
        'grafica_temperatura': grafica_temperatura,
    }

    return render(request, 'web/temperatura.html', context)


@login_required
def bateria(request):
    registros = RegistroEnviroPro.objects.exclude(bateria_mv__isnull=True).order_by('-fecha_hora')

    estadisticas = registros.aggregate(
        promedio_bateria=Avg('bateria_mv', default=0),
        max_bateria=Max('bateria_mv', default=0),
        min_bateria=Min('bateria_mv', default=0)
    )

    ultima_lectura = registros.first()

    registros_mensuales = (
        RegistroEnviroPro.objects
        .exclude(bateria_mv__isnull=True)
        .annotate(mes=TruncMonth('fecha_hora'))
        .values('mes')
        .annotate(promedio=Avg('bateria_mv'))
        .order_by('mes')
    )

    labels_bateria = [r['mes'].strftime("%m/%Y") for r in registros_mensuales if r['mes']]
    datos_bateria = [float(r['promedio'] or 0) for r in registros_mensuales]

    grafica_bateria = None

    if labels_bateria and datos_bateria:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(labels_bateria, datos_bateria, color='orange', marker='o', linewidth=2)
        ax.fill_between(labels_bateria, datos_bateria, color='orange', alpha=0.15)

        ax.set_title('Evolución mensual de la batería media')
        ax.set_xlabel('Mes')
        ax.set_ylabel('Batería media (mV)')
        ax.grid(True, alpha=0.3)

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buffer = BytesIO()
        fig.savefig(buffer, format='png')
        buffer.seek(0)
        grafica_bateria = base64.b64encode(buffer.getvalue()).decode('utf-8')
        buffer.close()
        plt.close(fig)

    context = {
        'bateria_media': estadisticas['promedio_bateria'],
        'bateria_maxima': estadisticas['max_bateria'],
        'bateria_minima': estadisticas['min_bateria'],
        'ultima_lectura': ultima_lectura,
        'grafica_bateria': grafica_bateria,
    }

    return render(request, 'web/bateria.html', context)


@login_required
def panel_solar(request):
    registros = RegistroEnviroPro.objects.exclude(panel_solar_mv__isnull=True).order_by('-fecha_hora')

    estadisticas = registros.aggregate(
        promedio_panel=Avg('panel_solar_mv', default=0),
        max_panel=Max('panel_solar_mv', default=0),
        min_panel=Min('panel_solar_mv', default=0)
    )

    ultima_lectura = registros.first()

    registros_mensuales = (
        RegistroEnviroPro.objects
        .exclude(panel_solar_mv__isnull=True)
        .annotate(mes=TruncMonth('fecha_hora'))
        .values('mes')
        .annotate(promedio=Avg('panel_solar_mv'))
        .order_by('mes')
    )

    labels_panel = [r['mes'].strftime("%m/%Y") for r in registros_mensuales if r['mes']]
    datos_panel = [float(r['promedio'] or 0) for r in registros_mensuales]

    grafica_panel = None

    if labels_panel and datos_panel:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(labels_panel, datos_panel, color='royalblue', marker='o', linewidth=2)
        ax.fill_between(labels_panel, datos_panel, color='royalblue', alpha=0.15)

        ax.set_title('Evolución mensual del panel solar')
        ax.set_xlabel('Mes')
        ax.set_ylabel('Panel solar medio (mV)')
        ax.grid(True, alpha=0.3)

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buffer = BytesIO()
        fig.savefig(buffer, format='png')
        buffer.seek(0)
        grafica_panel = base64.b64encode(buffer.getvalue()).decode('utf-8')
        buffer.close()
        plt.close(fig)

    context = {
        'panel_solar_medio': estadisticas['promedio_panel'],
        'panel_solar_maximo': estadisticas['max_panel'],
        'panel_solar_minimo': estadisticas['min_panel'],
        'ultima_lectura': ultima_lectura,
        'grafica_panel': grafica_panel,
    }

    return render(request, 'web/panel_solar.html', context)


@login_required
def admin_usuarios(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    lista_usuarios = User.objects.all().order_by('id')
    return render(request, 'web/admin_usuarios.html', {
        'usuarios': lista_usuarios
    })


@login_required
def editar_usuario(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied

    usuario = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        es_admin = request.POST.get('is_superuser') == 'on'

        if not username:
            messages.error(request, 'El nombre de usuario es obligatorio.')
            return redirect('editar_usuario', pk=pk)

        if User.objects.exclude(pk=usuario.pk).filter(username=username).exists():
            messages.error(request, 'Ese nombre de usuario ya existe.')
            return redirect('editar_usuario', pk=pk)

        usuario.username = username
        usuario.email = email
        usuario.is_staff = es_admin
        usuario.is_superuser = es_admin
        usuario.save()

        messages.success(request, 'Usuario actualizado correctamente.')
        return redirect('admin_usuarios')

    return render(request, 'web/editar_usuario.html', {
        'usuario_obj': usuario
    })


@login_required
def eliminar_usuario(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied

    usuario = get_object_or_404(User, pk=pk)

    if request.user.pk == usuario.pk:
        messages.error(request, 'No puedes eliminar tu propio usuario administrador.')
        return redirect('admin_usuarios')

    if request.method == 'POST':
        usuario.delete()
        messages.success(request, 'Usuario eliminado correctamente.')
        return redirect('admin_usuarios')

    return render(request, 'web/eliminar_usuario.html', {
        'usuario_obj': usuario
    })