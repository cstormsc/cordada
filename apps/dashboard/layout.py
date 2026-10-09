"""Dashboard modules and each person's arrangement of them: two columns (main and a
narrower side column) and the modules they hid. Unknown ids are dropped and modules added
later appear in their default place, so a saved layout never breaks the page."""

from django.utils.translation import gettext_lazy as _

MODULES = {
    "avance": _("Avance general del proyecto"),
    "alertas": _("Alertas"),
    "preparacion": _("Índice de preparación por grupo"),
    "tickets": _("Tickets por tipo"),
    "impactos": _("Impactos"),
    "comunicacion": _("Comunicación"),
    "movilizacion": _("Movilización"),
    "formacion": _("Formación"),
    "transversal": _("Transversales"),
}
DEFAULT = {
    "main": [
        "avance",
        "preparacion",
        "tickets",
        "impactos",
        "comunicacion",
        "movilizacion",
        "formacion",
        "transversal",
    ],
    "side": ["alertas"],
    "hidden": [],
}
COLUMNS = ("main", "side", "hidden")


def clean(data):
    """A valid layout from untrusted input: known ids, each once."""
    seen, out = set(), {}
    for col in COLUMNS:
        values = data.get(col, []) if isinstance(data, dict) else []
        out[col] = []
        for mod in values if isinstance(values, list) else []:
            if isinstance(mod, str) and mod in MODULES and mod not in seen:
                seen.add(mod)
                out[col].append(mod)
    return out


def resolve(saved):
    """{main, side, hidden} for the page: the saved layout, plus any module it doesn't
    mention in its default column and position."""
    layout = clean(saved or {})
    if not any(layout.values()):
        return {col: list(DEFAULT[col]) for col in COLUMNS}
    placed = {m for col in COLUMNS for m in layout[col]}
    for col in ("main", "side"):
        for i, mod in enumerate(DEFAULT[col]):
            if mod not in placed:
                layout[col].insert(min(i, len(layout[col])), mod)
    return layout
