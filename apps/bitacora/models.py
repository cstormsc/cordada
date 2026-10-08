from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.catalogs.models import GrupoImpactado, SystemCatalog, SystemCatalogField
from apps.core.tenancy import TenantScopedModel, assign_next_number
from apps.matriz.models import Impacto

TECNICO = "tecnico"
IMPACTO_NO_ANTICIPADO = "impacto_no_anticipado"


class EstadoTicket(models.TextChoices):
    NUEVO = "nuevo", _("Nuevo")
    EN_CLASIFICACION = "en_clasificacion", _("En clasificación")
    VALIDADO = "validado", _("Validado")
    DERIVADO_TI = "derivado_ti", _("Derivado a TI")
    RESUELTO = "resuelto", _("Resuelto")
    CERRADO = "cerrado", _("Cerrado")


OPEN_TICKET_STATES = (EstadoTicket.NUEVO, EstadoTicket.EN_CLASIFICACION, EstadoTicket.VALIDADO,
                      EstadoTicket.DERIVADO_TI)


class Urgencia(models.TextChoices):
    NORMAL = "normal", _("Normal")
    GRAVE = "grave", _("Fallo grave")


class Ticket(TenantScopedModel):
    numero = models.PositiveIntegerField(_("ID"), editable=False)
    estado = models.CharField(_("estado"), max_length=20, choices=EstadoTicket.choices,
                              default=EstadoTicket.NUEVO, editable=False)
    titulo = models.CharField(_("asunto"), max_length=200,
                              help_text=_("En una frase: qué pasa."))
    descripcion = models.TextField(
        _("descripción"),
        help_text=_("Qué intentaba hacer la persona, qué pasó y desde cuándo."),
    )
    categoria = SystemCatalogField(
        SystemCatalog.CATEGORIA_TICKET, verbose_name=_("categoría"),
        help_text=_("Técnico solo si falla el sistema. Si la persona no sabe cómo hacerlo, "
                    "es conocimiento."),
    )
    urgencia = models.CharField(
        _("urgencia"), max_length=10, choices=Urgencia.choices, default=Urgencia.NORMAL,
        help_text=_("Fallo grave: impide trabajar. Un fallo grave técnico se deriva a TI de "
                    "inmediato y se valida en paralelo."),
    )
    grupo = models.ForeignKey(GrupoImpactado, on_delete=models.PROTECT, null=True, blank=True,
                              related_name="tickets", verbose_name=_("grupo impactado"))
    impacto = models.ForeignKey(Impacto, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="tickets", verbose_name=_("impacto vinculado"))
    caso_cliente = models.CharField(
        _("número de caso en el sistema del cliente"), max_length=60, blank=True,
        help_text=_("Los casos técnicos se registran también en la mesa de ayuda del cliente."),
    )
    recurrente_de = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="recurrencias",
        verbose_name=_("repite el caso"),
        help_text=_("Si es el mismo problema que un ticket anterior."),
    )
    validado = models.BooleanField(_("clasificación validada"), default=False, editable=False)
    validado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                     null=True, related_name="+", editable=False)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name="+", editable=False)
    created_at = models.DateTimeField(_("registrado"), auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    primera_respuesta_at = models.DateTimeField(_("primera respuesta"), null=True,
                                                editable=False)
    resuelto_at = models.DateTimeField(_("resolución"), null=True, editable=False)
    cerrado_at = models.DateTimeField(_("cierre"), null=True, editable=False)

    history = HistoricalRecords(excluded_fields=["updated_at"])

    class Meta(TenantScopedModel.Meta):
        verbose_name = _("ticket")
        verbose_name_plural = _("tickets")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["client", "numero"], name="unique_ticket_numero"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        return f"TCK-{self.numero:03d}" if self.numero else "TCK-nuevo"

    @property
    def es_tecnico(self):
        return bool(self.categoria_id) and self.categoria.code == TECNICO

    @property
    def es_impacto_no_anticipado(self):
        return bool(self.categoria_id) and self.categoria.code == IMPACTO_NO_ANTICIPADO

    @property
    def is_open(self):
        return self.estado in OPEN_TICKET_STATES

    def save(self, *args, **kwargs):
        with transaction.atomic():
            assign_next_number(self)
            super().save(*args, **kwargs)


class TicketTransicion(TenantScopedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="transiciones")
    desde = models.CharField(max_length=20, choices=EstadoTicket.choices)
    hacia = models.CharField(max_length=20, choices=EstadoTicket.choices)
    motivo = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["fecha"]


class TicketComentario(TenantScopedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="+")
    texto = models.TextField(_("comentario"))
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["fecha"]
