from django.http import Http404

from .models import Client
from .permissions import get_membership
from .tenancy import reset_current_client, set_current_client


class ClientMiddleware:
    """Resolves /c/<client_slug>/ URLs to request.client and request.membership.

    Clients the user isn't an active member of answer 404, so their existence
    isn't revealed. Sets the current client for TenantScopedModel queries.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client = None
        request.membership = None
        try:
            return self.get_response(request)
        finally:
            token = getattr(request, "_client_token", None)
            if token is not None:
                reset_current_client(token)

    def process_view(self, request, view_func, view_args, view_kwargs):
        slug = view_kwargs.get("client_slug")
        if slug is None:
            return None
        if not request.user.is_authenticated:
            return None  # the view's login_required redirects to login
        client = Client.objects.filter(slug=slug, is_active=True).first()
        membership = client and get_membership(request.user, client)
        if not membership:
            raise Http404
        membership.client = client
        request.client = client
        request.membership = membership
        request._client_token = set_current_client(client)
        return None
