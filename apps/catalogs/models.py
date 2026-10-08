from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.tenancy import TenantScopedModel

# --- System catalogs: the same for every client, maintained by platform admins ---


class SystemCatalog(models.TextChoices):
    TIEMPO = "tiempo", _("Tiempos del marco")
    TIPO_IMPACTO = "tipo_impacto", _("Tipos de impacto")
    ORIGEN = "origen", _("Origen de la detección")
    CATEGORIA_TICKET = "categoria_ticket", _("Categorías de ticket")
    TIPO_CAMBIO_CONOCIMIENTO = "tipo_cambio_conocimiento", _("Tipo de cambio en el conocimiento")
    EVIDENCIA_CIERRE = "evidencia_cierre", _("Tipo de evidencia de cierre")


class SystemCatalogItemQuerySet(models.QuerySet):
    def of(self, catalog):
        return self.filter(catalog=catalog)

    def active(self):
        return self.filter(is_active=True)


class SystemCatalogItem(models.Model):
    """`code` is stable and may be referenced by code; labels and help can change."""

    catalog = models.CharField(_("catálogo"), max_length=40, choices=SystemCatalog.choices)
    code = models.SlugField(_("código"), max_length=60)
    label = models.CharField(_("nombre"), max_length=120)
    help_text = models.TextField(_("ayuda"), blank=True)
    order = models.PositiveSmallIntegerField(_("orden"), default=0)
    is_active = models.BooleanField(_("activo"), default=True)

    history = HistoricalRecords()
    objects = SystemCatalogItemQuerySet.as_manager()

    class Meta:
        verbose_name = _("elemento de catálogo del sistema")
        verbose_name_plural = _("elementos de catálogos del sistema")
        ordering = ["catalog", "order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["catalog", "code"], name="unique_system_catalog_code"),
        ]

    def __str__(self):
        return self.label


class SystemCatalogField(models.ForeignKey):
    """FK to SystemCatalogItem restricted to one catalog, e.g.
    tipo = SystemCatalogField(SystemCatalog.TIPO_IMPACTO, verbose_name="tipo")
    """

    def __init__(self, catalog=None, **kwargs):
        self.catalog = catalog
        kwargs.setdefault("to", "catalogs.SystemCatalogItem")
        kwargs.setdefault("on_delete", models.PROTECT)
        kwargs.setdefault("related_name", "+")
        if catalog:
            kwargs["limit_choices_to"] = {"catalog": catalog, "is_active": True}
        super().__init__(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["catalog"] = self.catalog
        kwargs.pop("limit_choices_to", None)
        return name, path, args, kwargs

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        if value is not None and self.catalog:
            item = SystemCatalogItem.objects.filter(pk=value).values("catalog").first()
            if item and item["catalog"] != self.catalog:
                raise ValidationError(_("Valor fuera del catálogo."))


class Scale(models.Model):
    """Four-level scales (§3.3). Values 1–4 are fixed; labels and definitions are editable."""

    code = models.SlugField(_("código"), max_length=40, unique=True)
    name = models.CharField(_("nombre"), max_length=120)
    help_text = models.TextField(_("ayuda"), blank=True)
    order = models.PositiveSmallIntegerField(_("orden"), default=0)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("escala")
        verbose_name_plural = _("escalas")
        ordering = ["order"]

    def __str__(self):
        return self.name

    @property
    def is_defined(self):
        return self.levels.count() == 4

    def choices(self):
        return [(lvl.value, f"{lvl.label} ({lvl.value})") for lvl in self.levels.all()]


class ScaleLevel(models.Model):
    scale = models.ForeignKey(Scale, on_delete=models.CASCADE, related_name="levels")
    value = models.PositiveSmallIntegerField(
        _("valor"), choices=[(i, str(i)) for i in range(1, 5)]
    )
    label = models.CharField(_("nombre"), max_length=60)
    definition = models.TextField(
        _("definición"), blank=True,
        help_text=_("Se muestra al elegir este nivel."),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("nivel de escala")
        verbose_name_plural = _("niveles de escala")
        ordering = ["scale", "value"]
        constraints = [
            models.UniqueConstraint(fields=["scale", "value"], name="unique_scale_value"),
        ]

    def __str__(self):
        return f"{self.label} ({self.value})"


# --- Client catalogs: each client configures its own ---


class ClientCatalogItem(TenantScopedModel):
    name = models.CharField(_("nombre"), max_length=150)
    description = models.TextField(_("descripción"), blank=True)
    order = models.PositiveSmallIntegerField(_("orden"), default=0)
    is_active = models.BooleanField(_("activo"), default=True)

    history = HistoricalRecords(inherit=True)

    class Meta(TenantScopedModel.Meta):
        abstract = True
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(
                "client", models.functions.Lower("name"),
                name="%(app_label)s_%(class)s_unique_name",
            ),
        ]

    def __str__(self):
        return self.name


class GrupoImpactado(ClientCatalogItem):
    class Meta(ClientCatalogItem.Meta):
        verbose_name = _("grupo impactado")
        verbose_name_plural = _("grupos impactados")


class CategoriaResponsable(ClientCatalogItem):
    class Meta(ClientCatalogItem.Meta):
        verbose_name = _("categoría de responsable")
        verbose_name_plural = _("categorías de responsable")


class Cargo(ClientCatalogItem):
    class Meta(ClientCatalogItem.Meta):
        verbose_name = _("cargo")
        verbose_name_plural = _("cargos")


class UnidadOrganizacional(ClientCatalogItem):
    class Kind(models.TextChoices):
        AREA = "area", _("Área")
        OFICINA = "oficina", _("Oficina")
        SUCURSAL = "sucursal", _("Sucursal")
        DEPARTAMENTO = "departamento", _("Departamento")

    kind = models.CharField(_("tipo"), max_length=20, choices=Kind.choices)

    class Meta(ClientCatalogItem.Meta):
        verbose_name = _("unidad organizacional")
        verbose_name_plural = _("unidades organizacionales")
        ordering = ["kind", "order", "name"]
        constraints = [
            models.UniqueConstraint(
                "client", "kind", models.functions.Lower("name"),
                name="catalogs_unidadorganizacional_unique_name",
            ),
        ]
