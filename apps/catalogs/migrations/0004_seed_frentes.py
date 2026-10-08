"""The four fronts of the Ruta (Parte B §5), named as the indicator groups in §8."""

from django.db import migrations

FRENTES = [
    ("impactos", "Impactos"),
    ("comunicacion", "Comunicación"),
    ("movilizacion", "Movilización"),
    ("formacion", "Formación"),
]


def seed(apps, schema_editor):
    Item = apps.get_model("catalogs", "SystemCatalogItem")
    for order, (code, label) in enumerate(FRENTES, start=1):
        Item.objects.get_or_create(catalog="frente", code=code,
                                   defaults={"label": label, "order": order})


class Migration(migrations.Migration):
    dependencies = [("catalogs", "0003_alter_historicalsystemcatalogitem_catalog_and_more")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
