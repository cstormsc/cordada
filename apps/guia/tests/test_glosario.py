import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template

from apps.catalogs.models import SystemCatalogItem
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.guia import glosario
from apps.matriz.models import Estado

pytestmark = pytest.mark.django_db


@pytest.fixture
def login_as(client, member, acme):
    def login(role):
        user, _ = member(role, client=acme, email=f"{role}@example.com")
        client.force_login(user)
        return user

    return login


def templates():
    return [
        p
        for p in Path(settings.BASE_DIR).glob("**/templates/**/*.html")
        if "node_modules" not in p.parts
    ]


def test_every_help_icon_has_a_definition():
    used = set()
    for path in templates():
        used |= set(re.findall(r'\{% ayuda "(\w+)" %\}', path.read_text()))
    assert used, "no help icons found"
    assert used <= set(glosario.TERMINOS), used - set(glosario.TERMINOS)
    # Keys built in templates from a state or a role.
    for estado in Estado.values:
        assert f"impacto_{estado}" in glosario.TERMINOS
    for role in Role.values:
        assert f"rol_{role}" in glosario.TERMINOS


def render(text, **ctx):
    return Template("{% load guia %}" + text).render(Context(ctx))


def test_help_bubble_links_to_the_glossary_only_when_the_guide_is_on(acme):
    with tenant_context(acme):
        html = render('{% ayuda "descubierto" %}')
        assert "¿Qué significa «Descubierto»?" in html and "ninguna actividad en la Ruta" in html
        assert 'href="/c/acme/guia/#glosario-descubierto"' in html
        assert render('{% ayuda "no-existe" %}') == ""
        acme.enabled_modules = ["matriz"]
        acme.save()
        assert "/guia/" not in render('{% ayuda "descubierto" %}')


def test_catalog_help_uses_the_methodology_text(acme):
    item = SystemCatalogItem(
        catalog="tiempo", code="x", label="Cumbre", help_text="Uno. Dos. Tres."
    )
    with tenant_context(acme):
        html = render("{% ayuda_catalogo item %}", item=item)
    assert "Uno. Dos. …" in html and "Tres" not in html and "#catalogo-tiempo" in html
    assert render("{% ayuda_catalogo item %}", item=SystemCatalogItem(label="Sin ayuda")) == ""


def test_guide_lists_the_glossary_and_puts_the_flag_on_cumbre(client, login_as):
    login_as(Role.GUIA)
    body = client.get("/c/acme/guia/").content.decode()
    assert 'id="glosario"' in body and 'id="glosario-bloqueado"' in body
    assert re.search(r'<li class="summit"><b>Cumbre</b>', body)
