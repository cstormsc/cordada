import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.aprendizaje import cursos
from apps.aprendizaje.models import Curso, EstadoCurso, Inscripcion, Leccion
from apps.core.models import Module, Role
from apps.core.tenancy import tenant_context
from apps.formularios.models import EstadoCuestionario, Persona

pytestmark = pytest.mark.django_db
BASE = "/c/acme/aprendizaje/"


def base(c):
    return f"{BASE}{c.numero}/"


def lecciones(acme, c):
    with tenant_context(acme):
        return list(Leccion.objects.filter(curso=c).order_by("orden"))


def deps(acme, leccion):
    with tenant_context(acme):
        return {d.titulo for d in leccion.depende_de.all()}


class TestCurso:
    def test_create_with_impacts_and_evaluation(
        self, client, equipo, acme, make_impacto, make_evaluacion
    ):
        impacto = make_impacto(requiere_formacion=True)
        ev = make_evaluacion()
        client.force_login(equipo)
        r = client.post(
            f"{BASE}nuevo/",
            {"titulo": "Cobranza nueva", "impactos": [impacto.pk], "evaluacion": ev.pk},
        )
        with tenant_context(acme):
            c = Curso.objects.get()
            assert r.url == f"{BASE}{c.numero}/"
            assert c.codigo == "CUR-001"
            assert list(c.impactos.all()) == [impacto]
            assert c.evaluacion == ev
            assert c.creado_por == equipo
        assert "Cobranza nueva" in client.get(BASE).content.decode()

    def test_closed_questionnaires_are_not_offered(self, client, equipo, make_evaluacion):
        abierto = make_evaluacion()
        cerrado = make_evaluacion(EstadoCuestionario.CERRADO)
        client.force_login(equipo)
        body = client.get(f"{BASE}nuevo/").content.decode()
        assert abierto.codigo in body
        assert cerrado.codigo not in body

    def test_numbers_are_per_client(self, make_curso, make_client, equipo):
        assert make_curso().numero == 1
        other = make_client("otro")
        with tenant_context(other):
            assert Curso.objects.create(titulo="X", creado_por=equipo).numero == 1


class TestLecciones:
    def post_lesson(self, client, c, **data):
        data = {"titulo": "Qué cambia", "tipo": "texto", "obligatoria": "on", **data}
        return client.post(f"{base(c)}lecciones/nueva/", data)

    def test_each_type_needs_its_content(self, client, equipo, acme, make_curso):
        c = make_curso()
        client.force_login(equipo)
        r = self.post_lesson(client, c)
        assert "Escribe el contenido" in r.content.decode()
        r = self.post_lesson(client, c, tipo="video")
        assert "Pega el enlace del video" in r.content.decode()
        r = self.post_lesson(client, c, tipo="documento")
        assert "Sube el documento o pega su enlace" in r.content.decode()
        assert lecciones(acme, c) == []

        self.post_lesson(client, c, contenido="El cobro pasa al nuevo sistema.")
        self.post_lesson(client, c, titulo="Demo", tipo="video", url="youtu.be/abc", minutos="5")
        pdf = SimpleUploadedFile("guia.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        self.post_lesson(client, c, titulo="Guía", tipo="documento", archivo=pdf)
        ls = lecciones(acme, c)
        assert [(x.orden, x.tipo) for x in ls] == [(1, "texto"), (2, "video"), (3, "documento")]
        assert ls[1].url == "https://youtu.be/abc"
        assert ls[2].archivo.name.startswith(f"clientes/{acme.pk}/lecciones/")

        r = client.get(f"{base(c)}lecciones/{ls[2].pk}/archivo/")
        assert r.status_code == 200
        assert b"".join(r.streaming_content) == b"%PDF-1.4 x"

    def test_dependencies_refuse_cycles(self, client, equipo, acme, make_curso):
        c = make_curso(3)
        l1, l2, l3 = lecciones(acme, c)
        client.force_login(equipo)

        def edit(leccion, *depende_de):
            return client.post(
                f"{base(c)}lecciones/{leccion.pk}/",
                {
                    "titulo": leccion.titulo,
                    "tipo": "texto",
                    "contenido": "x",
                    "obligatoria": "on",
                    "depende_de": [d.pk for d in depende_de],
                },
            )

        assert edit(l2, l1).status_code == 302
        assert edit(l3, l2).status_code == 302
        r = edit(l1, l3)  # l3 → l2 → l1: would loop back
        assert r.status_code == 200
        assert "Se formaría un ciclo" in r.content.decode()
        assert deps(acme, l1) == set()
        assert deps(acme, l3) == {"L2"}

        body = client.get(base(c)).content.decode()
        assert "Depende de" in body

    def test_cycle_detection(self):
        graph = {1: set(), 2: {1}, 3: {2}}
        assert cursos.creates_cycle(graph, 1, {3})
        assert cursos.creates_cycle(graph, 2, {2})
        assert not cursos.creates_cycle(graph, 3, {1, 2})
        assert not cursos.creates_cycle(graph, 1, set())

    def test_reorder_and_delete_renumber(self, client, equipo, acme, make_curso):
        c = make_curso(3)
        l1, l2, l3 = lecciones(acme, c)
        client.force_login(equipo)
        r = client.post(
            f"{base(c)}ordenar/",
            json.dumps({"ids": [l3.pk, l1.pk, l2.pk]}),
            content_type="application/json",
        )
        assert r.status_code == 204
        assert [x.titulo for x in lecciones(acme, c)] == ["L3", "L1", "L2"]
        assert (
            client.post(f"{base(c)}ordenar/", "{}", content_type="application/json").status_code
            == 400
        )

        client.post(f"{base(c)}lecciones/{l3.pk}/borrar/")
        assert [(x.orden, x.titulo) for x in lecciones(acme, c)] == [(1, "L1"), (2, "L2")]


class TestPublicar:
    def test_publish_errors(self, acme, make_curso, make_evaluacion):
        c = make_curso()
        with tenant_context(acme):
            assert cursos.publish_errors(c) == ["Agrega al menos una lección."]
            Leccion.objects.create(curso=c, titulo="Video", tipo="video", obligatoria=False)
            c.evaluacion = make_evaluacion(EstadoCuestionario.BORRADOR)
            errors = cursos.publish_errors(c)
            assert "Lección 1: pega el enlace del video." in errors
            assert any("debe estar publicada" in e for e in errors)

            c.evaluacion = None
            assert any(
                "marca al menos una lección obligatoria" in e for e in cursos.publish_errors(c)
            )

    def test_publish_freezes_the_structure(self, client, equipo, acme, make_curso):
        c = make_curso(2)
        l1, l2 = lecciones(acme, c)
        client.force_login(equipo)
        client.post(f"{base(c)}publicar/")
        with tenant_context(acme):
            c.refresh_from_db()
        assert c.estado == EstadoCurso.PUBLICADO and c.publicado_at

        assert client.get(f"{base(c)}lecciones/nueva/").status_code == 302
        client.post(f"{base(c)}lecciones/{l1.pk}/borrar/")
        assert len(lecciones(acme, c)) == 2
        r = client.post(
            f"{base(c)}ordenar/",
            json.dumps({"ids": [l2.pk, l1.pk]}),
            content_type="application/json",
        )
        assert r.status_code == 400

        # Content can still be corrected; type and dependencies stay.
        client.post(
            f"{base(c)}lecciones/{l2.pk}/",
            {
                "titulo": "L2 corregida",
                "tipo": "video",
                "contenido": "Texto nuevo",
                "depende_de": [l1.pk],
            },
        )
        (_, l2) = lecciones(acme, c)
        assert (l2.titulo, l2.tipo, l2.contenido, l2.obligatoria) == (
            "L2 corregida",
            "texto",
            "Texto nuevo",
            True,
        )
        assert deps(acme, l2) == set()

        client.post(f"{base(c)}cerrar/")
        with tenant_context(acme):
            c.refresh_from_db()
        assert c.estado == EstadoCurso.CERRADO

    def test_publish_with_errors_stays_draft(self, client, equipo, acme, make_curso):
        c = make_curso()
        client.force_login(equipo)
        r = client.post(f"{base(c)}publicar/", follow=True)
        assert "Agrega al menos una lección." in r.content.decode()
        with tenant_context(acme):
            c.refresh_from_db()
        assert c.is_draft


class TestAcceso:
    def test_guide_designs(self, client, member, acme, make_curso):
        c = make_curso(1)
        guia, _ = member(Role.GUIA, client=acme, email="guia@example.com")
        client.force_login(guia)
        assert client.get(BASE).status_code == 200
        assert client.get(f"{base(c)}lecciones/nueva/").status_code == 200

    @pytest.mark.parametrize("role", [Role.CAPITAN, Role.PATROCINADOR, Role.LIDER_AREA])
    def test_other_roles_are_refused(self, client, member, acme, make_curso, role):
        c = make_curso(1)
        user, _ = member(role, client=acme, email="otro@example.com")
        client.force_login(user)
        for url in (BASE, base(c), f"{base(c)}lecciones/nueva/"):
            assert client.get(url).status_code == 403
        assert client.post(f"{base(c)}publicar/").status_code == 403

    def test_disabled_module(self, client, equipo, acme, make_curso):
        make_curso()
        acme.enabled_modules = [m for m in Module.values if m != Module.APRENDIZAJE]
        acme.save()
        client.force_login(equipo)
        assert client.get(BASE).status_code == 403
        assert "aprendizaje/" not in client.get("/c/acme/").content.decode()

    def test_home_card(self, client, equipo):
        client.force_login(equipo)
        assert "Ascenso y Aprendizaje" in client.get("/c/acme/").content.decode()

    def test_other_clients_courses_are_not_found(self, client, member, make_client, make_curso):
        c = make_curso(1)
        user, _ = member(Role.EQUIPO_CAMBIO, client=make_client("otro"), email="x@example.com")
        client.force_login(user)
        assert client.get(f"/c/otro/aprendizaje/{c.numero}/").status_code == 404


class TestInscripcion:
    def test_token_round_trip_and_revocation(self, acme, make_curso):
        c = make_curso(1)
        with tenant_context(acme):
            p = Persona.objects.create(email="Ana@Example.com")
            i = Inscripcion.objects.create(curso=c, persona=p)
        found = Inscripcion.from_token(i.token)
        assert found == i and found.vencido is False
        old = i.token
        i.version += 1
        with tenant_context(acme):
            i.save()
        assert Inscripcion.from_token(old) is None
        assert Inscripcion.from_token("basura") is None
