from django.urls import path

from . import views

app_name = "guia"

urlpatterns = [
    path("", views.index, name="index"),
    path("plantillas/<int:pk>/", views.descargar_plantilla, name="descargar_plantilla"),
    path("documentos/", views.agregar_documento, name="agregar_documento"),
    path("documentos/<int:pk>/", views.descargar_documento, name="descargar_documento"),
    path("documentos/<int:pk>/eliminar/", views.eliminar_documento, name="eliminar_documento"),
]
