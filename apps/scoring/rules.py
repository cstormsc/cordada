"""Risk and priority rules from Parte B §3.4. Pure functions, no database."""

from enum import IntEnum

SCALE_VALUES = range(1, 5)  # every scale has four levels


class RiskBand(IntEnum):
    BAJO = 1
    MEDIO = 2
    ALTO = 3
    CRITICO = 4

    @property
    def label(self):
        return {1: "Bajo", 2: "Medio", 3: "Alto", 4: "Crítico"}[self]


class Priority(IntEnum):
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4

    @property
    def label(self):
        return {
            1: "P1 Inmediata",
            2: "P2 Prioritaria",
            3: "P3 Planificada",
            4: "P4 De seguimiento",
        }[self]


EXTREME_SEVERITY = 4
POSSIBLE_SCORES = frozenset(p * s for p in SCALE_VALUES for s in SCALE_VALUES)


def _check(name, value):
    if value not in SCALE_VALUES:
        raise ValueError(f"{name} debe estar entre 1 y 4, no {value!r}")


def risk_score(probability: int, severity: int) -> int:
    _check("probabilidad", probability)
    _check("severidad", severity)
    return probability * severity


def risk_band(score: int) -> RiskBand:
    if score not in POSSIBLE_SCORES:
        raise ValueError(f"{score} no es un producto posible de dos valores entre 1 y 4")
    if score <= 3:
        return RiskBand.BAJO
    if score <= 6:
        return RiskBand.MEDIO
    if score <= 9:
        return RiskBand.ALTO
    return RiskBand.CRITICO


def risk_level(probability: int, severity: int) -> RiskBand:
    return risk_band(risk_score(probability, severity))


def is_severity_alert(severity: int) -> bool:
    """Any Extrema severity raises an alert, whatever the probability."""
    _check("severidad", severity)
    return severity == EXTREME_SEVERITY


def priority(magnitude: int, band: RiskBand) -> Priority:
    _check("magnitud", magnitude)
    total = magnitude + RiskBand(band).value
    if total >= 7:
        return Priority.P1
    if total >= 5:
        return Priority.P2
    if total == 4:
        return Priority.P3
    return Priority.P4
