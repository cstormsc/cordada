from django.core.management.base import BaseCommand, CommandError

from apps.plataforma import demo


class Command(BaseCommand):
    help = (
        f"Crea el cliente de demostración «{demo.NAME}» (/c/{demo.SLUG}/) con datos de ejemplo. "
        "Con --reset lo borra y lo vuelve a crear."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email", required=True, help="Cuenta existente que entra como Administración."
        )
        parser.add_argument("--reset", action="store_true", help="Borra la demo anterior primero.")

    def handle(self, *args, email, reset, **options):
        if reset and demo.purge():
            self.stdout.write("Demo anterior borrada.")
        from apps.core.models import Client

        if Client.objects.filter(slug=demo.SLUG).exists():
            raise CommandError("La demo ya existe. Usa --reset para volver a crearla.")
        try:
            client = demo.Builder(email, out=self.stdout.write).run()
        except ValueError as e:
            raise CommandError(str(e)) from None
        self.stdout.write(self.style.SUCCESS(f"Listo: /c/{client.slug}/ · entra con {email}"))
