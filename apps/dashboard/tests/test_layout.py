import json
from decimal import Decimal as D

import pytest

from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.dashboard import indicators as ind
from apps.dashboard import layout
from apps.dashboard.models import IndicadorConfig, Preferencia

pytestmark = pytest.mark.django_db
URL = "/c/acme/dashboard/"
SAVE = f"{URL}orden/"


def tile(key, frente, value, unit="%", higher=True):
    i = ind.Indicator(key, frente, "ejecucion", key, "", "", unit=unit, higher_is_better=higher)
    return ind.Tile(i, ind.Result(None if value is None else D(value)), None, None, "", "")


class TestAvanceGeneral:
    def test_average_of_fronts_each_the_average_of_its_percentages(self):
        tiles = [
            tile("a", "impactos", 80), tile("b", "impactos", 90),  # 85
            tile("c", "comunicacion", 70),
            tile("d", "movilizacion", 40), tile("n", "movilizacion", 999, unit="n"),  # counts out
            tile("t", "movilizacion", 5, higher=False),  # lower is better: out
            tile("e", "formacion", None),  # no data: front left out
            tile("x", "transversal", 10),  # not one of the four fronts
        ]  # fmt: skip
        result, partes = ind.avance_general(tiles)
        assert [(p["code"], p["valor"], p["n"]) for p in partes] == [
            ("impactos", 85, 2), ("comunicacion", 70, 1), ("movilizacion", 40, 1),
            ("formacion", None, 0),
        ]  # fmt: skip
        assert result.value == 65 and "3 de 4" in result.detail

    def test_no_data(self):
        result, _ = ind.avance_general([tile("a", "impactos", None)])
        assert result.value is None

    def test_page_leads_with_it_and_it_can_be_turned_off(self, client, equipo, acme, member):
        admin, _ = member(Role.ADMINISTRACION, client=acme, email="adm@example.com")
        client.force_login(admin)
        body = client.get(URL).content.decode()
        main = body.split('data-col="main"')[1].split('data-col="side"')[0]
        assert main.index('data-mod="avance"') < main.index('data-mod="preparacion"')
        assert main.index('data-mod="tickets"') < main.index('data-mod="impactos"')
        assert 'data-mod="alertas"' in body.split('data-col="side"')[1]
        with tenant_context(acme):
            IndicadorConfig.objects.create(key=ind.GENERAL, activo=False)
        assert 'data-mod="avance"' not in client.get(URL).content.decode()


class TestLayoutRules:
    def test_clean_keeps_known_ids_once(self):
        dirty = {"main": ["avance", "nope", "avance", 3], "side": ["avance", "alertas"], "x": 1}
        assert layout.clean(dirty) == {"main": ["avance"], "side": ["alertas"], "hidden": []}
        assert layout.clean("not a dict") == {"main": [], "side": [], "hidden": []}

    def test_missing_modules_come_back_in_their_default_place(self):
        out = layout.resolve({"main": ["impactos"], "side": ["tickets"], "hidden": ["alertas"]})
        assert out["hidden"] == ["alertas"]
        assert out["side"] == ["tickets"]
        assert out["main"][0] == "avance" and "preparacion" in out["main"]
        assert sorted(m for col in out.values() for m in col) == sorted(layout.MODULES)

    def test_nothing_saved_is_the_default(self):
        assert layout.resolve(None) == layout.DEFAULT


class TestSaving:
    def post(self, client, data):
        return client.post(SAVE, json.dumps(data), content_type="application/json")

    def test_each_person_keeps_their_own_layout(self, client, equipo, acme, member):
        client.force_login(equipo)
        mine = {
            "main": ["tickets", "avance"],
            "side": ["alertas", "impactos"],
            "hidden": ["formacion"],
        }
        assert self.post(client, mine).json()["ok"]
        body = client.get(URL).content.decode()
        main = body.split('data-col="main"')[1].split('data-col="side"')[0]
        assert main.index('data-mod="tickets"') < main.index('data-mod="avance"')
        side = body.split('data-col="side"')[1]
        assert side.index('data-mod="alertas"') < side.index('data-mod="impactos"')
        assert 'data-mod="formacion"' not in body and 'data-show="formacion"' in body

        other, _ = member(Role.GUIA, client=acme, email="guia@example.com")
        client.force_login(other)
        body = client.get(URL).content.decode()
        assert 'data-mod="formacion"' in body  # not affected by someone else's choices
        main = body.split('data-col="main"')[1].split('data-col="side"')[0]
        assert main.index('data-mod="avance"') < main.index('data-mod="tickets"')

    def test_reset_and_bad_input(self, client, equipo, acme):
        client.force_login(equipo)
        self.post(client, {"main": ["tickets"], "hidden": ["avance"]})
        assert self.post(client, {"reset": True}).json()["layout"] == layout.DEFAULT
        with tenant_context(acme):
            assert not Preferencia.objects.exists()
        bad = client.post(SAVE, "{nope", content_type="application/json")
        assert bad.status_code == 400
        assert self.post(client, ["a list"]).status_code == 400
        assert client.get(SAVE).status_code == 405

    def test_only_dashboard_viewers(self, client, member, acme):
        captain, _ = member(Role.CAPITAN, client=acme, email="cap@example.com")
        client.force_login(captain)
        assert self.post(client, {"main": ["avance"]}).status_code == 403
