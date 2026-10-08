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
