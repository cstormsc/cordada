"""Exact tables from Parte B §3.4."""

import pytest

from .rules import (
    Priority,
    RiskBand,
    is_severity_alert,
    priority,
    risk_band,
    risk_level,
    risk_score,
)

B, M, A, C = RiskBand.BAJO, RiskBand.MEDIO, RiskBand.ALTO, RiskBand.CRITICO

# Rows: probability 1..4 · columns: severity 1..4
RISK_TABLE = [
    [B, B, B, M],
    [B, M, M, A],
    [B, M, A, C],
    [M, A, C, C],
]


@pytest.mark.parametrize("probability", range(1, 5))
@pytest.mark.parametrize("severity", range(1, 5))
def test_risk_level_table(probability, severity):
    assert risk_level(probability, severity) == RISK_TABLE[probability - 1][severity - 1]


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (1, B),
        (2, B),
        (3, B),
        (4, M),
        (6, M),
        (8, A),
        (9, A),
        (12, C),
        (16, C),
    ],
)
def test_band_limits(score, band):
    assert risk_band(score) == band


@pytest.mark.parametrize("score", [0, 5, 7, 10, 11, 13, 17])
def test_impossible_scores_are_rejected(score):
    with pytest.raises(ValueError):
        risk_band(score)


@pytest.mark.parametrize(("p", "s"), [(0, 1), (1, 5), (None, 2)])
def test_out_of_scale_values_are_rejected(p, s):
    with pytest.raises(ValueError):
        risk_score(p, s)


def test_extreme_severity_alerts_regardless_of_band():
    assert is_severity_alert(4)
    assert not is_severity_alert(3)
    # Improbable × Extrema is only Medio, but still alerts.
    assert risk_level(1, 4) == M


# §3.4 priority table. Rows: risk band · columns: magnitude Leve..Profundo
P1, P2, P3, P4 = Priority
PRIORITY_TABLE = {
    C: [P2, P2, P1, P1],
    A: [P3, P2, P2, P1],
    M: [P4, P3, P2, P2],
    B: [P4, P4, P3, P2],
}


@pytest.mark.parametrize("band", list(RiskBand))
@pytest.mark.parametrize("magnitude", range(1, 5))
def test_priority_table(band, magnitude):
    assert priority(magnitude, band) == PRIORITY_TABLE[band][magnitude - 1]


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (2, P4),
        (3, P4),
        (4, P3),
        (5, P2),
        (6, P2),
        (7, P1),
        (8, P1),
    ],
)
def test_priority_sums(total, expected):
    magnitude = min(4, total - 1)
    band = RiskBand(total - magnitude)
    assert priority(magnitude, band) == expected


def test_labels():
    assert C.label == "Crítico"
    assert P1.label == "P1 Inmediata"
