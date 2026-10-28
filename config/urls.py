from django.contrib import admin
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from apps.formularios import public as formularios_public

urlpatterns = [
    path("admin/", admin.site.urls),
    # Browsers ask for /favicon.ico on their own; point them at the real icon.
    path("favicon.ico", RedirectView.as_view(url=static("img/favicon.svg"), permanent=True)),
    path("plataforma/", include("apps.plataforma.urls")),
    path("f/<str:token>/", formularios_public.responder, name="formularios_responder"),
    path("a/<str:token>/", include("apps.aprendizaje.urls_publicas")),
    path("", include("apps.core.urls")),
]
