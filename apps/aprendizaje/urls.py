from django.urls import path

from . import views

app_name = "aprendizaje"

urlpatterns = [
    path("", views.index, name="index"),
    path("nuevo/", views.crear, name="crear"),
    path("encabezado/", views.encabezado, name="encabezado"),
    path("encabezado/imagen/", views.encabezado_imagen, name="encabezado_imagen"),
    path("<int:numero>/", views.curso, name="curso"),
    path("<int:numero>/editar/", views.editar, name="editar"),
    path("<int:numero>/lecciones/nueva/", views.leccion, name="leccion_nueva"),
    path("<int:numero>/lecciones/<int:pk>/", views.leccion, name="leccion"),
    path("<int:numero>/lecciones/<int:pk>/borrar/", views.borrar_leccion, name="borrar_leccion"),
    path(
        "<int:numero>/lecciones/<int:pk>/bloques/nuevo/<str:tipo>/",
        views.bloque,
        name="bloque_nuevo",
    ),
    path("<int:numero>/lecciones/<int:pk>/bloques/<int:bloque_pk>/", views.bloque, name="bloque"),
    path(
        "<int:numero>/lecciones/<int:pk>/bloques/<int:bloque_pk>/borrar/",
        views.borrar_bloque,
        name="borrar_bloque",
    ),
    path(
        "<int:numero>/lecciones/<int:pk>/bloques/ordenar/",
        views.ordenar_bloques,
        name="ordenar_bloques",
    ),
    path("<int:numero>/archivos/<int:bloque_pk>/", views.archivo, name="archivo"),
    path("<int:numero>/imagenes/<int:item_pk>/", views.imagen, name="imagen"),
    path("<int:numero>/vista-previa/", views.vista_previa, name="vista_previa"),
    path(
        "<int:numero>/vista-previa/<int:pk>/",
        views.vista_previa_leccion,
        name="vista_previa_leccion",
    ),
    path("<int:numero>/ordenar/", views.ordenar, name="ordenar"),
    path("<int:numero>/publicar/", views.publicar, name="publicar"),
    path("<int:numero>/cerrar/", views.cerrar, name="cerrar"),
]
