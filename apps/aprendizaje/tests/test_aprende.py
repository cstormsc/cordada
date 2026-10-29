"""Phase 2: a person climbing a course through their link, their team and badges."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.aprendizaje import avance, cursos
from apps.aprendizaje.models import (
    Ajustes,
    Bloque,
    EstadoCurso,
    Inscripcion,
)
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.formularios.models import Enlace, Persona, Respuesta

from .test_cursos import TestBloques, base, items, lecciones, page

pytestmark = pytest.mark.django_db


def publicar(acme, c):
    with tenant_context(acme):
        c.estado = EstadoCurso.PUBLICADO
        c.save()


def inscribir(acme, c, email="ana@example.com", **persona):
    with tenant_context(acme):
        p = Persona.objects.create(email=email, nombre=email.split("@")[0].title(), **persona)
        return Inscripcion.objects.create(curso=c, persona=p)


def url(ins, name="portada", **kwargs):
    return reverse(f"aprende:{name}", kwargs={"token": ins.token, **kwargs})


def refresh(acme, obj):
    with tenant_context(acme):
        obj.refresh_from_db()
    return obj


class TestEnlaces:
    def test_generate_and_export(self, client, equipo, acme, make_curso):
        c = make_curso(1)
        client.force_login(equipo)
        r = client.post(f"{base(c)}personas/")
        assert r.url == base(c)  # a draft has no links yet
        publicar(acme, c)
        with tenant_context(acme):
            Persona.objects.create(email="ana@example.com", sucursal="Centro")
            Persona.objects.create(email="beto@example.com", is_active=False)
        client.post(f"{base(c)}personas/")
        client.post(f"{base(c)}personas/")  # again: no duplicates
        with tenant_context(acme):
            assert Inscripcion.objects.filter(curso=c).count() == 1
        body = client.get(f"{base(c)}personas/").content.decode()
        assert "1 persona inscrita" in body and "Centro" in body and "ana@example.com" in body
        r = client.get(f"{base(c)}personas/exportar/?formato=csv")
        assert "ana@example.com" in r.content.decode() and "/a/" in r.content.decode()
        r = client.get(f"{base(c)}personas/exportar/")
        assert r["Content-Type"].startswith("application/vnd.openxml")

    def test_admin_sees_teams_but_not_people(self, client, member, acme, make_curso):
        c = make_curso(1)
        publicar(acme, c)
        inscribir(acme, c, sucursal="Centro")
        admin, _ = member(Role.ADMINISTRACION, client=acme, email="admin@example.com")
        client.force_login(admin)
        body = client.get(f"{base(c)}personas/").content.decode()
        assert "Avance por cordada" in body and "Detalle por persona" not in body


class TestRecorrido:
    def test_lessons_in_order_until_the_summit(self, client, acme, make_curso):
        c = make_curso(2)
        l1, l2 = lecciones(acme, c)
        with tenant_context(acme):
            l2.depende_de.add(l1)
        publicar(acme, c)
        ins = inscribir(acme, c)
        body = page(client, url(ins))
        assert "Hola, Ana." in body and "Tu expedición" in body
        r = client.get(url(ins, "leccion", pk=l2.pk))
        assert r.url == f"{url(ins)}?bloqueada={l2.pk}"
        assert "tapada por la niebla" in client.get(r.url).content.decode()
        assert client.post(url(ins, "marcar", pk=l2.pk)).url.endswith(f"?bloqueada={l2.pk}")

        body = client.get(url(ins, "leccion", pk=l1.pk)).content.decode()
        assert "Llegar a Campo 1" in body
        assert refresh(acme, ins).iniciada_at is not None
        assert client.post(url(ins, "marcar", pk=l1.pk)).url == url(ins, "leccion", pk=l2.pk)
        assert refresh(acme, ins).completada_at is None
        assert client.post(url(ins, "marcar", pk=l2.pk)).url == url(ins)
        assert refresh(acme, ins).completada_at is not None
        body = page(client, url(ins))
        assert "¡Hiciste cumbre!" in body and "3 474 m" in body
        assert "Ya la viste" in client.get(url(ins, "leccion", pk=l1.pk)).content.decode()

    def test_straight_to_the_evaluation(self, client, acme, make_curso, make_evaluacion):
        c = make_curso(2, evaluacion=make_evaluacion())
        publicar(acme, c)
        ins = inscribir(acme, c)
        assert client.get(url(ins, "evaluacion")).url == url(ins)  # lessons first
        client.post(url(ins, "directo"))  # no confirmation: nothing happens
        assert refresh(acme, ins).directo_at is None
        r = client.post(url(ins, "directo"), {"confirmo": "1"})
        assert r.url == url(ins, "evaluacion") and refresh(acme, ins).directo_at
        r = client.get(r.url)
        with tenant_context(acme):
            enlace = Enlace.objects.get(cuestionario=c.evaluacion, persona=ins.persona)
        assert r.url == reverse("formularios_responder", args=[enlace.token])

        with tenant_context(acme):
            Respuesta.objects.create(
                enlace=enlace, intento=1, elecciones={}, puntos_por_pregunta={},
                puntaje=100, aprobado=True,
            )  # fmt: skip
        body = client.get(url(ins)).content.decode()
        assert "Aprobaste la evaluación" in body
        assert refresh(acme, ins).completada_at is not None
        with tenant_context(acme):
            ganadas = {i["clave"] for i in avance.insignias(ins) if i["ganada"]}
        assert ganadas == {"cumbre", "ventana", "alpino"}

    def test_files_and_banner_through_the_link(self, client, acme, make_curso):
        c, otro = make_curso(1), make_curso(1)
        publicar(acme, c)
        ins = inscribir(acme, c)
        (leccion,) = lecciones(acme, c)
        (ajena,) = lecciones(acme, otro)
        with tenant_context(acme):
            png = SimpleUploadedFile("a.png", b"\x89PNG x", content_type="image/png")
            mia = Bloque.objects.create(leccion=leccion, tipo="imagen", archivo=png)
            png = SimpleUploadedFile("b.png", b"\x89PNG x", content_type="image/png")
            no = Bloque.objects.create(leccion=ajena, tipo="imagen", archivo=png)
        assert client.get(url(ins, "archivo", bloque_pk=mia.pk)).status_code == 200
        assert client.get(url(ins, "archivo", bloque_pk=no.pk)).status_code == 404
        assert client.get(url(ins, "encabezado")).status_code == 404  # none set

    def test_links_that_do_not_open(self, client, acme, make_curso):
        c = make_curso(1)
        ins = inscribir(acme, c)
        assert client.get(url(ins)).status_code == 404  # still a draft
        publicar(acme, c)
        with tenant_context(acme):
            Persona.objects.filter(pk=ins.persona_id).update(is_active=False)
        assert client.get(url(ins)).status_code == 404
        with tenant_context(acme):
            Persona.objects.filter(pk=ins.persona_id).update(is_active=True)
            c.estado = EstadoCurso.CERRADO
            c.save()
        r = client.get(url(ins))
        assert r.status_code == 410 and "Este curso ya cerró" in r.content.decode()
        assert client.get("/a/basura/").status_code == 404

    def test_plain_look_has_no_team_or_badges(self, client, acme, make_curso):
        c = make_curso(1)
        publicar(acme, c)
        ins = inscribir(acme, c, sucursal="Centro")
        with tenant_context(acme):
            Ajustes.objects.create(expedicion=False)
        body = client.get(url(ins)).content.decode()
        assert "Tu cordada" not in body and "Insignias" not in body
        (leccion,) = lecciones(acme, c)
        assert (
            "Marcar como vista" in client.get(url(ins, "leccion", pk=leccion.pk)).content.decode()
        )


class TestCordada:
    def test_the_team_reaches_the_summit_together(self, client, acme, make_curso):
        c = make_curso(1, fecha_limite=timezone.localdate())
        publicar(acme, c)
        (leccion,) = lecciones(acme, c)
        ana = inscribir(acme, c, "ana@example.com", sucursal="Centro")
        beto = inscribir(acme, c, "beto@example.com", sucursal="Centro")
        inscribir(acme, c, "caro@example.com", sucursal="Norte")
        client.post(url(ana, "marcar", pk=leccion.pk))
        body = page(client, url(ana))
        assert "Tu cordada: Centro" in body and "1 de 2 personas en cumbre" in body
        assert "beto" not in body.lower()  # never names
        client.post(url(beto, "marcar", pk=leccion.pk))
        assert "¡Tu cordada hizo cumbre!" in page(client, url(ana))
        with tenant_context(acme):
            ana = Inscripcion.objects.get(pk=ana.pk)
            equipo = avance.cordada(ana)
            assert {i["clave"] for i in avance.insignias(ana, equipo) if i["ganada"]} == {
                "cumbre",
                "ventana",
                "cordada",
            }

    def test_late_summits_do_not_count_for_the_team(self, acme, make_curso):
        c = make_curso(1, fecha_limite=timezone.localdate())
        publicar(acme, c)
        ana = inscribir(acme, c, "ana@example.com", sucursal="Centro")
        beto = inscribir(acme, c, "beto@example.com", sucursal="Centro")
        with tenant_context(acme):
            ayer = timezone.now() - timezone.timedelta(days=1)
            manana = timezone.now() + timezone.timedelta(days=2)
            Inscripcion.objects.filter(pk=ana.pk).update(completada_at=ayer)
            Inscripcion.objects.filter(pk=beto.pk).update(completada_at=manana)
            equipo = avance.cordada(Inscripcion.objects.get(pk=ana.pk))
        assert equipo["arriba"] == 1 and not equipo["lograda"]
        with tenant_context(acme):
            Ajustes.objects.create(meta_cordada=50)
            assert avance.cordada(Inscripcion.objects.get(pk=ana.pk))["lograda"]

    @pytest.mark.parametrize(
        "datos,cordada",
        [
            ({"sucursal": "Centro", "departamento": "Cajas"}, "Centro"),
            ({"departamento": "Cajas", "oficina": "Torre"}, "Cajas"),
            ({"oficina": " Torre "}, "Torre"),
            ({}, None),
        ],
    )
    def test_who_climbs_together(self, datos, cordada):
        assert avance.cordada_de(Persona(email="x@example.com", **datos)) == cordada


class TestJuegosNuevos:
    url = TestBloques.url

    def test_classify_needs_groups_and_a_group_per_card(self, client, equipo, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        client.force_login(equipo)
        u = self.url(c, leccion, "clasificar")
        cards = items(("Caja → Arqueos", ""), ("Fax", ""), ("Doble factor", ""))
        r = client.post(u, {"grupo_1": "Lo llevo", "grupo_2": "", **cards})
        assert "obligatorio" in r.content.decode()
        r = client.post(u, {"grupo_1": "Lo llevo", "grupo_2": "Lo dejo", **cards})
        assert "Elige el grupo de cada tarjeta" in r.content.decode()
        cards.update({"it-0-grupo": "1", "it-1-grupo": "2", "it-2-grupo": "1"})
        client.post(u, {"grupo_1": "Lo llevo", "grupo_2": "Lo dejo", **cards})
        with tenant_context(acme):
            b = Bloque.objects.get(leccion=leccion, tipo="clasificar")
            assert b.grupos == ["Lo llevo", "Lo dejo"]
            assert [i.grupo for i in b.items.all()] == [1, 2, 1]
        body = page(client, f"{base(c)}vista-previa/{leccion.pk}/")
        assert "Arma la mochila" in body and f'id="clasificar-{b.pk}"' in body
        assert '"grupos": ["Lo llevo", "Lo dejo"]' in body

    def test_scenario_needs_a_consequence_per_decision(self, client, equipo, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        client.force_login(equipo)
        u = self.url(c, leccion, "escenario")
        situacion = {"texto": "Un cliente pide su saldo por teléfono."}
        r = client.post(u, {**situacion, **items(("Se lo doy", "", True), ("Verifico", "Bien"))})
        assert "Escribe qué pasa con cada decisión" in r.content.decode()
        client.post(u, {**situacion, **items(("Se lo doy", "Riesgo"), ("Verifico", "Bien", True))})
        body = page(client, f"{base(c)}vista-previa/{leccion.pk}/")
        assert "Decisión en la arista" in body and "Un cliente pide su saldo" in body

    def test_flip_cards_need_both_sides(self, client, equipo, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        client.force_login(equipo)
        u = self.url(c, leccion, "tarjetas")
        r = client.post(u, items(("KYC", "Conoce a tu cliente"), ("SLA", "")))
        assert "frente y su reverso" in r.content.decode()
        client.post(u, items(("KYC", "Conoce a tu cliente"), ("SLA", "Nivel de servicio")))
        body = page(client, f"{base(c)}vista-previa/{leccion.pk}/")
        assert "Tarjetas de nudos" in body and "Conoce a tu cliente" in body


class TestPantallas:
    url = TestBloques.url

    def test_breaks_and_games_split_the_lesson(self):
        def b(pk, tipo, titulo="", exigir=False):
            return Bloque(pk=pk, tipo=tipo, titulo=titulo, exigir_juego=exigir)

        lista = [
            b(1, "corte", "Ignorado: no hay nada antes"),
            b(2, "texto"),
            b(3, "nota"),
            b(4, "corte", "Segunda"),
            b(5, "corte"),  # two breaks in a row make one
            b(6, "imagen"),
            b(7, "pregunta"),
            b(8, "corte", exigir=True),
            b(9, "ordenar"),
            b(10, "texto"),
            b(11, "corte"),  # a break at the end leaves no empty screen
        ]
        out = cursos.pantallas(lista)
        assert [[x.pk for x in p["bloques"]] for p in out] == [[2, 3], [6], [7], [9], [10]]
        assert [p["titulo"] for p in out] == ["Ignorado: no hay nada antes", "Segunda", "", "", ""]
        assert [p["exigir"] for p in out] == [False, False, True, False, False]
        assert [p["juegos"] for p in out] == [[], [], [7], [9], []]
        assert len(cursos.pantallas([b(1, "texto"), b(2, "nota")])) == 1
        assert cursos.pantallas([]) == []

    def test_a_break_in_the_editor_and_the_lesson(self, client, equipo, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        client.force_login(equipo)
        client.post(self.url(c, leccion, "texto"), {"titulo": "Uno", "texto": "Primera parte."})
        body = page(client, f"{base(c)}vista-previa/{leccion.pk}/")
        assert "Primera parte." in body and "tramos(" not in body
        client.post(self.url(c, leccion, "corte"), {"titulo": "La segunda", "exigir_juego": "on"})
        client.post(self.url(c, leccion, "texto"), {"titulo": "Dos", "texto": "Segunda parte."})
        with tenant_context(acme):
            corte = Bloque.objects.get(leccion=leccion, tipo="corte")
            assert corte.exigir_juego and corte.titulo == "La segunda"
        editor = page(client, f"{base(c)}lecciones/{leccion.pk}/")
        assert 'class="corte"' in editor and "Exige el juego" in editor
        body = page(client, f"{base(c)}vista-previa/{leccion.pk}/")
        assert 'x-data="tramos(2)"' in body and "Tramo" in body
        assert body.index("Primera parte.") < body.index("Continuar") < body.index("La segunda")
        assert body.index("La segunda") < body.index("Segunda parte.")
        assert body.count("leccion-nav") == 1 and body.index("Segunda parte.") < body.index(
            "leccion-nav"
        )

    def test_public_lesson_with_a_required_game(self, client, acme, make_curso):
        c = make_curso(1)
        (leccion,) = lecciones(acme, c)
        with tenant_context(acme):
            Bloque.objects.create(leccion=leccion, orden=1, tipo="texto", texto="Intro.")
            q = Bloque.objects.create(leccion=leccion, orden=2, tipo="pregunta", texto="¿Cuál?")
            q.items.create(orden=1, titulo="Esta", correcta=True)
            q.items.create(orden=2, titulo="Otra")
            Bloque.objects.create(leccion=leccion, orden=3, tipo="corte", exigir_juego=True)
            Bloque.objects.create(leccion=leccion, orden=4, tipo="texto", texto="Fin.")
        publicar(acme, c)
        ins = inscribir(acme, c)
        body = page(client, url(ins, "leccion", pk=leccion.pk))
        assert 'x-data="tramos(3)"' in body
        assert f'data-exigir="1" data-juegos="{q.pk}"' in body
        assert f"$dispatch('juego-resuelto', {q.pk})" in body
        assert "Resuelve el juego para seguir subiendo." in body


def test_preview_shows_badges_and_a_sample_team(client, equipo, acme, make_curso):
    c = make_curso(1)
    client.force_login(equipo)
    body = page(client, f"{base(c)}vista-previa/")
    assert "Insignias" in body and "Estilo alpino" in body and "Ejemplo:" in body
