import datetime
from decimal import Decimal

import pytest

from apps.bitacora.models import Ticket
from apps.catalogs.models import GrupoImpactado, SystemCatalogItem
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.dashboard import indicators as ind
from apps.dashboard.models import IndicadorConfig, ValorManual
from apps.formularios.models import (
    Cuestionario,
    Enlace,
    EstadoCertificacion,
    Evaluacion,
    ListaObservacion,
    Persona,
    Respuesta,
)
from apps.matriz.models import Estado
from apps.ruta.models import Actividad

pytestmark = pytest.mark.django_db
D = Decimal
TODAY = datetime.date(2026, 10, 15)
URL = "/c/acme/dashboard/"


def item(catalog, code):
    return SystemCatalogItem.objects.get(catalog=catalog, code=code)


def ctx(acme, **kw):
    return ind.Ctx(acme, today=TODAY, **kw)


def act(acme, equipo, frente, **kw):
    data = {
        "titulo": "a",
        "frente": item("frente", frente),
        "registrado_por": equipo,
        "fecha_planificada": datetime.date(2026, 10, 1),
    }
    grupos = kw.pop("grupos", [])
    impactos = kw.pop("impactos", [])
    data.update(kw)
    with tenant_context(acme):
        a = Actividad.objects.create(**data)
        a.grupos.set(grupos)
        a.impactos.set(impactos)
    return a


class TestImpactIndicators:
    def test_plan_and_critical(self, acme, equipo, make_impacto):
        with_plan = make_impacto(complete=True, estado=Estado.EN_ATENCION)
        make_impacto(complete=True, estado=Estado.EVALUADO)  # no activity: no plan
        make_impacto()  # proposed: not counted
        act(acme, equipo, "impactos", impactos=[with_plan])
        make_impacto(probabilidad=4, severidad=4, estado=Estado.CERRADO)  # critical, mitigated
        make_impacto(probabilidad=4, severidad=3, estado=Estado.EN_ATENCION)  # critical, open
        with tenant_context(acme):
            plan = ind.imp_con_plan(ctx(acme))
            crit = ind.imp_criticos(ctx(acme))
        assert plan.value == D(25)  # 1 of the 4 validated impacts
        assert crit.value == D(50) and "1 abiertos" in crit.detail


class TestRutaIndicators:
    def test_messages_on_time_and_coverage(self, acme, equipo):
        with tenant_context(acme):
            norte = GrupoImpactado.objects.create(name="Norte")
            GrupoImpactado.objects.create(name="Sur")
        act(
            acme,
            equipo,
            "comunicacion",
            estado="completado",
            fecha_real=datetime.date(2026, 10, 1),
            grupos=[norte],
        )  # on time
        act(
            acme, equipo, "comunicacion", estado="completado", fecha_real=datetime.date(2026, 10, 9)
        )  # late
        act(acme, equipo, "comunicacion")  # not done
        act(acme, equipo, "comunicacion", fecha_planificada=datetime.date(2026, 12, 1))
        act(acme, equipo, "comunicacion", no_planificada=True, fecha_planificada=None)
        with tenant_context(acme):
            c = ctx(acme)
            assert ind.com_a_tiempo(c).value == D(33)
            assert ind.com_cobertura(c).value == D(50)
            assert ind.com_iniciativa(c).value == D(1)


class TestPeopleIndicators:
    def setup_people(self, acme, equipo, n, passed):
        with tenant_context(acme):
            g = GrupoImpactado.objects.create(name="Norte", personas=50)
            c = Cuestionario.objects.create(titulo="c", creado_por=equipo, estado="publicado")
            for i in range(n):
                p = Persona.objects.create(email=f"p{i}@x.com", grupo=g)
                e = Enlace.objects.create(cuestionario=c, persona=p)
                Respuesta.objects.create(
                    enlace=e,
                    intento=1,
                    elecciones={},
                    puntos_por_pregunta={},
                    puntaje=D(90),
                    aprobado=i < passed,
                )
        return g

    def test_verification_respects_minimum_group_size(self, acme, equipo):
        self.setup_people(acme, equipo, 4, 3)
        with tenant_context(acme):
            r = ind.for_verificacion(ctx(acme))
        assert r.value is None and "menos de 5" in r.detail

    def test_verification_and_readiness(self, acme, equipo, make_impacto):
        g = self.setup_people(acme, equipo, 5, 4)
        make_impacto(grupo=g, estado=Estado.CERRADO)
        make_impacto(grupo=g, estado=Estado.EN_ATENCION)
        with tenant_context(acme):
            assert ind.for_verificacion(ctx(acme)).value == D(80)
            row = next(r for r in ind.readiness_by_group(ctx(acme)) if r["grupo"] == g)
        assert row["parts"] == {"impactos": D(50), "verificacion": D(80)}
        assert row["value"] == D(65)

    def test_certification(self, acme, equipo, make_impacto):
        g = self.setup_people(acme, equipo, 5, 5)
        with tenant_context(acme):
            lista = ListaObservacion.objects.create(
                impacto=make_impacto(grupo=g), titulo="l", creada_por=equipo
            )
            for i, p in enumerate(Persona.objects.all()):
                Evaluacion.objects.create(
                    lista=lista,
                    persona=p,
                    lider=equipo,
                    estado=EstadoCertificacion.CERTIFICADO
                    if i < 4
                    else EstadoCertificacion.EN_REFUERZO,
                )
            assert ind.for_certificacion(ctx(acme)).value == D(80)

    def test_tickets_per_100(self, acme, equipo):
        g = self.setup_people(acme, equipo, 0, 0)
        with tenant_context(acme):
            for _ in range(3):
                Ticket.objects.create(
                    titulo="t",
                    descripcion="d",
                    grupo=g,
                    categoria=item("categoria_ticket", "tecnico"),
                    registrado_por=equipo,
                )
            assert ind.mov_tickets(ctx(acme)).value == D("6.0")


class TestTrafficLight:
    def tile(self, key, value, **cfg):
        i = ind.BY_KEY[key]
        return ind.Tile(
            i,
            ind.Result(D(value)),
            verde=cfg.get("verde", i.verde),
            amarillo=cfg.get("amarillo", i.amarillo),
            responsable="",
            frecuencia="",
        )

    @pytest.mark.parametrize(
        ("value", "status"),
        [(95, "good"), (90, "good"), (80, "warning"), (70, "warning"), (69, "critical")],
    )
    def test_higher_is_better(self, value, status):
        assert self.tile("imp_con_plan", value).status == status

    def test_lower_is_better_and_undefined(self):
        assert self.tile("mov_tickets", 3).status == "none"  # no default threshold
        assert self.tile("mov_tickets", 3, verde=D(5), amarillo=D(10)).status == "good"
        assert self.tile("mov_tickets", 8, verde=D(5), amarillo=D(10)).status == "warning"
        assert self.tile("mov_tickets", 12, verde=D(5), amarillo=D(10)).status == "critical"
        assert self.tile("imp_no_anticipados", 4).status == "none"  # informative


class TestPages:
    @pytest.mark.parametrize("role", [Role.CAPITAN, Role.EQUIPO_TECNICO, Role.LIDER_AREA])
    def test_roles_without_dashboard(self, client, member, acme, role):
        user, _ = member(role, client=acme, email="x@x.com")
        client.force_login(user)
        assert client.get(URL).status_code == 403

    def test_sponsor_sees_dashboard_without_loading_data(self, client, member, acme, make_impacto):
        make_impacto(complete=True, magnitud=4, probabilidad=4, severidad=4)
        user, _ = member(Role.PATROCINADOR, client=acme, email="pmo@x.com")
        client.force_login(user)
        body = client.get(URL).content.decode()
        assert "Alertas" in body and "IMP-001" in body and "Mensajes a tiempo" in body
        assert "Cargar datos externos" not in body
        assert client.get(f"{URL}datos/").status_code == 403

    def test_filters_and_charts_data(self, client, equipo, acme):
        with tenant_context(acme):
            g = GrupoImpactado.objects.create(name="Norte")
        client.force_login(equipo)
        body = client.get(
            f"{URL}?grupo={g.pk}&tiempo={item('tiempo', 'cumbre').pk}"
        ).content.decode()
        assert 'id="data-readiness"' in body and 'id="data-tickets"' in body

    def test_manual_values(self, client, equipo, acme):
        client.force_login(equipo)
        client.post(
            f"{URL}datos/",
            {
                "key": "tr_usuarios_activos",
                "fecha": "2026-10-01",
                "valor": "72",
                "nota": "Informe TI",
            },
        )
        client.post(
            f"{URL}datos/", {"key": "tr_usuarios_activos", "fecha": "2026-10-08", "valor": "85"}
        )
        with tenant_context(acme):
            assert ind.manual(ctx(acme), "tr_usuarios_activos").value == D(85)
            assert ValorManual.objects.count() == 2
        body = client.get(URL).content.decode()
        assert "85 %" in body and "dato del 08/10/2026" in body

    def test_admin_configures_thresholds_and_hides_indicators(self, client, member, acme):
        admin, _ = member(Role.ADMINISTRACION, client=acme, email="adm@x.com")
        client.force_login(admin)
        assert client.get(f"{URL}indicadores/").status_code == 200
        client.post(
            f"{URL}indicadores/com_a_tiempo/",
            {
                "com_a_tiempo-verde": "95",
                "com_a_tiempo-amarillo": "85",
                "com_a_tiempo-responsable": "Comunicaciones",
                "com_a_tiempo-frecuencia": "Semanal",
                "com_a_tiempo-activo": "on",
            },
        )
        client.post(
            f"{URL}indicadores/tr_diagnostico/",
            {"tr_diagnostico-responsable": "", "tr_diagnostico-frecuencia": ""},
        )
        with tenant_context(acme):
            cfg = IndicadorConfig.objects.get(key="com_a_tiempo")
            assert (cfg.verde, cfg.amarillo, cfg.responsable) == (D(95), D(85), "Comunicaciones")
            assert not IndicadorConfig.objects.get(key="tr_diagnostico").activo
        body = client.get(URL).content.decode()
        assert "Comunicaciones" in body and 'id="tr_diagnostico"' not in body

    def test_inverted_thresholds_rejected(self, client, member, acme):
        admin, _ = member(Role.ADMINISTRACION, client=acme, email="adm@x.com")
        client.force_login(admin)
        r = client.post(
            f"{URL}indicadores/com_a_tiempo/",
            {
                "com_a_tiempo-verde": "60",
                "com_a_tiempo-amarillo": "80",
                "com_a_tiempo-activo": "on",
            },
            follow=True,
        )
        assert "entre el umbral rojo y el verde" in r.content.decode()

    def test_only_administracion_configures(self, client, equipo):
        client.force_login(equipo)
        assert client.get(f"{URL}indicadores/").status_code == 403

    def test_readiness_alert(self, client, equipo, acme, make_impacto):
        with tenant_context(acme):
            g = GrupoImpactado.objects.create(name="Rezagado")
        make_impacto(grupo=g, estado=Estado.EN_ATENCION)  # 0 % attended -> index 0
        client.force_login(equipo)
        body = client.get(URL).content.decode()
        assert "Grupos bajo el umbral de preparación" in body and "Rezagado" in body


class TestDashboardEditing:
    """§2 confirmed: Administración edits the Dashboard (indicator settings)."""

    @pytest.mark.parametrize(
        ("role", "status"), [(Role.ADMINISTRACION, 200), (Role.EQUIPO_CAMBIO, 403)]
    )
    def test_who_configures_indicators(self, client, member, acme, role, status):
        user, _ = member(role, client=acme, email="x@example.com")
        client.force_login(user)
        assert client.get(f"{URL}indicadores/").status_code == status
        link = "Configurar indicadores" in client.get(URL).content.decode()
        assert link == (status == 200)
