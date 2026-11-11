"""Slows down password guessing on /entrar/: after too many failures for an account, or
from one address, further attempts are refused for a while without checking the password."""

import hashlib

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

WINDOW_SECONDS = 15 * 60
MAX_PER_ACCOUNT = 5
MAX_PER_ADDRESS = 20


def client_ip(request):
    """The visitor's address. Behind the HTTPS proxy or tunnel every request arrives from
    the proxy, so take the address it reports: the last one in X-Forwarded-For, which the
    proxy adds itself (earlier ones come from the visitor and can be made up)."""
    if request is None:
        return ""
    if settings.BEHIND_HTTPS_PROXY:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[-1].strip()
        if forwarded:
            return forwarded
    return request.META.get("REMOTE_ADDR", "")


def _keys(username, ip):
    account = hashlib.sha256(username.strip().lower().encode()).hexdigest()
    return f"login-fail:account:{account}", f"login-fail:ip:{ip}"


def _bump(key):
    if not cache.add(key, 1, WINDOW_SECONDS):
        try:
            cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.add(key, 1, WINDOW_SECONDS)


def is_blocked(username, ip):
    account, address = _keys(username, ip)
    return cache.get(account, 0) >= MAX_PER_ACCOUNT or cache.get(address, 0) >= MAX_PER_ADDRESS


def record_failure(username, ip):
    for key in _keys(username, ip):
        _bump(key)


def reset_account(username, ip):
    cache.delete(_keys(username, ip)[0])


class ThrottledAuthenticationForm(AuthenticationForm):
    throttled = False

    def clean(self):
        username = self.cleaned_data.get("username") or ""
        ip = client_ip(self.request)
        if is_blocked(username, ip):
            self.throttled = True
            raise ValidationError(
                _("Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo."),
                code="throttled",
            )
        try:
            cleaned = super().clean()
        except ValidationError:
            record_failure(username, ip)
            raise
        reset_account(username, ip)
        return cleaned
