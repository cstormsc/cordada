"""The people list is the client's reporting line: each person's `supervisor` is the
email of their leader, and an área leader's team is whoever names them (§7.5).
This checks that those emails belong to someone who can actually evaluate."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.models import Invitation, Membership, Role

OK = "ok"
INVITADO = "invitado"
OTRO_ROL = "otro_rol"
SIN_CUENTA = "sin_cuenta"
NO_ES_CORREO = "no_es_correo"

PROBLEMAS = {
    INVITADO: _("Invitado como líder de área; aún no acepta la invitación."),
    OTRO_ROL: _("Tiene cuenta, pero no con el rol Líder de área: no verá a su equipo."),
    SIN_CUENTA: _("No tiene cuenta de Líder de área: invítalo desde la administración."),
    NO_ES_CORREO: _("No es un correo: la columna supervisor debe tener el correo del líder."),
}


@dataclass
class Supervisor:
    email: str
    personas: int
    estado: str

    @property
    def problema(self):
        return PROBLEMAS.get(self.estado, "")


def check(client, counts):
    """counts: {supervisor email: people reporting to them}. Returns the problems
    first, then the ones that are fine, each group by team size."""
    emails = {e.lower() for e in counts}
    members = {
        m["email"]: m["role"]
        for m in Membership.objects.filter(client=client, is_active=True)
        .annotate(email=Lower("user__email"))
        .filter(email__in=emails)
        .values("email", "role")
    }
    invited = set(
        Invitation.objects.pending()
        .filter(client=client, role=Role.LIDER_AREA)
        .annotate(e=Lower("email"))
        .filter(e__in=emails)
        .values_list("e", flat=True)
    )
    result = []
    for email, n in counts.items():
        key = email.lower()
        try:
            validate_email(key)
        except ValidationError:
            estado = NO_ES_CORREO
        else:
            if members.get(key) == Role.LIDER_AREA:
                estado = OK
            elif key in invited:
                estado = INVITADO
            elif key in members:
                estado = OTRO_ROL
            else:
                estado = SIN_CUENTA
        result.append(Supervisor(email=email, personas=n, estado=estado))
    return sorted(result, key=lambda s: (s.estado == OK, -s.personas, s.email))


def from_records(client, records):
    counts = {}
    for r in records:
        email = (r.get("supervisor") or "").strip().lower()
        if email:
            counts[email] = counts.get(email, 0) + 1
    return check(client, counts)


def from_people(client, personas):
    rows = (
        personas.filter(is_active=True)
        .exclude(supervisor="")
        .annotate(s=Lower("supervisor"))
        .values("s")
        .annotate(n=Count("id"))
    )
    return check(client, {r["s"].strip(): r["n"] for r in rows})
