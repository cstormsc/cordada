"""System catalogs and scales from Parte B §3 and §4.

Only values the document fixes are loaded. Still to be defined (§13), and
editable from /plataforma/catalogos/: the origin values, the written
definition of each scale level, and the resistance and preparation scales.
"""

from django.db import migrations

CATALOGS = {
    "tiempo": [
        ("horizonte", "Horizonte"),
        ("travesia", "Travesía"),
        ("cumbre", "Cumbre"),
        ("legado", "Legado"),
    ],
    "tipo_impacto": [
        ("proceso", "Proceso"),
        ("tecnologia", "Tecnología"),
        ("rol_funcion", "Rol o función"),
        ("estructura", "Estructura"),
        ("cultura", "Cultura"),
        ("conocimiento", "Conocimiento"),
    ],
    "categoria_ticket": [
        ("tecnico", "Técnico"),
        ("conocimiento", "Conocimiento"),
        ("adopcion", "Adopción"),
        ("proceso", "Proceso"),
        ("comunicacion", "Comunicación"),
        ("impacto_no_anticipado", "Impacto no anticipado"),
        ("sugerencia_mejora", "Sugerencia de mejora"),
    ],
    "tipo_cambio_conocimiento": [
        ("funcion_nueva", "Función nueva"),
        ("funcion_modificada", "Función modificada"),
        ("herramienta_proceso_nuevo", "Herramienta o proceso nuevo"),
        ("sin_aprendizaje", "Sin aprendizaje"),
    ],
    "evidencia_cierre": [
        ("formacion_completada", "Formación completada"),
        ("adopcion_medida", "Adopción medida"),
        ("tickets_bajo_umbral", "Tickets bajo un umbral"),
        ("verificacion_grupo", "Verificación con el grupo"),
        ("aprobacion_responsable", "Aprobación del responsable"),
    ],
}

SCALES = [
    ("magnitud", "Magnitud", ["Leve", "Moderado", "Alto", "Profundo"]),
    ("probabilidad", "Probabilidad", ["Improbable", "Posible", "Probable", "Casi segura"]),
    ("severidad", "Severidad", ["Menor", "Notable", "Mayor", "Extrema"]),
    ("resistencia", "Resistencia esperada", []),
    ("preparacion", "Preparación del grupo", []),
]


def seed(apps, schema_editor):
    Item = apps.get_model("catalogs", "SystemCatalogItem")
    Scale = apps.get_model("catalogs", "Scale")
    Level = apps.get_model("catalogs", "ScaleLevel")

    for catalog, items in CATALOGS.items():
        for order, (code, label) in enumerate(items, start=1):
            Item.objects.get_or_create(
                catalog=catalog, code=code, defaults={"label": label, "order": order}
            )

    for order, (code, name, levels) in enumerate(SCALES, start=1):
        scale, _ = Scale.objects.get_or_create(code=code, defaults={"name": name, "order": order})
        for value, label in enumerate(levels, start=1):
            Level.objects.get_or_create(scale=scale, value=value, defaults={"label": label})


class Migration(migrations.Migration):
    dependencies = [("catalogs", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
