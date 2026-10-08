from django import template
from django.urls import reverse

from apps.core.models import Module
from apps.core.tenancy import get_current_client

register = template.Library()


@register.simple_tag
def guia_url(bound_field):
    """Link to the guide section for a form field that declares one, or ""."""
    anchor = getattr(bound_field.field, "guia", None)
    client = get_current_client()
    if not anchor or client is None or not client.has_module(Module.GUIA):
        return ""
    return f"{reverse('guia:index', args=[client.slug])}#{anchor}"
