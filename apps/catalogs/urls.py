from django.urls import path

from . import views

app_name = "catalogs"

urlpatterns = [
    path("", views.config_index, name="index"),
    path("personas/", views.personas, name="personas"),
    path("personas/<int:pk>/", views.persona_grupos, name="persona_grupos"),
    path("<slug:catalog>/", views.catalog_list, name="list"),
    path("<slug:catalog>/<int:pk>/", views.catalog_edit, name="edit"),
]
