import itertools
import re

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from apps.core.models import Module
from apps.core.tenancy import get_current_client

from .. import anchors, glosario

register = template.Library()


@register.simple_tag
def guia_url(bound_field):
    """Link to the guide section for a form field that declares one, or ""."""
    anchor = getattr(bound_field.field, "guia", None)
    client = get_current_client()
    if not anchor or client is None or not client.has_module(Module.GUIA):
        return ""
    return f"{reverse('guia:index', args=[client.slug])}#{anchor}"


_ids = itertools.count(1)


def _guia_link(anchor):
    client = get_current_client()
    if client is None or not client.has_module(Module.GUIA):
        return ""
    return f"{reverse('guia:index', args=[client.slug])}#{anchor}"


def _bubble(term, text, href):
    """A "?" button with its definition (shown by static/js/ayuda.js on hover, focus or tap)."""
    tip = f"ayuda-{next(_ids)}"
    more = (
        format_html(
            ' <a href="{}" target="_blank" rel="noopener">{}</a>', href, _("Más en la guía")
        )
        if href
        else ""
    )
    return format_html(
        '<span class="ayuda"><button type="button" class="ayuda-btn" aria-label="{}" '
        'aria-describedby="{}">?</button><span class="ayuda-tip" role="tooltip" id="{}" hidden>'
        "<strong>{}</strong> {}{}</span></span>",
        _("¿Qué significa «%(term)s»?") % {"term": term},
        tip,
        tip,
        term,
        text,
        more,
    )


@register.simple_tag
def ayuda(key):
    """Short reminder of what a platform term means: {% ayuda "descubierto" %}."""
    if key not in glosario.TERMINOS:
        return ""
    term, text = glosario.TERMINOS[key]
    return _bubble(term, text, _guia_link(glosario.anchor(key)))


@register.simple_tag
def ayuda_catalogo(item, sentences=2):
    """Reminder for a methodology catalog item (a front, a stage), from its own help text."""
    help_text = (getattr(item, "help_text", "") or "").strip()
    if not help_text:
        return ""
    parts = re.split(r"(?<=[.?!])\s+", help_text)
    text = " ".join(parts[:sentences]) + (" …" if len(parts) > sentences else "")
    return _bubble(str(item), text, _guia_link(anchors.catalogo(item.catalog)))
