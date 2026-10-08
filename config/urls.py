from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("plataforma/", include("apps.plataforma.urls")),
    path("", include("apps.core.urls")),
]
