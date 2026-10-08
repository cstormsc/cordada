"""Anchors of the field guide page. Form fields carry one in `field.guia`, and
the field template links to it (contextual help, Parte B §9)."""

CALCULOS = "calculos"


def catalogo(code):
    return f"catalogo-{code}"


def escala(code):
    return f"escala-{code}"
