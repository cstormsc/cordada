from django.urls import path

from . import views

app_name = "aprendizaje"

urlpatterns = [
    path("", views.index, name="index"),
    path("nuevo/", views.crear, name="crear"),
    path("<int:numero>/", views.curso, name="curso"),
    path("<int:numero>/editar/", views.editar, name="editar"),
    path("<int:numero>/lecciones/nueva/", views.leccion, name="leccion_nueva"),
    path("<int:numero>/lecciones/<int:pk>/", views.leccion, name="leccion"),
    path("<int:numero>/lecciones/<int:pk>/borrar/", views.borrar_leccion, name="borrar_leccion"),
    path("<int:numero>/lecciones/<int:pk>/archivo/", views.archivo, name="archivo"),
    path("<int:numero>/ordenar/", views.ordenar, name="ordenar"),
    path("<int:numero>/publicar/", views.publicar, name="publicar"),
    path("<int:numero>/cerrar/", views.cerrar, name="cerrar"),
]
