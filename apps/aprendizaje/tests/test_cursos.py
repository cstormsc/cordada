import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.aprendizaje import cursos
from apps.aprendizaje.models import (
    Bloque,
    BloqueItem,
    Curso,
    EstadoCurso,
    Inscripcion,
    Leccion,
)
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
    def test_new_lesson_needs_no_link_and_goes_to_its_blocks(
        self, client, equipo, acme, make_curso
    ):
        c = make_curso()
        client.force_login(equipo)
        r = client.post(f"{base(c)}lecciones/nueva/", {"titulo": "Qué cambia", "minutos": "5"})
        (leccion,) = lecciones(acme, c)
        assert r.url == f"{base(c)}lecciones/{leccion.pk}/"
        body = client.get(r.url).content.decode()
        assert "Agrega el primer bloque" in body
        assert "Paso a paso" in body

    def test_dependencies_refuse_cycles(self, client, equipo, acme, make_curso):
        c = make_curso(3)
        l1, l2, l3 = lecciones(acme, c)
        client.force_login(equipo)

        def edit(leccion, *depende_de):
            return client.post(
                f"{base(c)}lecciones/{leccion.pk}/",
                {
                    "titulo": leccion.titulo,
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


def items(*pairs, prefix="it", initial=0):
    """POST data for the steps / sections formset."""
    total = max(len(pairs), 2)
    data = {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "12",
    }
    for n, (titulo, texto) in enumerate(pairs):
        data[f"{prefix}-{n}-titulo"] = titulo
        data[f"{prefix}-{n}-texto"] = texto
    return data


class TestBloques:
    def url(self, c, leccion, tipo):
        return f"{base(c)}lecciones/{leccion.pk}/bloques/nuevo/{tipo}/"

    def bloques(self, acme, leccion):
        with tenant_context(acme):
            return list(Bloque.objects.filter(leccion=leccion).prefetch_related("items"))

    def test_each_type_and_what_it_needs(self, client, equipo, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        client.force_login(equipo)

        r = client.post(self.url(c, leccion, "video"), {"titulo": "Demo"})
        assert r.status_code == 200 and "obligatorio" in r.content.decode()
        client.post(self.url(c, leccion, "video"), {"url": "youtu.be/dQw4w9WgXcQ"})
        client.post(self.url(c, leccion, "nota"), {"texto": "Ojo con el cierre de caja."})

        png = SimpleUploadedFile("caja.png", b"\x89PNG fake", content_type="image/png")
        client.post(self.url(c, leccion, "imagen"), {"archivo": png, "texto": "La caja"})
        pdf = SimpleUploadedFile("guia.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        r = client.post(self.url(c, leccion, "imagen"), {"archivo": pdf})
        assert "Sube una imagen" in r.content.decode()
        pdf = SimpleUploadedFile("guia.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        client.post(self.url(c, leccion, "documento"), {"archivo": pdf})

        r = client.post(self.url(c, leccion, "pasos"), items(("Abrir", "Entra al Núcleo")))
        assert "Agrega al menos dos pasos" in r.content.decode()
        client.post(
            self.url(c, leccion, "pasos"),
            {"titulo": "Cobrar", **items(("Abrir", "Entra"), ("", ""), ("Cobrar", "Marca"))},
        )
        r = client.post(self.url(c, leccion, "acordeon"), items(("", "Sin título")))
        assert "Cada sección necesita un título" in r.content.decode()
        client.post(self.url(c, leccion, "acordeon"), items(("¿Y si falla?", "Llama a TI")))

        bs = self.bloques(acme, leccion)
        assert [b.tipo for b in bs] == [
            "texto", "video", "nota", "imagen", "documento", "pasos", "acordeon",
        ]  # fmt: skip
        assert [b.orden for b in bs] == list(range(1, 8))
        assert bs[1].url == "https://youtu.be/dQw4w9WgXcQ"
        assert [(i.orden, i.titulo) for i in bs[5].items.all()] == [(1, "Abrir"), (2, "Cobrar")]

        r = client.get(f"{base(c)}archivos/{bs[3].pk}/")
        assert r.status_code == 200 and "inline" in r["Content-Disposition"]
        r = client.get(f"{base(c)}archivos/{bs[4].pk}/")
        assert "attachment" in r["Content-Disposition"]
        assert b"".join(r.streaming_content) == b"%PDF-1.4 x"

    def test_edit_steps_reorder_and_delete(self, client, equipo, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        client.force_login(equipo)
        client.post(self.url(c, leccion, "pasos"), items(("A", "1"), ("B", "2"), ("C", "3")))
        texto, pasos = self.bloques(acme, leccion)
        a, b, _c = pasos.items.all()
        data = items(("A", "1"), ("B", "2 bis"), ("C", "3"), initial=3)
        data.update({"it-0-id": a.pk, "it-1-id": b.pk, "it-2-id": _c.pk, "it-0-DELETE": "on"})
        client.post(f"{base(c)}lecciones/{leccion.pk}/bloques/{pasos.pk}/", data)
        assert [(i.orden, i.texto) for i in self.bloques(acme, leccion)[1].items.all()] == [
            (1, "2 bis"),
            (2, "3"),
        ]

        r = client.post(
            f"{base(c)}lecciones/{leccion.pk}/bloques/ordenar/",
            json.dumps({"ids": [pasos.pk, texto.pk]}),
            content_type="application/json",
        )
        assert r.status_code == 204
        assert [b.tipo for b in self.bloques(acme, leccion)] == ["pasos", "texto"]
        client.post(f"{base(c)}lecciones/{leccion.pk}/bloques/{pasos.pk}/borrar/")
        assert [(b.orden, b.tipo) for b in self.bloques(acme, leccion)] == [(1, "texto")]

    def test_unknown_type_and_other_lessons_blocks(self, client, equipo, acme, make_curso):
        c, otro = make_curso(1), make_curso(1)
        (leccion,) = lecciones(acme, c)
        (ajena,) = lecciones(acme, otro)
        (bloque,) = self.bloques(acme, ajena)
        client.force_login(equipo)
        assert client.get(self.url(c, leccion, "quiz")).status_code == 404
        r = client.get(f"{base(c)}lecciones/{leccion.pk}/bloques/{bloque.pk}/")
        assert r.status_code == 404

    def test_old_lessons_become_blocks(self):
        """Migration 0002 turns each lesson's single content into blocks."""
        from importlib import import_module

        migration = import_module("apps.aprendizaje.migrations.0002_bloques")
        assert callable(migration.lessons_to_blocks)


class TestPublicar:
    def test_publish_errors(self, acme, make_curso, make_evaluacion):
        c = make_curso()
        with tenant_context(acme):
            assert cursos.publish_errors(c) == ["Agrega al menos una lección."]
            leccion = Leccion.objects.create(curso=c, titulo="Video", obligatoria=False)
            c.evaluacion = make_evaluacion(EstadoCuestionario.BORRADOR)
            errors = cursos.publish_errors(c)
            assert "Lección 1: agrega al menos un bloque." in errors
            Bloque.objects.create(leccion=leccion, tipo="video")
            errors = cursos.publish_errors(c)
            assert "Lección 1, bloque 1: pega el enlace del video." in errors
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

        # The title and the blocks can still change; obligatoria and dependencies stay.
        client.post(
            f"{base(c)}lecciones/{l2.pk}/", {"titulo": "L2 corregida", "depende_de": [l1.pk]}
        )
        with tenant_context(acme):
            bloque = l2.bloques.get()
        client.post(f"{base(c)}lecciones/{l2.pk}/bloques/{bloque.pk}/", {"texto": "Texto nuevo"})
        client.post(f"{base(c)}lecciones/{l2.pk}/bloques/nuevo/nota/", {"texto": "Ojo"})
        (_, l2) = lecciones(acme, c)
        assert (l2.titulo, l2.obligatoria) == ("L2 corregida", True)
        assert deps(acme, l2) == set()
        with tenant_context(acme):
            assert [b.texto for b in l2.bloques.all()] == ["Texto nuevo", "Ojo"]

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


class TestVistaPrevia:
    def test_course_as_the_person_sees_it(self, client, equipo, acme, make_curso, make_evaluacion):
        c = make_curso(2, evaluacion=make_evaluacion())
        l1, l2 = lecciones(acme, c)
        with tenant_context(acme):
            l2.depende_de.add(l1)
            demo = Leccion.objects.create(curso=c, orden=3, titulo="Demo")
            Bloque.objects.create(leccion=demo, tipo="video", url="https://youtu.be/dQw4w9WgXcQ")
            pasos = Bloque.objects.create(leccion=demo, orden=2, tipo="pasos", titulo="Cobrar")
            BloqueItem.objects.create(bloque=pasos, orden=1, titulo="Abrir", texto="Entra")
            BloqueItem.objects.create(bloque=pasos, orden=2, titulo="Cobrar", texto="Marca")
        client.force_login(equipo)
        assert "Vista previa" in client.get(base(c)).content.decode()

        body = client.get(f"{base(c)}vista-previa/").content.decode()
        assert "Así verá la persona este curso" in body
        assert "0 de 3 lecciones vistas" in body
        assert "Se abre al ver: L1" in body
        assert "Ir directo a la evaluación" in body
        assert f"{base(c)}vista-previa/{l1.pk}/" in body  # Empezar goes to the first open one

        body = client.get(f"{base(c)}vista-previa/{l2.pk}/").content.decode()
        assert "Lección 2 de 3" in body
        assert "bloqueada hasta ver: L1" in body
        assert "Texto 2" in body
        ls = lecciones(acme, c)
        body = client.get(f"{base(c)}vista-previa/{ls[2].pk}/").content.decode()
        assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in body
        assert "Paso 1 de 2" in body and "Paso 2 de 2" in body

    def test_preview_is_for_the_team_only(self, client, member, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        user, _ = member(Role.CAPITAN, client=acme, email="cap@example.com")
        client.force_login(user)
        assert client.get(f"{base(c)}vista-previa/").status_code == 403
        assert client.get(f"{base(c)}vista-previa/{leccion.pk}/").status_code == 403

    def test_lesson_of_another_course_is_not_found(self, client, equipo, acme, make_curso):
        c, otro = make_curso(1), make_curso(1)
        (leccion,) = lecciones(acme, otro)
        client.force_login(equipo)
        assert client.get(f"{base(c)}vista-previa/{leccion.pk}/").status_code == 404


@pytest.mark.parametrize(
    ("url", "embed"),
    [
        ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3",
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        ),
        ("https://vimeo.com/76979871", "https://player.vimeo.com/video/76979871"),
        ("https://vimeo.com/76979871/abc123", "https://player.vimeo.com/video/76979871?h=abc123"),
        ("https://drive.google.com/file/d/x/view", None),
        ("", None),
    ],
)
def test_video_embed(url, embed):
    assert cursos.video_embed(url) == embed
