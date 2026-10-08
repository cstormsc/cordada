from django.urls import path

from . import views

app_name = "matriz"

urlpatterns = [
    path("", views.index, name="index"),
    path("mis-propuestas/", views.mis_propuestas, name="mis_propuestas"),
    path("nuevo/", views.crear, name="crear"),
    path("tablero/", views.tablero, name="tablero"),
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
    path("<int:numero>/grupo-sugerido/", views.resolver_grupo_sugerido,
         name="resolver_grupo_sugerido"),
]
