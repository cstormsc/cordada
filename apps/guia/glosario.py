# ruff: noqa: E501 (one definition per line reads better than wrapped strings)
"""Short definitions behind the "?" next to terms across the site ({% ayuda "clave" %}),
also listed in the field guide's Glosario. One place, so the tooltips and the guide agree.

Methodology terms that already live in the system catalogs (fronts, stages) use their own
help text instead ({% ayuda_catalogo item %}); this file covers the platform's vocabulary.
"""

from django.utils.translation import gettext_lazy as _

# section -> [(key, term, definition)]
SECCIONES = [
    (
        _("Roles"),
        [
            ("rol_administracion", _("Administración (consultora)"), _("Configura el espacio del cliente (catálogos, indicadores) y edita todos los módulos.")),
            ("rol_equipo_cambio", _("Equipo de cambio"), _("Gestiona la matriz, la ruta y la bitácora, valida lo que se propone desde terreno y es el único que ve el detalle individual de los cuestionarios.")),
            ("rol_capitan", _("Capitán"), _("Referente de uno o más grupos impactados: propone impactos, registra tickets y ve en la Ruta las actividades de sus grupos.")),
            ("rol_guia", _("Guía"), _("Acompaña a los grupos en terreno: propone impactos, clasifica tickets y diseña cuestionarios y listas de observación.")),
            ("rol_equipo_tecnico", _("Equipo técnico"), _("TI: propone impactos y resuelve los tickets técnicos que se le derivan.")),
            ("rol_patrocinador", _("Patrocinador y PMO"), _("Sigue el avance: ve la matriz, la ruta y el dashboard (resultados agregados), y puede comentar. No edita.")),
            ("rol_lider_area", _("Líder de área"), _("Evalúa en la práctica a las personas de su equipo y sube el resumen firmado.")),
            ("grupo_impactado", _("Grupo impactado"), _("Personas a las que el cambio afecta de la misma forma, por ejemplo los cajeros de sucursal. Agrupa impactos, actividades, tickets y resultados.")),
        ],
    ),
    (
        _("Matriz de Impactos"),
        [
            ("impacto_flujo", _("Ciclo de vida de un impacto"), _("Propuesto → evaluado → en atención → atendido → cerrado, más descartado (con motivo) y reabierto. Para salir de Propuesto se exigen los campos de evaluación.")),
            ("impacto_propuesto", _("Propuesto"), _("Registrado o sugerido desde terreno. El equipo de cambio lo valida y completa su evaluación.")),
            ("impacto_evaluado", _("Evaluado"), _("Validado y con lo necesario para gestionarlo: magnitud, responsable, fecha y criterio de cierre.")),
            ("impacto_en_atencion", _("En atención"), _("Se están ejecutando las medidas y actividades para atenderlo.")),
            ("impacto_atendido", _("Atendido"), _("Cumple su criterio de cierre; falta confirmarlo y cerrarlo.")),
            ("impacto_cerrado", _("Cerrado"), _("Atendido y confirmado. Para editarlo hay que reabrirlo.")),
            ("impacto_descartado", _("Descartado"), _("No se gestionará; el motivo queda registrado. Puede reabrirse.")),
            ("impacto_reabierto", _("Reabierto"), _("Volvió a abrirse porque el problema reapareció o no quedó resuelto. El motivo queda registrado.")),
            ("prioridad", _("Prioridad"), _("De P1 Inmediata a P4 De seguimiento. Suma la magnitud (1 a 4) y el nivel de riesgo (1 a 4): 7–8 es P1, 5–6 P2, 4 P3 y 2–3 P4. El equipo de cambio puede ajustarla con una justificación.")),
            ("riesgo", _("Riesgo"), _("Probabilidad × severidad, de 1 a 16: Bajo hasta 3, Medio hasta 6, Alto hasta 9 y Crítico desde 12.")),
            ("severidad_extrema", _("Severidad extrema"), _("El nivel más grave de la escala de severidad. Siempre genera una alerta, sea cual sea la probabilidad.")),
            ("criterio_cierre", _("Criterio de cierre"), _("Con qué evidencia y con qué meta se demostrará que el impacto quedó atendido. Se define al evaluarlo, no al final.")),
            ("p1_sin_criterio", _("P1 sin criterio de cierre"), _("Impacto de prioridad inmediata que todavía no define cómo se demostrará que quedó atendido.")),
            ("descubierto", _("Descubierto"), _("Impacto activo (evaluado, en atención o reabierto) que no tiene ninguna actividad en la Ruta.")),
            ("bloqueado", _("Bloqueado"), _("Depende de otro impacto que sigue abierto. Es solo un aviso: no impide avanzar.")),
            ("dependencia", _("Depende de"), _("Este impacto necesita que otro avance primero. Solo avisa; nunca bloquea el ciclo de vida.")),
            ("grupo_sugerido", _("Grupo sugerido"), _("Grupo que alguien de terreno propuso porque todavía no existía. El equipo de cambio lo crea o lo asigna a uno existente.")),
            ("derivacion", _("Derivación"), _("Qué necesita el impacto para atenderse: comunicación, movilización y/o formación.")),
            ("certificacion_lider", _("Certificación del líder"), _("El líder de área observa a cada persona del grupo en su trabajo y certifica a quienes cumplen todos los criterios.")),
            ("fotos_etapa", _("Fotos por etapa"), _("Copia completa de la matriz al cerrar una etapa, para comparar después cómo evolucionó. Se puede exportar a Excel.")),
        ],
    ),
    (
        _("Ruta"),
        [
            ("cumplimiento", _("Cumplimiento"), _("Se calcula solo: hecha a tiempo, hecha con retraso, no realizada (pasó la fecha y no se hizo), no planificada o pendiente.")),
            ("no_realizada", _("No realizada"), _("Actividad cuya fecha planificada ya pasó y todavía no está completada.")),
            ("no_planificada", _("No planificada"), _("Actividad que surgió sobre la marcha, sin fecha planificada.")),
            ("huerfana", _("Huérfana"), _("Actividad que no está vinculada a ningún impacto de la matriz.")),
            ("vocero", _("Líder o vocero"), _("Quién da la cara en una comunicación, por ejemplo el gerente que firma el mensaje.")),
            ("informe_cumplimiento", _("Informe de cumplimiento"), _("Lo planificado frente a lo hecho, por etapa o por mes, para las sesiones de cierre y apertura de etapa y el resumen al patrocinador.")),
        ],
    ),
    (
        _("Bitácora"),
        [
            ("ticket_flujo", _("Estados de un ticket"), _("Nuevo → en clasificación → validado → (derivado a TI) → resuelto → cerrado. Solo los técnicos van a TI.")),
            ("ticket_nuevo", _("Nuevo"), _("Registrado; espera que un guía o el equipo de cambio lo tome para clasificarlo.")),
            ("ticket_validado", _("Validado"), _("Categoría confirmada. Los técnicos se derivan a TI; el resto lo resuelve el equipo.")),
            ("ticket_derivado_ti", _("Derivado a TI"), _("En manos del equipo técnico. TI puede devolverlo, con motivo, si no es una falla.")),
            ("fallo_grave", _("Fallo grave"), _("Falla técnica que impide operar. Se deriva a TI de inmediato y se valida en paralelo.")),
            ("recurrente", _("Recurrente"), _("Ticket que repite un caso anterior. Sirve para detectar dudas que vuelven y reforzar la formación.")),
            ("a_mi_tambien", _("A mí también"), _("Quien tiene el mismo problema lo marca en el ticket existente en vez de registrar otro.")),
            ("primera_respuesta", _("Primera respuesta"), _("Cuándo alguien tomó el ticket por primera vez. Se registra solo con el primer cambio de estado.")),
            ("por_cada_100", _("Por cada 100"), _("Tickets del grupo por cada 100 personas, para comparar grupos de distinto tamaño.")),
            ("impacto_no_anticipado", _("Impacto no anticipado"), _("Un efecto del cambio que no estaba en la matriz. Desde el ticket se puede proponer como impacto.")),
            ("vista_ti", _("Vista TI en vivo"), _("Los tickets derivados a TI, primero los graves. Se actualiza sola cada 15 segundos.")),
        ],
    ),
    (
        _("Formularios"),
        [
            ("enlace_personal", _("Enlace personal"), _("Cada persona responde con su propio enlace, sin cuenta. Se exporta para enviarlo desde el correo del cliente y vence en el plazo configurado.")),
            ("nota_minima", _("Nota mínima"), _("Puntaje sobre 100 que hay que alcanzar para aprobar.")),
            ("intentos", _("Intentos"), _("Cuántas veces puede responder cada persona. Cuenta el mejor resultado.")),
            ("opcion_multiple", _("Opción múltiple"), _("Da el puntaje completo solo si se marcan todas las correctas y ninguna incorrecta.")),
            ("confidencialidad", _("Tamaño mínimo de grupo"), _("Los grupos con menos respuestas que este mínimo no muestran resultados, y si con eso todavía se podrían deducir, también se oculta el siguiente más pequeño. Así nadie queda identificado.")),
            ("verificacion", _("Verificación de competencias"), _("Qué parte del grupo aprobó el cuestionario vinculado al impacto.")),
            ("supervisor", _("Supervisor"), _("Correo del líder directo en la carga de personas. Con él se arma el equipo que evalúa cada líder de área.")),
            ("lista_observacion", _("Lista de observación"), _("Criterios que el líder evalúa como cumple o no cumple al observar a cada persona en su trabajo.")),
            ("cert_pendiente", _("Pendiente"), _("El líder todavía no evalúa a esta persona.")),
            ("cert_aplicado", _("Aplicado, por firmar"), _("Ya evaluada; falta subir el resumen firmado.")),
            ("cert_certificado", _("Certificado"), _("Cumple todos los criterios y el resumen firmado está subido.")),
            ("cert_en_refuerzo", _("En refuerzo"), _("No cumple algún criterio. Se avisa a los guías de su grupo para reforzar.")),
            ("resumen_firmado", _("Resumen firmado"), _("PDF con las evaluaciones, firmado por el líder. Al subirlo, cada persona queda certificada o en refuerzo.")),
        ],
    ),
    (
        _("Dashboard"),
        [
            ("avance_general", _("Avance general del proyecto"), _("Promedio de los cuatro frentes; cada frente es el promedio de sus indicadores en % que tienen datos. Provisional hasta que la metodología defina ponderaciones.")),
            ("indice_preparacion", _("Índice de preparación"), _("De 0 a 100 por grupo: promedio de sus impactos atendidos, la verificación y la certificación. Provisional.")),
            ("semaforo", _("Semáforo"), _("En meta, Atención o Bajo meta según los umbrales de cada indicador, siempre con ícono y texto. Los umbrales los define Administración en la configuración de indicadores.")),
            ("provisional", _("Provisional"), _("Cálculo de trabajo hasta que la metodología lo defina en detalle.")),
        ],
    ),
]  # fmt: skip

TERMINOS = {key: (term, text) for _s, items in SECCIONES for key, term, text in items}


def anchor(key):
    return f"glosario-{key}"
