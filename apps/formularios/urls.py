from django.urls import path

from . import views

app_name = "formularios"

urlpatterns = [
    path("", views.index, name="index"),
    path("personas/", views.personas, name="personas"),
    path("personas/cargar/", views.cargar, name="cargar"),
    path("personas/cargar/confirmar/", views.confirmar_carga, name="confirmar_carga"),
    path("personas/<int:pk>/estado/", views.persona_estado, name="persona_estado"),
    path("nuevo/", views.crear, name="crear"),
    path("<int:numero>/", views.cuestionario, name="cuestionario"),
    path("<int:numero>/editar/", views.editar, name="editar"),
    path("<int:numero>/preguntas/nueva/", views.pregunta, name="pregunta_nueva"),
    path("<int:numero>/preguntas/<int:pk>/", views.pregunta, name="pregunta"),
    path("<int:numero>/preguntas/<int:pk>/borrar/", views.borrar_pregunta,
         name="borrar_pregunta"),
    path("<int:numero>/puntos/", views.puntos, name="puntos"),
    path("<int:numero>/repartir/", views.repartir, name="repartir"),
    path("<int:numero>/publicar/", views.publicar, name="publicar"),
    path("<int:numero>/cerrar/", views.cerrar, name="cerrar"),
    path("<int:numero>/enlaces/", views.enlaces, name="enlaces"),
    path("<int:numero>/enlaces/exportar/", views.exportar_enlaces, name="exportar_enlaces"),
    path("<int:numero>/resultados/", views.resultados, name="resultados"),
]
