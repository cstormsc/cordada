from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import Invitation, Membership, User


def invite(*, request, client, email, role, cargo=None, departamento=None):
    """Creates an invitation and emails the link. Replaces any pending one for that email."""
    with transaction.atomic():
        Invitation.objects.pending().filter(client=client, email__iexact=email).update(
            revoked_at=timezone.now()
        )
        invitation, token = Invitation.create(
            client=client,
            email=email,
            role=role,
            invited_by=request.user,
            cargo=cargo,
            departamento=departamento,
        )
    link = request.build_absolute_uri(reverse("accept_invitation", args=[token]))
    context = {"invitation": invitation, "link": link}
    send_mail(
        subject=f"Invitación a Cordada · {client.name}",
        message=render_to_string("core/email/invitation.txt", context),
        from_email=None,
        recipient_list=[invitation.email],
    )
    return invitation


@transaction.atomic
def accept(invitation, user, *, cargo=None, departamento=None):
    """cargo and departamento are what the invitee confirmed (pre-filled from the invitation)."""
    membership, _ = Membership.objects.update_or_create(
        user=user,
        client=invitation.client,
        defaults={
            "role": invitation.role,
            "is_active": True,
            "cargo": cargo,
            "departamento": departamento,
        },
    )
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    return membership


def existing_user(invitation):
    return User.objects.filter(email__iexact=invitation.email).first()
