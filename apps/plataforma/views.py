from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import invitations
from apps.core.decorators import platform_admin_required
from apps.core.models import Client, Invitation, Membership, Role

from .forms import ClientForm, InviteForm, MembershipRoleForm


@platform_admin_required
def client_list(request):
    clients = Client.objects.annotate(
        member_count=Count("memberships", filter=Q(memberships__is_active=True)),
    )
    return render(request, "plataforma/client_list.html", {"clients": clients})


@platform_admin_required
def client_create(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save(commit=False)
        client.created_by = request.user
        client.save()
        messages.success(request, _("Cliente creado. Ahora invita a su equipo."))
        return redirect("plataforma:client_detail", slug=client.slug)
    return render(request, "plataforma/client_form.html", {"form": form})


@platform_admin_required
def client_detail(request, slug):
    client = get_object_or_404(Client, slug=slug)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Cambios guardados."))
        return redirect("plataforma:client_detail", slug=client.slug)
    return render(request, "plataforma/client_detail.html", {
        "client": client,
        "form": form,
        "invite_form": InviteForm(client=client),
        **_members_context(client),
    })


def _members_context(client):
    return {
        "memberships": client.memberships.select_related("user").order_by(
            "-is_active", "user__email"
        ),
        "pending_invitations": client.invitations.pending(),
        "roles": Role.choices,
    }


@platform_admin_required
@require_POST
def invite(request, slug):
    client = get_object_or_404(Client, slug=slug, is_active=True)
    form = InviteForm(request.POST, client=client)
    if form.is_valid():
        invitation = invitations.invite(
            request=request, client=client,
            email=form.cleaned_data["email"], role=form.cleaned_data["role"],
        )
        messages.success(request,
                         _("Invitación enviada a %(email)s.") % {"email": invitation.email})
        return redirect("plataforma:client_detail", slug=client.slug)
    return render(request, "plataforma/client_detail.html", {
        "client": client,
        "form": ClientForm(instance=client),
        "invite_form": form,
        **_members_context(client),
    }, status=400)


@platform_admin_required
@require_POST
def revoke_invitation(request, slug, pk):
    invitation = get_object_or_404(Invitation.objects.pending(), client__slug=slug, pk=pk)
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])
    messages.success(request, _("Invitación anulada."))
    return redirect("plataforma:client_detail", slug=slug)


@platform_admin_required
@require_POST
def membership_update(request, slug, pk):
    membership = get_object_or_404(Membership, client__slug=slug, pk=pk)
    if "is_active" in request.POST:
        membership.is_active = request.POST["is_active"] == "1"
        membership.save(update_fields=["is_active"])
    else:
        form = MembershipRoleForm(request.POST, instance=membership)
        if form.is_valid():
            form.save()
    messages.success(request, _("Membresía actualizada."))
    return redirect("plataforma:client_detail", slug=slug)
