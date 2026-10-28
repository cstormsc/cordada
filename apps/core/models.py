import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El correo es obligatorio")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)

    def members_of(self, client):
        """Active members of a client, with their job title there as `cargo_nombre`."""
        cargo = Membership.objects.filter(user=OuterRef("pk"), client=client).values("cargo__name")[
            :1
        ]
        return (
            self.filter(memberships__client=client, memberships__is_active=True)
            .annotate(cargo_nombre=Subquery(cargo))
            .order_by("first_name", "last_name", "email")
        )


class User(AbstractUser):
    """Accounts are created by invitation and log in with their email."""

    username = None
    email = models.EmailField(_("correo"), unique=True)
    is_platform_admin = models.BooleanField(
        _("administrador de plataforma"),
        default=False,
        help_text=_(
            "Puede crear y configurar clientes e invitar usuarios. "
            "No da acceso a los datos de los clientes."
        ),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")

    def __str__(self):
        return self.email

    @property
    def display_name(self):
        return self.get_full_name() or self.email

    def active_memberships(self):
        return (
            self.memberships.filter(is_active=True, client__is_active=True)
            .select_related("client")
            .order_by("client__name")
        )


class Module(models.TextChoices):
    MATRIZ = "matriz", _("Matriz de Impactos")
    RUTA = "ruta", _("Ruta")
    BITACORA = "bitacora", _("Bitácora")
    FORMULARIOS = "formularios", _("Formularios")
    APRENDIZAJE = "aprendizaje", _("Ascenso y Aprendizaje")
    DASHBOARD = "dashboard", _("Dashboard")
    GUIA = "guia", _("Guía de campo")


def all_modules():
    return list(Module.values)


def default_retention_years():
    return settings.DATA_RETENTION_YEARS


class Client(models.Model):
    name = models.CharField(_("nombre"), max_length=200)
    slug = models.SlugField(
        _("identificador"),
        max_length=60,
        unique=True,
        help_text=_("Se usa en la dirección web del espacio: /c/<identificador>/"),
    )
    is_active = models.BooleanField(_("activo"), default=True)
    enabled_modules = ArrayField(
        models.CharField(max_length=20, choices=Module.choices),
        verbose_name=_("módulos activos"),
        default=all_modules,
        blank=True,
    )
    tamano_minimo_grupo = models.PositiveSmallIntegerField(
        _("tamaño mínimo de grupo"),
        default=5,
        help_text=_(
            "En las vistas agregadas, los grupos con menos respuestas que este número "
            "no muestran resultados, para que nadie pueda ser identificado."
        ),
    )
    retencion_anos = models.PositiveSmallIntegerField(
        _("conservación de datos (años)"),
        default=default_retention_years,
        help_text=_(
            "Cuántos años se conservan los datos del cliente. Por defecto, el valor de "
            "la plataforma; la política de privacidad aún está por definir."
        ),
    )
    created_at = models.DateTimeField(_("creado"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("cliente")
        verbose_name_plural = _("clientes")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def has_module(self, module):
        return module in self.enabled_modules


class Role(models.TextChoices):
    ADMINISTRACION = "administracion", _("Administración (consultora)")
    EQUIPO_CAMBIO = "equipo_cambio", _("Equipo de cambio")
    CAPITAN = "capitan", _("Capitán")
    GUIA = "guia", _("Guía")
    EQUIPO_TECNICO = "equipo_tecnico", _("Equipo técnico")
    PATROCINADOR = "patrocinador", _("Patrocinador y PMO")
    LIDER_AREA = "lider_area", _("Líder de área")


class Membership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(_("rol"), max_length=30, choices=Role.choices)
    is_active = models.BooleanField(_("activa"), default=True)
    created_at = models.DateTimeField(_("creada"), auto_now_add=True)
    grupos = models.ManyToManyField(
        "catalogs.GrupoImpactado",
        blank=True,
        related_name="miembros",
        verbose_name=_("grupos"),
        help_text=_(
            "Grupos impactados que acompaña. Un capitán solo ve las actividades de sus grupos."
        ),
    )

    cargo = models.ForeignKey(
        "catalogs.Cargo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("cargo"),
    )
    departamento = models.ForeignKey(
        "catalogs.UnidadOrganizacional",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("departamento"),
        limit_choices_to={"kind": "departamento"},
    )

    history = HistoricalRecords(m2m_fields=[grupos])

    class Meta:
        verbose_name = _("membresía")
        verbose_name_plural = _("membresías")
        constraints = [
            models.UniqueConstraint(fields=["user", "client"], name="unique_membership"),
        ]

    def __str__(self):
        return f"{self.user} · {self.client} · {self.get_role_display()}"

    @property
    def puesto(self):
        """«Cargo · Departamento», with whichever is set."""
        return " · ".join(str(x) for x in (self.cargo, self.departamento) if x)


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


class InvitationQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(
            accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()
        )

    def get_by_token(self, token):
        return self.get(token_hash=_hash_token(token))


class Invitation(models.Model):
    VALID_DAYS = 7

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(_("correo"))
    role = models.CharField(_("rol"), max_length=30, choices=Role.choices)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Suggested by whoever invites; the invitee confirms or corrects them on accepting.
    cargo = models.ForeignKey(
        "catalogs.Cargo", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    departamento = models.ForeignKey(
        "catalogs.UnidadOrganizacional",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = InvitationQuerySet.as_manager()

    class Meta:
        verbose_name = _("invitación")
        verbose_name_plural = _("invitaciones")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} → {self.client}"

    @classmethod
    def create(cls, *, client, email, role, invited_by, cargo=None, departamento=None):
        """Returns (invitation, raw_token). Only the token's hash is stored."""
        token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            client=client,
            email=email.strip().lower(),
            role=role,
            cargo=cargo,
            departamento=departamento,
            token_hash=_hash_token(token),
            invited_by=invited_by,
            expires_at=timezone.now() + timedelta(days=cls.VALID_DAYS),
        )
        return invitation, token

    @property
    def is_pending(self):
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )
