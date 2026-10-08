from django.urls import path

from . import views

app_name = "ruta"

urlpatterns = [
    path("", views.index, name="index"),
    path("nueva/", views.crear, name="crear"),
    path("exportar/", views.exportar, name="exportar"),
    path("informe/", views.informe, name="informe"),
    path("informe/pdf/", views.informe_pdf, name="informe_pdf"),
    path("<int:numero>/", views.detalle, name="detalle"),
    path("<int:numero>/editar/", views.editar, name="editar"),
    path("<int:numero>/evidencias/", views.adjuntar, name="adjuntar"),
    path("<int:numero>/evidencias/<int:pk>/", views.descargar, name="descargar"),
]
