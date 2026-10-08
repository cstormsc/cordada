from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import User


class Command(BaseCommand):
    help = "Crea un administrador de plataforma, o da ese permiso a una cuenta existente."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, email, **options):
        email = email.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            password = getpass("Contraseña: ")
            if password != getpass("Repite la contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")
            try:
                validate_password(password)
            except ValidationError as e:
                raise CommandError(" ".join(e.messages)) from None
            user = User.objects.create_user(email=email, password=password)
        user.is_platform_admin = True
        user.save(update_fields=["is_platform_admin"])
        self.stdout.write(self.style.SUCCESS(f"{email} es administrador de plataforma."))
