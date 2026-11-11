from django.urls import path

from . import public

app_name = "aprende"

urlpatterns = [
    path("", public.portada, name="portada"),
    path("lecciones/<int:pk>/", public.leccion, name="leccion"),
    path("lecciones/<int:pk>/vista/", public.marcar, name="marcar"),
    path("directo/", public.directo, name="directo"),
    path("evaluacion/", public.evaluacion, name="evaluacion"),
    path("archivos/<int:bloque_pk>/", public.archivo, name="archivo"),
    path("imagenes/<int:item_pk>/", public.imagen, name="imagen"),
    path("encabezado/", public.encabezado, name="encabezado"),
]
