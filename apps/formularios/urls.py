from django.urls import path

from . import views, views_lider

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
    path("listas/", views_lider.listas, name="listas"),
    path("listas/nueva/<int:impacto>/", views_lider.lista_crear, name="lista_crear"),
    path("listas/<int:pk>/", views_lider.lista, name="lista"),
    path("listas/<int:pk>/criterios/<int:criterio>/borrar/", views_lider.criterio_borrar,
         name="criterio_borrar"),
    path("listas/<int:pk>/publicar/", views_lider.lista_publicar, name="lista_publicar"),
    path("listas/<int:pk>/seguimiento/", views_lider.seguimiento, name="seguimiento"),
    path("listas/<int:pk>/actas/<int:acta>/", views_lider.acta_descargar, name="acta"),
    path("evaluar/", views_lider.evaluar_index, name="evaluar_index"),
    path("evaluar/<int:pk>/", views_lider.evaluar, name="evaluar"),
    path("evaluar/<int:pk>/pdf/", views_lider.evaluar_pdf, name="evaluar_pdf"),
    path("evaluar/<int:pk>/acta/", views_lider.evaluar_acta, name="evaluar_acta"),
]
