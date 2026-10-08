import pytest

from apps.core.models import Client, Membership, Role, User


@pytest.fixture
def make_user(db):
    def make(email="persona@example.com", **kwargs):
        return User.objects.create_user(email=email, password="clave-segura-123", **kwargs)

    return make


@pytest.fixture
def platform_admin(make_user):
    return make_user("admin@cordada.local", is_platform_admin=True)


@pytest.fixture
def make_client(db):
    def make(slug="acme", **kwargs):
        return Client.objects.create(name=kwargs.pop("name", slug.title()), slug=slug, **kwargs)

    return make


@pytest.fixture
def member(make_user, make_client):
    """Returns a factory: member(role, client=None, email=...) -> (user, client)."""

    def make(role=Role.EQUIPO_CAMBIO, client=None, email="miembro@example.com", **kwargs):
        client = client or make_client()
        user = make_user(email)
        Membership.objects.create(user=user, client=client, role=role, **kwargs)
        return user, client

    return make
