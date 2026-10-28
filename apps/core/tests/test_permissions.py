"""Restates Parte B §2 independently of ROLE_PERMISSIONS."""

import pytest

from apps.core.models import Module, Role
from apps.core.permissions import Action, can, role_actions

A = Action
M = Module

# (role, module): (must have, must not have). Cells marked "no" in §2 are in NO_ACCESS.
CELLS = {
    (Role.ADMINISTRACION, M.MATRIZ): ({A.EDIT, A.VIEW, A.LINK}, set()),
    (Role.ADMINISTRACION, M.RUTA): ({A.EDIT, A.VIEW}, set()),
    (Role.ADMINISTRACION, M.BITACORA): ({A.EDIT, A.VIEW}, set()),
    (Role.ADMINISTRACION, M.DASHBOARD): ({A.EDIT, A.VIEW}, set()),
    (Role.ADMINISTRACION, M.FORMULARIOS): ({A.EDIT, A.DESIGN}, {A.VIEW_INDIVIDUAL}),
    (Role.ADMINISTRACION, M.APRENDIZAJE): ({A.EDIT, A.DESIGN}, {A.VIEW_INDIVIDUAL}),
    (Role.ADMINISTRACION, M.GUIA): ({A.EDIT}, set()),
    (Role.EQUIPO_CAMBIO, M.MATRIZ): ({A.EDIT, A.LINK}, set()),
    (Role.EQUIPO_CAMBIO, M.RUTA): ({A.EDIT}, set()),
    (Role.EQUIPO_CAMBIO, M.BITACORA): ({A.EDIT}, set()),
    (Role.EQUIPO_CAMBIO, M.DASHBOARD): ({A.VIEW}, {A.EDIT}),
    (Role.EQUIPO_CAMBIO, M.FORMULARIOS): ({A.EDIT, A.VIEW_INDIVIDUAL}, set()),
    (Role.EQUIPO_CAMBIO, M.APRENDIZAJE): ({A.EDIT, A.DESIGN, A.VIEW_INDIVIDUAL}, set()),
    (Role.EQUIPO_CAMBIO, M.GUIA): ({A.VIEW}, {A.EDIT}),
    (Role.CAPITAN, M.MATRIZ): ({A.PROPOSE}, {A.VIEW, A.EDIT}),
    (Role.CAPITAN, M.RUTA): ({A.VIEW_OWN_GROUP}, {A.VIEW, A.EDIT}),
    (Role.CAPITAN, M.BITACORA): ({A.REGISTER}, {A.CLASSIFY, A.EDIT}),
    (Role.CAPITAN, M.GUIA): ({A.VIEW}, {A.EDIT}),
    (Role.GUIA, M.MATRIZ): ({A.PROPOSE}, {A.VIEW, A.EDIT}),
    (Role.GUIA, M.RUTA): ({A.VIEW}, {A.EDIT}),
    (Role.GUIA, M.BITACORA): ({A.REGISTER, A.CLASSIFY}, {A.EDIT, A.EDIT_DERIVED}),
    (Role.GUIA, M.DASHBOARD): ({A.VIEW}, {A.EDIT}),
    (Role.GUIA, M.FORMULARIOS): ({A.DESIGN}, {A.EDIT, A.VIEW_INDIVIDUAL}),
    (Role.GUIA, M.APRENDIZAJE): ({A.DESIGN}, {A.EDIT, A.VIEW_INDIVIDUAL}),
    (Role.GUIA, M.GUIA): ({A.VIEW}, {A.EDIT}),
    (Role.EQUIPO_TECNICO, M.MATRIZ): ({A.PROPOSE}, {A.VIEW, A.EDIT}),
    (Role.EQUIPO_TECNICO, M.BITACORA): ({A.VIEW, A.EDIT_DERIVED}, {A.EDIT, A.CLASSIFY}),
    (Role.EQUIPO_TECNICO, M.GUIA): ({A.VIEW}, {A.EDIT}),
    (Role.PATROCINADOR, M.MATRIZ): ({A.VIEW}, {A.EDIT, A.PROPOSE}),
    (Role.PATROCINADOR, M.RUTA): ({A.VIEW}, {A.EDIT}),
    (Role.PATROCINADOR, M.DASHBOARD): ({A.VIEW}, {A.EDIT}),
    (Role.PATROCINADOR, M.GUIA): ({A.VIEW}, {A.EDIT}),
    (Role.LIDER_AREA, M.FORMULARIOS): ({A.LEADER_EVAL}, {A.VIEW_INDIVIDUAL, A.EDIT, A.DESIGN}),
    (Role.LIDER_AREA, M.GUIA): ({A.VIEW}, {A.EDIT}),
}

NO_ACCESS = [
    (Role.CAPITAN, M.DASHBOARD),
    (Role.CAPITAN, M.FORMULARIOS),
    (Role.EQUIPO_TECNICO, M.RUTA),
    (Role.EQUIPO_TECNICO, M.DASHBOARD),
    (Role.EQUIPO_TECNICO, M.FORMULARIOS),
    (Role.PATROCINADOR, M.BITACORA),
    (Role.PATROCINADOR, M.FORMULARIOS),
    (Role.LIDER_AREA, M.MATRIZ),
    (Role.LIDER_AREA, M.RUTA),
    (Role.LIDER_AREA, M.BITACORA),
    (Role.LIDER_AREA, M.DASHBOARD),
    (Role.CAPITAN, M.APRENDIZAJE),
    (Role.EQUIPO_TECNICO, M.APRENDIZAJE),
    (Role.PATROCINADOR, M.APRENDIZAJE),
    (Role.LIDER_AREA, M.APRENDIZAJE),
]


def test_every_cell_of_the_table_is_covered():
    covered = set(CELLS) | set(NO_ACCESS)
    assert covered == {(r, m) for r in Role for m in Module}


@pytest.mark.parametrize(("role", "module"), CELLS, ids=lambda v: str(v))
def test_role_cell(role, module):
    must, must_not = CELLS[(role, module)]
    actions = role_actions(role, module)
    assert must <= actions
    assert not (must_not & actions)


@pytest.mark.parametrize(("role", "module"), NO_ACCESS, ids=lambda v: str(v))
def test_no_access_cell(role, module):
    assert role_actions(role, module) == frozenset()


def test_only_change_team_and_administracion_manage_dependencies():
    holders = {r for r in Role if A.LINK in role_actions(r, M.MATRIZ)}
    assert holders == {Role.ADMINISTRACION, Role.EQUIPO_CAMBIO}


@pytest.mark.parametrize("module", [M.FORMULARIOS, M.APRENDIZAJE])
def test_only_change_team_sees_individual_results(module):
    holders = {r for r in Role if A.VIEW_INDIVIDUAL in role_actions(r, module)}
    assert holders == {Role.EQUIPO_CAMBIO}


@pytest.mark.django_db
def test_can_requires_active_membership_and_enabled_module(member):
    user, client = member(Role.EQUIPO_CAMBIO)
    assert can(user, client, M.MATRIZ, A.EDIT)

    client.enabled_modules = [M.RUTA]
    client.save()
    assert not can(user, client, M.MATRIZ, A.EDIT)
    assert can(user, client, M.RUTA, A.EDIT)

    user.memberships.update(is_active=False)
    assert not can(user, client, M.RUTA, A.EDIT)


@pytest.mark.django_db
def test_platform_admin_gets_no_client_data_access(platform_admin, make_client):
    assert not can(platform_admin, make_client(), M.MATRIZ, A.VIEW)
