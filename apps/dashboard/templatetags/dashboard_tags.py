from django import template
from django.utils.html import format_html
from django.utils.translation import gettext as _

register = template.Library()

STATUS = {
    "good": ("✓", "En meta"),
    "warning": ("▲", "Atención"),
    "critical": ("✕", "Bajo meta"),
    "none": ("–", "Sin umbral"),
}


@register.simple_tag
def alert_chip(count):
    """Alerts are not indicators: no traffic-light vocabulary, just whether there are any."""
    status, label = ("critical", "Alerta") if count else ("good", "Sin alertas")
    return status_chip(status, label)


@register.simple_tag
def status_chip(status, label=None):
    icon, default = STATUS[status]
    label = label or default
    return format_html('<span class="status status-{}"><span class="status-icon" '
                       'aria-hidden="true">{}</span>{}</span>', status, icon, _(label))


@register.simple_tag
def tile_value(tile):
    v = tile.result.value
    if v is None:
        return "—"
    unit = tile.indicator.unit
    text = f"{v:.0f}" if v == v.to_integral() else f"{v:.1f}"
    return f"{text} %" if unit == "%" else text


@register.filter
def get_item(mapping, key):
    return mapping.get(key, "")
