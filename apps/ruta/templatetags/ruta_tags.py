from django import template
from django.utils.html import format_html

from apps.ruta.models import Cumplimiento

register = template.Library()


@register.simple_tag
def cumplimiento(value):
    if not value:
        return ""
    value = Cumplimiento(value)
    return format_html('<span class="cump {}">{}</span>', value.value, value.label)


@register.simple_tag
def pct(value):
    return "—" if value is None else f"{value} %"
