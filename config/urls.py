from django.contrib import admin
from django.urls import include, path

from apps.formularios import public as formularios_public

urlpatterns = [
    path("admin/", admin.site.urls),
    path("plataforma/", include("apps.plataforma.urls")),
    path("f/<str:token>/", formularios_public.responder, name="formularios_responder"),
    path("", include("apps.core.urls")),
]
