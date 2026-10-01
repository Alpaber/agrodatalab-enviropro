from django.urls import path
from . import views


urlpatterns = [
    path('', views.inicio, name='inicio'),

    path('usuarios/', views.usuarios, name='usuarios'),
    path('registro/', views.registro_usuario, name='registro'),
    path('login/', views.login_usuario, name='login'),
    path('logout/', views.logout_usuario, name='logout'),

    path('dashboard/', views.dashboard, name='dashboard'),
    path('alertas/', views.alertas, name='alertas'),
    path('importacion/', views.importacion, name='importacion'),
    path('acerca/', views.acerca, name='acerca'),

    path('recomendaciones/', views.recomendaciones, name='recomendaciones'),
    path('recomendaciones/crear/', views.crear_recomendacion, name='crear_recomendacion'),
    path('recomendaciones/<int:pk>/editar/', views.editar_recomendacion, name='editar_recomendacion'),
    path('recomendaciones/<int:pk>/eliminar/', views.eliminar_recomendacion, name='eliminar_recomendacion'),
    path('recomendaciones/<int:pk>/revisar/', views.marcar_revisada, name='marcar_revisada'),
    path('recomendaciones/<int:pk>/descartar/', views.marcar_descartada, name='marcar_descartada'),

    path('grafico-humedad/', views.grafico_humedad, name='grafico_humedad'),
    path('grafico-temperatura/', views.grafico_temperatura, name='grafico_temperatura'),

    path('registros/', views.registros, name='registros'),

    path('humedad/', views.humedad, name='humedad'),
    path('temperatura/', views.temperatura, name='temperatura'),
    path('bateria/', views.bateria, name='bateria'),
    path('panel-solar/', views.panel_solar, name='panel_solar'),

    path('admin-usuarios/', views.admin_usuarios, name='admin_usuarios'),
    path('admin-usuarios/editar/<int:pk>/', views.editar_usuario, name='editar_usuario'),
    path('admin-usuarios/eliminar/<int:pk>/', views.eliminar_usuario, name='eliminar_usuario'),
]