import pytest
from django.core.management import call_command

from apps.bitacora.models import Ticket
from apps.core.models import Client, Membership, Role, User
from apps.core.tenancy import tenant_context
from apps.formularios.models import Evaluacion, Respuesta
from apps.matriz.models import Impacto
from apps.plataforma import demo
from apps.ruta.models import Actividad

pytestmark = pytest.mark.django_db


def test_demo_builds_every_module_and_rebuilds(client, make_user):
    admin = make_user("presentador@example.com")
    call_command("seed_demo", email=admin.email)
    c = Client.objects.get(slug=demo.SLUG)
    with tenant_context(c):
        estados = set(Impacto.objects.values_list("estado", flat=True))
        assert estados >= {
            "propuesto",
            "evaluado",
            "en_atencion",
            "atendido",
            "cerrado",
            "descartado",
            "reabierto",
        }
        assert Actividad.objects.count() >= 15 and Ticket.objects.count() >= 15
        assert (
            Respuesta.objects.exists() and Evaluacion.objects.filter(estado="certificado").exists()
        )
    assert Membership.objects.get(user=admin, client=c).role == Role.ADMINISTRACION
    others = User.objects.filter(email__endswith=f"@{demo.DOMAIN}")
    assert others.exists() and not any(u.has_usable_password() for u in others)

    # Every main page renders for the presenter.
    client.force_login(admin)
    pages = [
        "", "matriz/", "matriz/lista/", "ruta/", "ruta/informe/", "bitacora/",
        "bitacora/metricas/", "formularios/", "formularios/1/resultados/",
        "formularios/listas/", "dashboard/", "guia/", "configuracion/personas/",
    ]  # fmt: skip
    for path in pages:
        assert client.get(f"/c/{demo.SLUG}/{path}").status_code == 200, path

    call_command("seed_demo", email=admin.email, reset=True)  # rebuild from scratch
    assert Client.objects.filter(slug=demo.SLUG).count() == 1
    with tenant_context(Client.objects.get(slug=demo.SLUG)):
        assert Impacto.objects.count() == 13


def test_demo_needs_an_existing_account():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="No existe una cuenta"):
        call_command("seed_demo", email="nadie@example.com")
