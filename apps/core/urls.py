from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("entrar/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("salir/", views.logout_view, name="logout"),
    path("invitacion/<str:token>/", views.accept_invitation, name="accept_invitation"),
    path("c/<slug:client_slug>/", views.client_home, name="client_home"),
    path("health/", views.health, name="health"),
]
