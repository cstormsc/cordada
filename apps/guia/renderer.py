from django.forms.renderers import DjangoTemplates


class FormRenderer(DjangoTemplates):
    """Default renderer, with a field template that links each field to the guide."""

    field_template_name = "guia/field.html"
