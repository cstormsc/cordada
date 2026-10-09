from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("orden/", views.guardar_layout, name="guardar_layout"),
    path("datos/", views.datos, name="datos"),
    path("datos/<int:pk>/borrar/", views.borrar_dato, name="borrar_dato"),
    path("indicadores/", views.indicadores, name="indicadores"),
    path("indicadores/<slug:key>/", views.indicador_guardar, name="indicador_guardar"),
]
