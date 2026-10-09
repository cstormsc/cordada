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


def test_first_and_last_name_columns(client, equipo, acme):
    headers, rows = importer.read_rows(
        csv_file("Correo,Nombres,Apellidos,Puesto\nana@x.com,Ana María,Núñez Soto,Analista\n")
    )
    records, _ = importer.parse(rows, importer.map_headers(headers))
    assert records[0] == {
        "email": "ana@x.com",
        "nombre": "Ana María",
        "apellido": "Núñez Soto",
        "cargo": "Analista",
    }
    with tenant_context(acme):
        persona = Persona.objects.create(**records[0])
        assert str(persona) == "Ana María Núñez Soto"
    client.force_login(equipo)
    page = client.get("/c/acme/formularios/personas/?q=núñez").content.decode()
    assert "<td>Núñez Soto</td><td>Analista</td>" in page


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


class TestSupervisors:
    """The people list is the reporting line: supervisors must be área leaders with an
    account under the same email, or their team can't be evaluated."""

    def test_check_classifies_each_supervisor(self, acme, member, platform_admin):
        from apps.core.models import Invitation
        from apps.formularios import supervisores as S

        member(Role.LIDER_AREA, client=acme, email="Lider@x.com")
        member(Role.CAPITAN, client=acme, email="capitan@x.com")
        Invitation.create(
            client=acme, email="nuevo@x.com", role=Role.LIDER_AREA, invited_by=platform_admin
        )
        result = S.check(
            acme,
            {
                "lider@x.com": 3,
                "capitan@x.com": 2,
                "nuevo@x.com": 1,
                "nadie@x.com": 4,
                "Juan Pérez": 1,
            },
        )
        assert {s.email: s.estado for s in result} == {
            "lider@x.com": S.OK,
            "capitan@x.com": S.OTRO_ROL,
            "nuevo@x.com": S.INVITADO,
            "nadie@x.com": S.SIN_CUENTA,
            "Juan Pérez": S.NO_ES_CORREO,
        }
        assert result[0].email == "nadie@x.com"  # problems first, biggest team first
        assert result[-1].estado == S.OK

    def test_preview_and_people_page_flag_supervisors(self, client, equipo, acme, member):
        member(Role.LIDER_AREA, client=acme, email="lider@x.com")
        client.force_login(equipo)
        body = client.post(
            URL,
            {
                "archivo": csv_file(
                    "correo,jefe\nana@x.com,LIDER@x.com\nbea@x.com,nadie@x.com\n"
                    "cia@x.com,nadie@x.com\n"
                )
            },
        ).content.decode()
        assert "Supervisores" in body and "líder con cuenta" in body
        assert "No tiene cuenta de Líder de área" in body
        client.post("/c/acme/formularios/personas/cargar/confirmar/")
        with tenant_context(acme):
            assert Persona.objects.get(email="ana@x.com").supervisor == "lider@x.com"
        page = client.get("/c/acme/formularios/personas/").content.decode()
        assert "Supervisores sin cuenta de líder" in page
        assert "nadie@x.com" in page and "2 personas" in page
        assert "lider@x.com</span>" not in page  # fine ones are not listed there

    def test_leader_without_team_is_told_why(self, client, member, acme):
        user, _ = member(Role.LIDER_AREA, client=acme, email="lider@x.com")
        client.force_login(user)
        body = client.get("/c/acme/formularios/evaluar/").content.decode()
        assert "nadie tiene a lider@x.com como supervisor" in body
