from decimal import Decimal

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalogs.models import GrupoImpactado
from apps.core.models import Membership, Role
from apps.core.tenancy import tenant_context
from apps.formularios.models import (
    Acta,
    Criterio,
    Enlace,
    EstadoCertificacion,
    EstadoCuestionario,
    Evaluacion,
    ListaObservacion,
    Persona,
    Respuesta,
)

pytestmark = pytest.mark.django_db
E = EstadoCertificacion
BASE = "/c/acme/formularios/"


@pytest.fixture
def setup(acme, equipo, member, make_impacto, make_cuestionario):
    """Impact needing certification, a published checklist with 2 criteria, a leader with
    three reports: two passed the questionnaire, one failed; plus someone else's report."""
    leader, _ = member(Role.LIDER_AREA, client=acme, email="lider@x.com")
    with tenant_context(acme):
        norte = GrupoImpactado.objects.create(name="Norte")
        impacto = make_impacto(requiere_certificacion_lider=True, grupo=norte)
        c = make_cuestionario(1, impacto=impacto)
        c.estado = EstadoCuestionario.PUBLICADO
        c.save()
        people = {}
        for email, passed in [("ana@x.com", True), ("beto@x.com", True), ("caro@x.com", False)]:
            p = Persona.objects.create(
                email=email,
                nombre=email.split("@")[0].title(),
                supervisor="LIDER@x.com",
                grupo=norte,
            )
            enlace = Enlace.objects.create(cuestionario=c, persona=p)
            Respuesta.objects.create(
                enlace=enlace,
                intento=1,
                elecciones={},
                puntos_por_pregunta={},
                puntaje=Decimal("90" if passed else "20"),
                aprobado=passed,
            )
            people[email] = p
        Persona.objects.create(email="otro@x.com", supervisor="otro-lider@x.com", grupo=norte)
        lista = ListaObservacion.objects.create(
            impacto=impacto, titulo="Observación", creada_por=equipo, estado="publicada"
        )
        c1 = Criterio.objects.create(lista=lista, texto="Registra el pago", orden=1)
        c2 = Criterio.objects.create(lista=lista, texto="Concilia", orden=2)
    return {
        "leader": leader,
        "lista": lista,
        "criterios": [c1, c2],
        "people": people,
        "impacto": impacto,
        "grupo": norte,
    }


def pdf_upload(name="firmado.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 signed")


class TestTeam:
    def test_only_reports_who_passed_the_questionnaire(self, client, setup):
        client.force_login(setup["leader"])
        body = client.get(f"{BASE}evaluar/{setup['lista'].pk}/").content.decode()
        assert "Ana" in body and "Beto" in body
        assert "Caro" not in body and "otro@x.com" not in body

    def test_without_questionnaire_uses_the_impact_group(self, setup, acme):
        from apps.formularios.certificacion import team

        with tenant_context(acme):
            setup["impacto"].cuestionarios.update(impacto=None)
            emails = set(team(setup["lista"], "lider@x.com").values_list("email", flat=True))
        assert emails == {"ana@x.com", "beto@x.com", "caro@x.com"}

    def test_leader_home_card_and_list(self, client, setup):
        client.force_login(setup["leader"])
        assert "Evaluación práctica" in client.get("/c/acme/").content.decode()
        body = client.get(f"{BASE}evaluar/").content.decode()
        assert "Observación" in body and "0 / 2" in body


class TestEvaluate:
    def post_results(self, client, setup, results):
        """results: {email: [bool per criterion]}"""
        lista, (c1, c2) = setup["lista"], setup["criterios"]
        client.get(f"{BASE}evaluar/{lista.pk}/")  # creates the evaluations
        data = {}
        for email, values in results.items():
            ev = Evaluacion.unscoped.get(lista=lista, persona__email=email)
            for crit, value in zip((c1, c2), values, strict=False):
                data[f"e{ev.pk}-c{crit.pk}"] = "si" if value else "no"
            data[f"e{ev.pk}-obs"] = "obs"
        return client.post(f"{BASE}evaluar/{lista.pk}/", data)

    def states(self, setup):
        return dict(
            Evaluacion.unscoped.filter(lista=setup["lista"]).values_list("persona__email", "estado")
        )

    def test_full_flow_certifies_only_if_all_criteria_met(
        self, client, setup, member, acme, django_capture_on_commit_callbacks
    ):
        guia, _ = member(Role.GUIA, client=acme, email="guia@x.com")
        with tenant_context(acme):
            Membership.objects.get(user=guia).grupos.set([setup["grupo"]])
        client.force_login(setup["leader"])

        self.post_results(client, setup, {"ana@x.com": [True, True], "beto@x.com": [True]})
        assert self.states(setup) == {"ana@x.com": E.APLICADO, "beto@x.com": E.PENDIENTE}
        self.post_results(client, setup, {"beto@x.com": [True, False]})
        assert self.states(setup)["beto@x.com"] == E.APLICADO

        pdf = client.get(f"{BASE}evaluar/{setup['lista'].pk}/pdf/")
        assert pdf["Content-Type"] == "application/pdf" and pdf.content.startswith(b"%PDF")

        with django_capture_on_commit_callbacks(execute=True):
            client.post(f"{BASE}evaluar/{setup['lista'].pk}/acta/", {"archivo": pdf_upload()})
        assert self.states(setup) == {"ana@x.com": E.CERTIFICADO, "beto@x.com": E.EN_REFUERZO}
        assert mail.outbox[-1].to == ["guia@x.com"]
        assert "Beto" in mail.outbox[-1].body and "Ana" not in mail.outbox[-1].body

    def test_certified_results_are_locked_but_refuerzo_can_be_reevaluated(self, client, setup):
        client.force_login(setup["leader"])
        self.post_results(client, setup, {"ana@x.com": [True, True], "beto@x.com": [False, False]})
        client.post(f"{BASE}evaluar/{setup['lista'].pk}/acta/", {"archivo": pdf_upload()})
        self.post_results(client, setup, {"ana@x.com": [False, False], "beto@x.com": [True, True]})
        states = self.states(setup)
        assert states["ana@x.com"] == E.CERTIFICADO
        assert states["beto@x.com"] == E.APLICADO  # re-evaluated, waits for a new signature
        client.post(f"{BASE}evaluar/{setup['lista'].pk}/acta/", {"archivo": pdf_upload("2.pdf")})
        assert self.states(setup)["beto@x.com"] == E.CERTIFICADO

    def test_upload_needs_applied_evaluations_and_a_pdf_or_image(self, client, setup):
        client.force_login(setup["leader"])
        url = f"{BASE}evaluar/{setup['lista'].pk}/acta/"
        r = client.post(url, {"archivo": pdf_upload()}, follow=True)
        assert "No hay evaluaciones aplicadas" in r.content.decode()
        self.post_results(client, setup, {"ana@x.com": [True, True]})
        r = client.post(url, {"archivo": SimpleUploadedFile("x.docx", b"x")}, follow=True)
        assert "PDF o una imagen" in r.content.decode()
        assert self.states(setup)["ana@x.com"] == E.APLICADO


class TestDesignAndFollowUp:
    def test_guide_builds_and_publishes_a_list(self, client, member, acme, make_impacto, equipo):
        impacto = make_impacto(requiere_certificacion_lider=True)
        guia, _ = member(Role.GUIA, client=acme, email="guia@x.com")
        client.force_login(guia)
        assert "Crear lista" in client.get(f"{BASE}listas/").content.decode()
        client.post(f"{BASE}listas/nueva/{impacto.numero}/", {"titulo": "Obs", "instrucciones": ""})
        lista = ListaObservacion.unscoped.get()
        response = client.post(f"{BASE}listas/{lista.pk}/publicar/", follow=True)
        assert "Agrega al menos un criterio" in response.content.decode()
        client.post(f"{BASE}listas/{lista.pk}/", {"c-texto": "Hace la conciliación"})
        client.post(f"{BASE}listas/{lista.pk}/publicar/")
        lista.refresh_from_db()
        assert lista.estado == "publicada"
        client.post(f"{BASE}listas/{lista.pk}/", {"c-texto": "Otro"})  # locked now
        assert Criterio.unscoped.filter(lista=lista).count() == 1

    def test_impacts_without_certification_have_no_list(self, client, equipo, make_impacto):
        impacto = make_impacto(requiere_certificacion_lider=False)
        client.force_login(equipo)
        assert client.get(f"{BASE}listas/nueva/{impacto.numero}/").status_code == 404

    def test_follow_up_visibility(self, client, setup, equipo, member, acme):
        client.force_login(setup["leader"])
        TestEvaluate().post_results(
            client, setup, {"ana@x.com": [True, True], "beto@x.com": [True, False]}
        )
        client.post(f"{BASE}evaluar/{setup['lista'].pk}/acta/", {"archivo": pdf_upload()})
        url = f"{BASE}listas/{setup['lista'].pk}/seguimiento/"

        client.force_login(equipo)  # change team: everything
        body = client.get(url).content.decode()
        assert "Detalle individual" in body and "Ana" in body and "firmado.pdf" in body

        guia, _ = member(Role.GUIA, client=acme, email="guia@x.com")
        client.force_login(guia)  # guide: only who is in reinforcement
        body = client.get(url).content.decode()
        assert "En refuerzo" in body and "Beto" in body
        assert "Detalle individual" not in body and ">Ana<" not in body

        # Administración also designs training, so it sees who needs reinforcement, but not
        # the individual detail.
        admin, _ = member(Role.ADMINISTRACION, client=acme, email="adm@x.com")
        client.force_login(admin)
        body = client.get(url).content.decode()
        assert "Beto" in body and "Detalle individual" not in body and ">Ana<" not in body

    def test_impact_page_summary(self, client, setup, equipo):
        client.force_login(setup["leader"])
        TestEvaluate().post_results(client, setup, {"ana@x.com": [True, True]})
        client.post(f"{BASE}evaluar/{setup['lista'].pk}/acta/", {"archivo": pdf_upload()})
        client.force_login(equipo)
        body = client.get(f"/c/acme/matriz/{setup['impacto'].numero}/").content.decode()
        assert "Certificación del líder" in body and "<strong>1</strong> certificados" in body

    @pytest.mark.parametrize("role", [Role.CAPITAN, Role.PATROCINADOR, Role.EQUIPO_TECNICO])
    def test_other_roles_cannot_evaluate(self, client, member, acme, setup, role):
        user, _ = member(role, client=acme, email="x@x.com")
        client.force_login(user)
        assert client.get(f"{BASE}evaluar/").status_code == 403
        assert client.get(f"{BASE}evaluar/{setup['lista'].pk}/").status_code == 403

    def test_signed_summary_download_is_protected(self, client, setup, member, acme):
        client.force_login(setup["leader"])
        TestEvaluate().post_results(client, setup, {"ana@x.com": [True, True]})
        client.post(f"{BASE}evaluar/{setup['lista'].pk}/acta/", {"archivo": pdf_upload()})
        acta = Acta.unscoped.get()
        url = f"{BASE}listas/{setup['lista'].pk}/actas/{acta.pk}/"
        assert client.get(url).status_code == 200
        other, _ = member(Role.LIDER_AREA, client=acme, email="otro-lider@x.com")
        client.force_login(other)
        assert client.get(url).status_code == 403
