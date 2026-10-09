from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .permissions import can, can_assign_groups, can_configure


def platform_admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_platform_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def client_permission_required(module, action):
    """For views under /c/<client_slug>/. The middleware has resolved the membership."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not can(request.user, request.client, module, action, membership=request.membership):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def client_member_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)

    return wrapper


def client_admin_required(view):
    """Client configuration views under /c/<client_slug>/ (Administración role)."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not can_configure(request.membership):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def client_group_assigner_required(view):
    """Assigning impacted groups to members (change team and Administración)."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not can_assign_groups(request.membership):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
