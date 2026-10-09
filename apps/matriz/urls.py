from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "matriz"

urlpatterns = [
    # The board is the default view; the list is the second one.
    path("", views.tablero, name="tablero"),
    path("lista/", views.index, name="index"),
    path("nuevo/", views.crear, name="crear"),
    path(  # old address of the board, kept for bookmarks
        "tablero/",
        RedirectView.as_view(pattern_name="matriz:tablero", query_string=True, permanent=True),
    ),
    path("<int:numero>/mover/", views.mover, name="mover"),
    path("exportar/", views.exportar, name="exportar"),
    path("grupos/nuevo/", views.crear_grupo, name="crear_grupo"),
    path("fotos/", views.fotos, name="fotos"),
    path("fotos/<int:pk>/exportar/", views.exportar_foto, name="exportar_foto"),
    path("<int:numero>/", views.detalle, name="detalle"),
    path("<int:numero>/editar/", views.editar, name="editar"),
    path("<int:numero>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("<int:numero>/prioridad/", views.ajustar_prioridad, name="ajustar_prioridad"),
    path("<int:numero>/comentarios/", views.comentar, name="comentar"),
    path("<int:numero>/adjuntos/", views.adjuntar, name="adjuntar"),
    path("<int:numero>/adjuntos/<int:pk>/", views.descargar_adjunto, name="descargar_adjunto"),
    path("<int:numero>/dependencias/", views.agregar_dependencia, name="agregar_dependencia"),
    path(
        "<int:numero>/dependencias/<int:pk>/quitar/",
        views.quitar_dependencia,
        name="quitar_dependencia",
    ),
    path(
        "<int:numero>/grupo-sugerido/",
        views.resolver_grupo_sugerido,
        name="resolver_grupo_sugerido",
    ),
]
