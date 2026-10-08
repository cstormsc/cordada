"""Role permissions per module, from Parte B §2.

This is the only place the role table lives. Views check it with can();
the tests restate §2 independently so a change here has to be deliberate.
"""

from enum import StrEnum

from .models import Membership, Module, Role


class Action(StrEnum):
    VIEW = "view"                      # V
    EDIT = "edit"                      # E
    PROPOSE = "propose"                # P: suggest impacts for the change team to validate
    REGISTER = "register"              # R: log tickets
    VIEW_OWN_GROUP = "view_own_group"  # Ruta, captains: only their group
    CLASSIFY = "classify"              # Bitácora: validate technical vs knowledge
    EDIT_DERIVED = "edit_derived"      # Bitácora, technical team: tickets sent to IT
    DESIGN = "design"                  # Formularios, guides: build instruments
    VIEW_INDIVIDUAL = "view_individual"  # Formularios: individual results (§7.4)
    LEADER_EVAL = "leader_eval"        # Formularios: leader's practical evaluation


A = Action
M = Module

ROLE_PERMISSIONS: dict[str, dict[str, frozenset[Action]]] = {
    Role.ADMINISTRACION: {
        M.MATRIZ: frozenset({A.EDIT}),
        M.RUTA: frozenset({A.EDIT}),
        M.BITACORA: frozenset({A.EDIT}),
        M.DASHBOARD: frozenset({A.VIEW}),
        M.FORMULARIOS: frozenset({A.EDIT}),
        M.GUIA: frozenset({A.EDIT}),
    },
    Role.EQUIPO_CAMBIO: {
        M.MATRIZ: frozenset({A.EDIT}),
        M.RUTA: frozenset({A.EDIT}),
        M.BITACORA: frozenset({A.EDIT}),
        M.DASHBOARD: frozenset({A.VIEW}),
        M.FORMULARIOS: frozenset({A.EDIT, A.VIEW_INDIVIDUAL}),
        M.GUIA: frozenset({A.VIEW}),
    },
    Role.CAPITAN: {
        M.MATRIZ: frozenset({A.PROPOSE}),
        M.RUTA: frozenset({A.VIEW_OWN_GROUP}),
        M.BITACORA: frozenset({A.REGISTER}),
        M.GUIA: frozenset({A.VIEW}),
    },
    Role.GUIA: {
        M.MATRIZ: frozenset({A.PROPOSE}),
        M.RUTA: frozenset({A.VIEW}),
        M.BITACORA: frozenset({A.REGISTER, A.CLASSIFY}),
        M.DASHBOARD: frozenset({A.VIEW}),
        M.FORMULARIOS: frozenset({A.DESIGN}),
        M.GUIA: frozenset({A.VIEW}),
    },
    Role.EQUIPO_TECNICO: {
        M.MATRIZ: frozenset({A.PROPOSE}),
        M.BITACORA: frozenset({A.VIEW, A.EDIT_DERIVED}),
        M.GUIA: frozenset({A.VIEW}),
    },
    Role.PATROCINADOR: {
        M.MATRIZ: frozenset({A.VIEW}),
        M.RUTA: frozenset({A.VIEW}),
        M.DASHBOARD: frozenset({A.VIEW}),  # aggregate only; detail is gated by VIEW_INDIVIDUAL
        M.GUIA: frozenset({A.VIEW}),
    },
    Role.LIDER_AREA: {
        M.FORMULARIOS: frozenset({A.LEADER_EVAL}),
        M.GUIA: frozenset({A.VIEW}),
    },
}

# Holding the key implies the values.
IMPLIES = {
    A.EDIT: {A.VIEW, A.PROPOSE, A.REGISTER, A.CLASSIFY, A.EDIT_DERIVED, A.DESIGN},
    A.VIEW: {A.VIEW_OWN_GROUP},
    A.CLASSIFY: {A.VIEW},
    A.EDIT_DERIVED: {A.VIEW},
}


def role_actions(role, module) -> frozenset[Action]:
    granted = set(ROLE_PERMISSIONS.get(role, {}).get(module, ()))
    pending = list(granted)
    while pending:
        for implied in IMPLIES.get(pending.pop(), ()):
            if implied not in granted:
                granted.add(implied)
                pending.append(implied)
    return frozenset(granted)


def get_membership(user, client):
    if not user.is_authenticated or not client.is_active:
        return None
    return (
        Membership.objects.filter(user=user, client=client, is_active=True)
        .only("role").first()
    )


def can(user, client, module, action, membership=None) -> bool:
    if not client.has_module(module):
        return False
    membership = membership or get_membership(user, client)
    if membership is None:
        return False
    return action in role_actions(membership.role, module)


def visible_modules(membership):
    """Modules the member can open at all, in menu order."""
    return [
        m for m in Module
        if membership.client.has_module(m) and role_actions(membership.role, m)
    ]


def can_configure(membership) -> bool:
    """Client configuration (catalogs, people, modules) belongs to Administración (§9)."""
    return membership is not None and membership.role == Role.ADMINISTRACION
