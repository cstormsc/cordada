from django.urls import path

from . import views

app_name = "plataforma"

urlpatterns = [
    path("", views.client_list, name="client_list"),
    path("clientes/nuevo/", views.client_create, name="client_create"),
    path("clientes/<slug:slug>/", views.client_detail, name="client_detail"),
    path("clientes/<slug:slug>/invitar/", views.invite, name="invite"),
    path(
        "clientes/<slug:slug>/invitaciones/<int:pk>/anular/",
        views.revoke_invitation,
        name="revoke_invitation",
    ),
    path(
        "clientes/<slug:slug>/miembros/<int:pk>/", views.membership_update, name="membership_update"
    ),
    path("catalogos/", views.catalog_index, name="catalog_index"),
    path("catalogos/<slug:catalog>/nuevo/", views.catalog_item, name="catalog_item_create"),
    path("catalogos/<slug:catalog>/<int:pk>/", views.catalog_item, name="catalog_item_edit"),
    path("escalas/<slug:code>/", views.scale_edit, name="scale_edit"),
]
