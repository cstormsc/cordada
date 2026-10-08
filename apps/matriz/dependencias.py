"""Impact dependencies: 'A depende de B'. They only warn; they never block a state change."""

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils.translation import gettext as _

from .models import OPEN_STATES, Dependencia, Estado, Impacto

WARN_ON = (Estado.ATENDIDO, Estado.CERRADO)


def open_prerequisites(impacto):
    """Impacts this one depends on that are still open."""
    return Impacto.objects.filter(dependientes__impacto=impacto, estado__in=OPEN_STATES)


def with_blocked(queryset):
    """Annotates n_bloqueos: open prerequisites per impact."""
    return queryset.annotate(
        n_bloqueos=Count(
            "dependencias",
            filter=Q(dependencias__depende_de__estado__in=OPEN_STATES),
            distinct=True,
        )
    )


def _reachable_from(start):
    """Every impact that `start` depends on, directly or not."""
    seen, frontier = set(), {start.pk}
    while frontier:
        frontier = (
            set(
                Dependencia.objects.filter(impacto_id__in=frontier).values_list(
                    "depende_de_id", flat=True
                )
            )
            - seen
        )
        seen |= frontier
    return seen


def add(impacto, depende_de, *, user):
    if impacto.pk == depende_de.pk:
        raise ValidationError(_("Un impacto no puede depender de sí mismo."))
    if Dependencia.objects.filter(impacto=impacto, depende_de=depende_de).exists():
        raise ValidationError(
            _("%(a)s ya depende de %(b)s.") % {"a": impacto.codigo, "b": depende_de.codigo}
        )
    if impacto.pk in _reachable_from(depende_de):
        raise ValidationError(
            _(
                "No se puede: %(b)s ya depende (directa o indirectamente) de "
                "%(a)s, y se formaría un ciclo."
            )
            % {"a": impacto.codigo, "b": depende_de.codigo}
        )
    return Dependencia.objects.create(impacto=impacto, depende_de=depende_de, creada_por=user)


def transition_warning(impacto):
    """Warning to show after a state change, or None."""
    if impacto.estado not in WARN_ON:
        return None
    pending = list(open_prerequisites(impacto).order_by("numero"))
    if not pending:
        return None
    return _("Atención: %(codigo)s depende de impactos aún abiertos: %(lista)s.") % {
        "codigo": impacto.codigo,
        "lista": ", ".join(f"{p.codigo} ({p.get_estado_display()})" for p in pending),
    }
