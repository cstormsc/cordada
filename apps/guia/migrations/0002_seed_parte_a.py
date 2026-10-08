"""Methodology from Parte A (borrador 0.1, octubre de 2026): guide topics, the
written definition of each scale level, and the help of Tiempos and Frentes.

Only empty fields are filled, so edits made from /plataforma/ are kept.
"""

from django.db import migrations

SCALE_HELP = {
    "magnitud": (
        "Mide cuánto cambia el trabajo de las personas. No mide el riesgo ni cuántas "
        "personas son. Se elige el nivel más alto cuyo criterio se cumpla con claridad, y "
        "los niveles Alto y Profundo se justifican con una frase breve."
    ),
    "probabilidad": "¿Qué tan probable es que el impacto genere un problema si no se actúa?",
    "severidad": "Si el problema ocurre, ¿qué tan grave es la consecuencia?",
    "resistencia": "[Por definir] Depende del diagnóstico previo al cambio.",
    "preparacion": "[Por definir] Depende del diagnóstico previo al cambio.",
}

SCALE_DEFINITIONS = {
    "magnitud": [
        "Ajuste menor: cambia una tarea o pantalla puntual. Basta con información o una "
        "guía rápida.",
        "Cambia una parte de las tareas diarias. Requiere formación corta o práctica guiada.",
        "Cambia la forma de trabajar en la mayoría de las tareas. Requiere formación "
        "estructurada con práctica y acompañamiento en la salida.",
        "Cambia el rol, la función o la estructura. Requiere formación extensa y "
        "acompañamiento sostenido.",
    ],
    "probabilidad": [
        "Poco probable: el grupo está preparado y no hay señales de dificultad.",
        "Puede ocurrir: hay algunos factores de dificultad.",
        "Más probable que ocurra que no: hay señales claras de resistencia o poca preparación.",
        "Ocurrirá salvo que se intervenga: hay evidencia concreta.",
    ],
    "severidad": [
        "Molestia o retraso puntual que se resuelve dentro del equipo.",
        "Afecta la productividad de un grupo por un tiempo limitado.",
        "Afecta la operación de un área o a clientes. Requiere escalar a la gerencia.",
        "Compromete una operación clave o el éxito del proyecto (incumplimiento regulatorio, "
        "daño significativo al cliente o detención de una operación crítica).",
    ],
}

CATALOG_HELP = {
    ("tiempo", "horizonte"): (
        "Foco: preparación del cambio y expectativas.\n"
        "Pregunta que responde: ¿por qué cambia y qué se espera de mí?\n"
        "Papel del líder: explica la razón del cambio, se compromete públicamente y reconoce "
        "lo que se deja atrás.\n"
        "Hito: diagnóstico previo como línea base, antes de lanzar los mensajes."
    ),
    ("tiempo", "travesia"): (
        "Foco: preparación para la implementación.\n"
        "Pregunta que responde: ¿qué cambia, cuándo y qué debo hacer para estar listo?\n"
        "Papel del líder: da certeza y se hace visible en los momentos de mayor duda.\n"
        "Hito: formación y preparación de los grupos. Termina con la revisión de salida a "
        "producción."
    ),
    ("tiempo", "cumbre"): (
        "Foco: implementación y motivación.\n"
        "Pregunta que responde: ¿cómo me apoyan y cómo vamos?\n"
        "Papel del líder: presencia en la salida, reconocimiento de logros y mensajes de "
        "avance.\n"
        "Hito: salida, acompañamiento y atención de tickets."
    ),
    ("tiempo", "legado"): (
        "Foco: sostenimiento.\n"
        "Pregunta que responde: ¿qué logramos y cómo hacemos que se quede?\n"
        "Papel del líder: refuerza el nuevo modo de trabajo, comunica los resultados y cierra "
        "el ciclo, de modo que el cambio deje huella en la organización.\n"
        "Hito: medición de adopción, diagnóstico posterior, cierre del ciclo y transferencia "
        "a la operación."
    ),
    ("frente", "impactos"): (
        "Identificación de impactos. Construye y mantiene la matriz. Se nutre de talleres, de "
        "la presencia en los equipos técnicos, de las solicitudes de cambio de la PMO, de los "
        "tickets y de lo que escuchan los capitanes."
    ),
    ("frente", "comunicacion"): (
        "Embebida en los equipos técnicos: busca la información en lugar de esperar a que se "
        "la entreguen. Mantiene el registro de eventos comunicables, construye la imagen de "
        "los líderes y no comunica lo que el equipo técnico no ha confirmado. Su efecto lo "
        "mide movilización."
    ),
    ("frente", "movilizacion"): (
        "Convoca, ejecuta y mide la participación de las personas impactadas: actividades "
        "conjuntas que no son formación, medición de la respuesta a la comunicación y "
        "acompañamiento en la salida a producción."
    ),
    ("frente", "formacion"): (
        "Se deriva de la matriz: solo se forma lo que cambia. Se concentra en la formación "
        "técnica e incluye la formación de los capitanes. Los guías dictan las formaciones y "
        "luego quedan disponibles durante la salida."
    ),
}

TEMAS = [
    (
        "principios",
        "Resumen y principios",
        """Cordada es un marco de ejecución de gestión del cambio, pensado sobre todo para implementaciones técnicas (sistemas, herramientas y procesos nuevos). Se entrega al cliente en una formación. No trata el componente humano y emocional del cambio, que se aborda en programas de formación independientes, con los que se integra. Su lema es "nadie sube solo": una cordada es el grupo de escaladores unidos por una misma cuerda.

1. La Matriz de Impactos es el núcleo. Todo lo demás nace de ella y vuelve a ella. Comienza en la planificación y es un documento vivo durante todo el proyecto.
2. Cuatro frentes siempre presentes. Cambia la profundidad según el proyecto, no la estructura.
3. Formación solo sobre lo que cambia. El diseño técnico se dirige a la diferencia entre lo que la persona sabe hoy y lo que necesitará saber.
4. Comunicación embebida. El equipo de cambio forma parte del día a día de los equipos técnicos y busca la información, en lugar de esperar a que se la entreguen.
5. El equipo de cambio es intermediario y defensor de las personas impactadas, y socio de la PMO.
6. Soporte cercano. Capitanes y guías forman una cadena de apoyo que acompaña a las personas, sobre todo en la salida a producción.
7. Todo se mide. Los indicadores tienen escala o porcentaje, y el estado del cambio se diagnostica antes y después.
8. Patrocinio activo y visible. Un patrocinador de negocio da la cara y habilita los recursos.""",
    ),
    (
        "glosario",
        "Glosario",
        """Personas impactadas: quienes reciben el cambio. Es el término general del marco; en el acompañamiento técnico también se les llama usuarios.
Matriz de Impactos: documento central que enumera cada impacto, a quién afecta, sus riesgos, la mitigación, el plan de acción y el criterio de cierre.
Frentes: las cuatro líneas de trabajo: identificación de impactos, comunicación, movilización y formación.
Tiempos: las cuatro etapas del marco: Horizonte, Travesía, Cumbre y Legado.
Patrocinador: líder de negocio que respalda el cambio, es su vocero y aprueba recursos.
Equipo de cambio: equipo que ejecuta los cuatro frentes.
Capitán: miembro de los equipos impactados, con perfil docente y formación adicional, que acompaña a sus pares y es el primer contacto de soporte.
Guía: formador que dicta las formaciones, mentorea a los capitanes y es la fuente de conocimiento a la que ellos acuden.
Cordada: nombre del marco. También alude a la cadena de apoyo entre capitanes, guías y equipo de cambio.
Ruta, Bitácora, Guía de campo: instrumentos de la plataforma (plan de actividades, registro de tickets y material de la metodología).""",
    ),
    (
        "matriz",
        "La Matriz de Impactos",
        """La matriz responde a: ¿qué cambia, para quién, qué puede salir mal, qué hacemos al respecto y cómo sabremos que quedó atendido? Se crea en la planificación y se actualiza mientras surgen impactos nuevos.

Dos reglas de diseño:
- Más selección que texto libre. Solo los campos de contenido son texto; todo lo que alimenta un indicador es selección, escala, fecha o número.
- Dos tipos de catálogos. Los del sistema (escalas, estados, tipos de impacto) son fijos para que los resultados sean comparables entre proyectos. Los del cliente (grupos impactados, categorías de responsable, áreas) los crea cada cliente al configurar su espacio.

Cada campo muestra una nota de ayuda que explica qué debe completarse, y cada nivel de las escalas muestra su definición al seleccionarlo.""",
    ),
    (
        "ciclo-de-vida",
        "Ciclo de vida del impacto",
        """- Propuesto: cualquier fuente lo registra: taller de planificación, reunión técnica, ticket de la Bitácora, solicitud de cambio de la PMO, diagnóstico o comentario de un capitán.
- Evaluado: el equipo de cambio completa las escalas, deriva a los frentes y define el criterio de cierre. Se calcula la prioridad.
- En atención: tiene acciones en marcha.
- Atendido: cumple su criterio de cierre.
- Cerrado: se confirma y queda archivado.

Un impacto también puede quedar descartado (con motivo registrado) o reabierto si reaparecen señales, por ejemplo tickets recurrentes sobre el mismo tema.

Quién propone: el equipo de cambio, los capitanes, los guías y el equipo técnico. El equipo de cambio valida antes de pasar a Evaluado.

Criterio de cierre: se define al registrar el impacto, no al final. Tiene un tipo de evidencia (formación completada, adopción medida, tickets bajo un umbral, verificación con el grupo, aprobación del responsable), una meta numérica y una descripción breve.

Historial: cada cambio queda registrado y al cerrar cada etapa se guarda una foto de la matriz.""",
    ),
    (
        "regla-decision",
        "Regla de decisión entre frentes",
        """Si solo hay que informar, es comunicación. Si las personas deben participar, probar o validar, es movilización. Si hay una brecha de conocimiento o habilidad técnica, es formación.

Los cuatro frentes están siempre presentes en todos los proyectos. En los pequeños se reducen a pocas acciones, y cuando un frente no aplica a un impacto se indica de forma explícita. Cada equipo organiza los frentes según sus recursos.""",
    ),
    (
        "frentes",
        "Los cuatro frentes",
        """Identificación de impactos
Construye y mantiene la matriz. Se nutre de talleres, de la presencia en los equipos técnicos, de las solicitudes de cambio de la PMO, de los tickets y de lo que escuchan los capitanes.

Comunicación
Embebida: forma parte de los equipos técnicos, cuya prioridad no son las personas impactadas. El oficial de comunicación actúa como un periodista que busca la información, y si no puede hacerlo, lo hace el equipo de cambio, el director del proyecto o la PMO.
- Registro de eventos comunicables: lista viva de hitos, decisiones, cambios y riesgos detectados, con su público y prioridad.
- Imagen de los líderes: construye los mensajes alineados con el tiempo en que se está, y define qué papel cumple cada líder en cada momento.
- Verificación antes de comunicar: no se comunica lo que el equipo técnico no ha confirmado.
- Efecto de la comunicación: lo mide movilización, no el propio frente.

Movilización
Convoca, ejecuta y mide la participación de las personas impactadas.
- Actividades conjuntas con el equipo de cambio que no son formación (sesiones, pilotos, redes de capitanes, retroalimentación estructurada).
- Medición de la respuesta a las acciones de comunicación: participación, comprensión y acciones realizadas.
- Acompañamiento en la salida a producción, con fase propia alrededor del arranque.

Formación
- Se deriva de la matriz: solo se forma lo que cambia.
- Se concentra en la formación técnica; la formación del componente humano y emocional se integra desde los programas existentes [por definir cómo].
- Incluye la formación de los capitanes. Los guías dictan las formaciones y luego pasan a un rol de disponibilidad permanente durante la salida.""",
    ),
    (
        "tiempos",
        "Los cuatro tiempos",
        """Su estructura se inspira en modelos clásicos de transición (final, zona neutral y nuevo comienzo), con un cuarto tiempo de sostenimiento. El foco, la pregunta que responde, el papel del líder y los hitos de cada tiempo están en el catálogo "Tiempos del marco", más abajo.

Hitos por tiempo
- Horizonte: diagnóstico previo como línea base, antes de lanzar los mensajes.
- Travesía: formación y preparación de los grupos. Termina con la revisión de salida a producción.
- Cumbre: salida, acompañamiento y atención de tickets.
- Legado: medición de adopción, diagnóstico posterior, cierre del ciclo y transferencia a la operación.""",
    ),
    (
        "figuras",
        "Figuras y gobierno",
        """Patrocinador
Es único, o si hay varios, uno es el principal. Define la vocería y el liderazgo del equipo.
- Perfil: de negocio y no solo técnico, por ejemplo la vicepresidencia de finanzas, la gerencia general o la de compras. Debe poder aprobar recursos con rapidez en casos extraordinarios y estar cerca de las contrataciones.
- Funciones: vocero del cambio, respaldo al acceso del equipo de cambio, aprobación de recursos, decisión de salida a producción y reconocimiento a quienes avanzan.
- Condiciones: un acuerdo de patrocinio inicial con la dedicación mínima acordada, y un patrocinador delegado para el día a día [propuesta].

Equipo de cambio
Su composición depende de los recursos de cada cliente. Reporta al patrocinador y mantiene una relación de socio con el director del proyecto y la PMO, con acceso amplio a los gerentes del proyecto. Un acuerdo de acceso al inicio (reuniones técnicas, comités de control de cambios, información del proyecto) es condición de arranque.

Capitanes
Se escogen entre los miembros de los equipos impactados con perfil docente, porque ya tienen relación con sus pares; no se contrata a alguien extra. Reciben formación adicional para acompañar. [propuesta] Criterios de selección, acuerdo con el jefe inmediato para liberar tiempo y algún reconocimiento por el rol.

Guías
Son los formadores. Mentorean a los capitanes y son la fuente de conocimiento cuando estos no pueden resolver. Durante la salida están disponibles por chat, mensajería o presencialmente.

Derechos de decisión [propuesta]
- Recursos extraordinarios: decide el patrocinador; participan el director del proyecto y el equipo de cambio.
- Salida a producción: decide el patrocinador, con el director; el equipo de cambio presenta el índice de preparación.
- Prioridad y contenido de la matriz: decide el equipo de cambio; participan el director (impactos técnicos) y el patrocinador (los P1).
- Mensajes clave y vocería: el patrocinador aprueba; comunicación los construye.
- Selección de capitanes: el equipo de cambio con los jefes de área; el patrocinador respalda el tiempo liberado.""",
    ),
    (
        "ceremonias",
        "Ceremonias",
        """- Avance general (mensual, con el patrocinador): visión general, impactos P1, riesgos críticos, decisiones pendientes y experiencias del proyecto.
- Apertura y cierre de etapa (en cada tiempo): el cierre presenta el cumplimiento del plan y la apertura presenta el plan ajustado de la etapa siguiente.
- Alineación de frentes (semanal, del equipo de cambio): coordinar los cuatro frentes.
- Revisión de salida a producción (al final de Travesía): decidir con el índice de preparación sobre la mesa: adelante, adelante con condiciones o aplazar.

El equipo de cambio no tiene otras ceremonias recurrentes, porque trabaja de forma colaborativa y está informado de forma constante.""",
    ),
    (
        "acompanamiento",
        "Acompañamiento",
        """Es la función de movilización que atiende a las personas durante la salida a producción.
- Cadena de soporte: el capitán es el primer contacto, el guía es la fuente de conocimiento, el equipo de cambio clasifica y da seguimiento, y TI atiende los fallos técnicos. Los impactos P1 llegan al patrocinador sin pasar por toda la cadena.
- Ventana de acompañamiento y tiempos de respuesta: [por definir].
- Categorías de ticket: técnico, conocimiento, adopción, proceso, comunicación, impacto no anticipado y sugerencia de mejora.
- Filtro previo: capitanes y guías clasifican si un error es realmente técnico o de conocimiento. Solo los técnicos validados pasan a TI, lo que reduce el ruido para el equipo técnico.
- Urgencia: un fallo grave se deriva de inmediato y se valida en paralelo. TI puede devolver un ticket mal clasificado.
- Trazabilidad: los casos técnicos se registran en el sistema del cliente y el ticket del marco guarda el número de ese caso.
- Retroalimentación: las dudas recurrentes alimentan refuerzos de formación, mensajes de comunicación y nuevos impactos en la matriz.""",
    ),
    (
        "medicion",
        "Medición",
        """Cuatro niveles
- Ejecución: ¿hicimos lo planificado?
- Respuesta: ¿la gente reaccionó?
- Adopción: ¿cambió lo que hacen?
- Resultados: ¿se lograron los beneficios del proyecto?

Exigencias para cada indicador: fórmula clara, escala o porcentaje de cumplimiento, fuente del dato, frecuencia y responsable. Los umbrales de cada uno [por definir].

Diagnóstico y preparación
- Diagnóstico previo (línea base): mide el estado antes del cambio, incluida la resistencia emocional. Se aplica al inicio de Horizonte, antes de lanzar los mensajes. Sus características (qué mide, a quién se aplica, anonimato y repetición) [por definir].
- Diagnóstico posterior: se repite en Legado para comparar con la línea base.
- Índice de preparación por grupo: combina impactos mitigados, formación completada, mensajes comprendidos y capitán activo. Se presenta en la revisión de salida a producción [umbrales por definir].""",
    ),
    (
        "cierre",
        "Cierre y salida del equipo de cambio",
        """La salida ocurre cuando el cambio ya se ejecutó y, a criterio del equipo, se mide la aceptación. Como guía, se apoya en tres tipos de evidencia:
1. Adopción cuantitativa sostenida: usuarios activos, procesos ejecutados correctamente u otras mediciones, con una meta y una ventana de tiempo.
2. Diagnóstico posterior, comparado con la línea base.
3. Estado de la matriz y de la Bitácora: sin impactos críticos abiertos y con los tickets en descenso.

La salida se presenta al patrocinador en la sesión de cierre final, con un informe breve de resultados, las lecciones aprendidas y el modo en que queda el soporte una vez que el equipo se retira.""",
    ),
    (
        "referencias",
        "Referencias y atribución",
        """La estructura se apoya en prácticas ampliamente difundidas, con nomenclatura propia: la evaluación de impacto del cambio y el análisis de interesados (estándares y guías como los de ACMP y PMI), los registros de riesgos de la gerencia de proyectos, los modelos de transición y de cambio de Lewin, Bridges y Kotter, el modelo ADKAR de Prosci como inspiración para las medidas de mitigación y los cuatro niveles de evaluación de la formación de Kirkpatrick. Se utilizan como inspiración y no se reproducen plantillas ni nombres de marca.""",
    ),
]


def _fill(obj, field, value):
    if value and not getattr(obj, field):
        setattr(obj, field, value)
        obj.save(update_fields=[field])


def seed(apps, schema_editor):
    Scale = apps.get_model("catalogs", "Scale")
    Level = apps.get_model("catalogs", "ScaleLevel")
    Item = apps.get_model("catalogs", "SystemCatalogItem")
    Tema = apps.get_model("guia", "Tema")

    for scale in Scale.objects.filter(code__in=SCALE_HELP):
        _fill(scale, "help_text", SCALE_HELP[scale.code])
    for code, definitions in SCALE_DEFINITIONS.items():
        for value, definition in enumerate(definitions, start=1):
            for level in Level.objects.filter(scale__code=code, value=value):
                _fill(level, "definition", definition)
    for (catalog, code), help_text in CATALOG_HELP.items():
        for item in Item.objects.filter(catalog=catalog, code=code):
            _fill(item, "help_text", help_text)
    for orden, (slug, titulo, contenido) in enumerate(TEMAS, start=1):
        Tema.objects.get_or_create(
            slug=slug, defaults={"titulo": titulo, "contenido": contenido, "orden": orden}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("guia", "0001_initial"),
        ("catalogs", "0005_grupoimpactado_personas_and_more"),
    ]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
