import pytest
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_health_checks_database(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_login_page_renders_in_spanish(client):
    response = client.get("/entrar/")
    assert response.status_code == 200
    assert 'lang="es"' in response.content.decode()


@pytest.mark.django_db
def test_users_log_in_with_email():
    user = get_user_model().objects.create_user(email="Ana@Example.com", password="x-secret-1")
    assert user.email == "Ana@example.com"
    assert user.check_password("x-secret-1")
    assert not user.is_staff


def test_system_checks_and_url_modules_load_without_a_client():
    # Forms built at import time must not query client-scoped models.
    from django.core.management import call_command
    from django.urls import get_resolver

    call_command("check")
    get_resolver().url_patterns  # noqa: B018 (imports every urls/views module)


@pytest.mark.django_db
def test_proposers_home_card_proposes(client, member):
    from apps.core.models import Role

    user, _ = member(Role.CAPITAN, email="cap@example.com")
    client.force_login(user)
    body = client.get(f"/c/{user.memberships.get().client.slug}/").content.decode()
    assert "Proponer un impacto" in body and "/matriz/nuevo/" in body


@pytest.mark.django_db
def test_stylesheet_url_changes_with_the_file(client):
    """Cache busting: the CSS link carries the file's version."""
    import re

    body = client.get("/entrar/").content.decode()
    assert re.search(r'href="/static/css/app\.css\?v=\d+"', body)
