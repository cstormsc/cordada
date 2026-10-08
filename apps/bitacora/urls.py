from django.urls import path

from . import views

app_name = "bitacora"

urlpatterns = [
    path("", views.index, name="index"),
    path("nuevo/", views.crear, name="crear"),
    path("ti/", views.ti, name="ti"),
    path("metricas/", views.metricas, name="metricas"),
    path("exportar/", views.exportar, name="exportar"),
    path("<int:numero>/", views.detalle, name="detalle"),
    path("<int:numero>/editar/", views.editar, name="editar"),
    path("<int:numero>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("<int:numero>/validar/", views.validar, name="validar"),
    path("<int:numero>/caso/", views.caso_cliente, name="caso_cliente"),
    path("<int:numero>/comentarios/", views.comentar, name="comentar"),
    path("<int:numero>/proponer-impacto/", views.proponer_impacto, name="proponer_impacto"),
]
