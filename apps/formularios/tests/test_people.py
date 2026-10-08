import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.catalogs.models import GrupoImpactado
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.formularios import importer
from apps.formularios.models import Carga, Persona

pytestmark = pytest.mark.django_db
URL = "/c/acme/formularios/personas/cargar/"


def csv_file(text, encoding="utf-8", name="personas.csv"):
    return SimpleUploadedFile(name, text.encode(encoding), content_type="text/csv")


def xlsx_file(rows):
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("personas.xlsx", buf.getvalue())


def test_csv_semicolons_latin1_and_header_aliases():
    headers, rows = importer.read_rows(
        csv_file(
            "Correo electrónico;Nombre;Depto;Jefe\nana@x.com;Ana Núñez;Cobranzas;lider@x.com\n",
            encoding="latin-1",
        )
    )
    mapping = importer.map_headers(headers)
    records, errors = importer.parse(rows, mapping)
    assert records == [
        {
            "email": "ana@x.com",
            "nombre": "Ana Núñez",
            "departamento": "Cobranzas",
            "supervisor": "lider@x.com",
        }
    ]
    assert errors == []


def test_invalid_and_duplicate_emails_are_reported():
    _, rows = importer.read_rows(csv_file("email\nana@x.com\nno-es-correo\nANA@x.com\n"))
    records, errors = importer.parse(rows, {"email": 0})
    assert [r["email"] for r in records] == ["ana@x.com"]
    assert "Fila 3" in errors[0] and "Fila 4" in errors[1]


def test_missing_email_column():
    with pytest.raises(importer.PeopleImportError, match="correo"):
        importer.map_headers(["nombre", "cargo"])


def test_preview_then_confirm_creates_groups_and_upserts(client, equipo, acme):
    with tenant_context(acme):
        Persona.objects.create(email="ana@x.com", nombre="Viejo nombre")
        GrupoImpactado.objects.create(name="Cobranzas")
    client.force_login(equipo)
    response = client.post(
        URL,
        {
            "archivo": xlsx_file(
                [
                    ["correo", "nombre", "departamento"],
                    ["ana@x.com", "Ana", "cobranzas"],
                    ["beto@x.com", "Beto", "Ventas"],
                    ["malo", "", ""],
                ]
            ),
            "columna_grupo": "departamento",
            "crear_grupos": "on",
        },
    )
    body = response.content.decode()
    assert "Vista previa" in body and "1 nuevas" in body and "Fila 4" in body
    with tenant_context(acme):
        assert Persona.objects.count() == 1  # nothing saved yet
    client.post(f"{URL}confirmar/")
    with tenant_context(acme):
        ana = Persona.objects.get(email="ana@x.com")
        beto = Persona.objects.get(email="beto@x.com")
        assert ana.nombre == "Ana" and ana.grupo.name == "Cobranzas"
        assert beto.grupo.name == "Ventas"  # created
        carga = Carga.objects.get()
        assert (carga.creadas, carga.actualizadas, len(carga.errores)) == (1, 1, 1)


def test_confirm_without_preview(client, equipo):
    client.force_login(equipo)
    assert client.post(f"{URL}confirmar/").url == URL


@pytest.mark.parametrize("role", [Role.GUIA, Role.LIDER_AREA, Role.CAPITAN])
def test_only_editors_handle_people(client, member, acme, role):
    user, _ = member(role, client=acme, email="x@example.com")
    client.force_login(user)
    assert client.get("/c/acme/formularios/personas/").status_code == 403
    assert client.get(URL).status_code == 403
