from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import connection
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import invitations
from .decorators import client_member_required
from .forms import AcceptInvitationForm
from .models import Invitation, Module, User
from .permissions import Action, can_assign_groups, can_configure, role_actions, visible_modules


@login_required
def home(request):
    memberships = list(request.user.active_memberships())
    if len(memberships) == 1 and not request.user.is_platform_admin:
        return redirect("client_home", client_slug=memberships[0].client.slug)
    return render(request, "core/home.html", {"memberships": memberships})


@client_member_required
def client_home(request, client_slug):
    form_actions = role_actions(request.membership.role, Module.FORMULARIOS)
    return render(
        request,
        "core/client_home.html",
        {
            "modules": visible_modules(request.membership),
            "can_configure": can_configure(request.membership),
            "can_assign_groups": can_assign_groups(request.membership),
            # Area leaders only do the practical evaluation, not the questionnaires.
            "module_links": {
                "formularios": bool({Action.EDIT, Action.DESIGN} & form_actions),
                "evaluar": Action.LEADER_EVAL in form_actions,
                "matriz": Action.VIEW in role_actions(request.membership.role, Module.MATRIZ),
            },
        },
    )


def accept_invitation(request, token):
    try:
        invitation = Invitation.objects.select_related("client").get_by_token(token)
    except Invitation.DoesNotExist:
        raise Http404 from None
    if not invitation.is_pending or not invitation.client.is_active:
        return render(request, "core/invitation_invalid.html", status=410)

    user = invitations.existing_user(invitation)
    if user is not None:
        # Existing account: they must be logged in as that account to accept.
        if not request.user.is_authenticated:
            messages.info(
                request,
                _("Inicia sesión con %(email)s para aceptar la invitación.")
                % {"email": invitation.email},
            )
            return redirect_to_login(request.get_full_path())
        if request.user != user:
            return render(
                request, "core/invitation_wrong_user.html", {"invitation": invitation}, status=403
            )
        if request.method == "POST":
            invitations.accept(invitation, user)
            return redirect("client_home", client_slug=invitation.client.slug)
        return render(request, "core/invitation_accept.html", {"invitation": invitation})

    form = AcceptInvitationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if request.user.is_authenticated:
            logout(request)
        user = User.objects.create_user(
            email=invitation.email,
            password=form.cleaned_data["password1"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
        )
        invitations.accept(invitation, user)
        login(request, user)
        return redirect("client_home", client_slug=invitation.client.slug)
    return render(request, "core/invitation_accept.html", {"invitation": invitation, "form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
