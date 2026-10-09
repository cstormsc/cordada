# Informe de QA — Cordada · tenant PrecisionQA Group

**Fecha:** 09/10/2026 · **Entorno:** local (`make up`, http://localhost:8000) · **Commit:** `de04db7`
**Respaldo previo a las pruebas:** `backups/cordada-20261009-131903.dump` (+ `-media.tar.gz`) — restaurar con las instrucciones del README para deshacer todos los datos de QA.

## Resumen

| | |
|---|---|
| Comprobaciones ejecutadas | ~470 (264 de acceso por rol × página + ~205 funcionales) |
| Exitosas | ~455 |
| Defectos confirmados | 4 |
| Diferencias con la documentación / decisiones pendientes | 4 |
| Mejoras menores (UX / validación) | 7 |
| Errores 500 en el servidor | **0** (las 139 trazas del log son 403 esperados de las pruebas negativas) |
| Errores de consola JS | 0 |

**Método:** pruebas HTTP reales contra el servidor en marcha (formularios con CSRF, una sesión por rol), más el navegador integrado para lo que depende de JS (tablero, htmx, dashboard, ancho de teléfono). Cuentas de prueba creadas: `qa-plataforma@precisionqa.test` (admin. de plataforma) y `qa-<rol>@precisionqa.test` para los 7 roles, además de `qa-invitado@precisionqa.test` (por invitación). La contraseña está solo en el scratchpad de la sesión.

---

## 1. Defectos encontrados

**Los cuatro (D1–D4) quedaron corregidos el 09/10/2026 en el commit `0df6d99`, con pruebas de regresión.**

| # | Severidad | Módulo | Defecto | Reproducción | Sugerencia |
|---|---|---|---|---|---|
| D1 ✅ | Media | Plataforma → Catálogos | Se permiten etiquetas duplicadas dentro del mismo catálogo del sistema. | Crear dos veces "Bitácora" en *Origen*: el segundo queda con código `bitacora_2` y aparecen dos "Bitácora" en el desplegable de la Matriz. (QA desactivó el duplicado.) | Validar etiqueta única (sin distinguir mayúsculas) por catálogo en `SystemCatalogItemForm`. |
| D2 ✅ | Baja | Bitácora → Métricas | Cuando el promedio es 0,0 h, "h promedio a la primera respuesta / resolución" muestra "—" (como si no hubiera datos). | Tickets respondidos/resueltos en menos de ~3 min → promedio 0,0 → se ve "—". | `metricas.html`: usar `default_if_none:"—"` en lugar de `default:"—"`. |
| D3 ✅ | Baja | Plataforma → Guía → Plantillas | El mensaje de error expone el nombre interno de la restricción de BD. | Guardar plantilla sin archivo ni enlace: *"…No se cumple la restricción "guia_plantilla_archivo_xor_url"."* | Validar en `clean()` del formulario para que solo salga el mensaje amigable. |
| D4 ✅ | Baja | Matriz | Se acepta una meta de criterio de cierre negativa. | Crear impacto con `criterio_meta = -50` → se guarda (IMP-012). | `MinValueValidator(0)` en `criterio_meta`. |

## 2. Diferencias con la documentación / decisiones pendientes

| # | Tema | Observación |
|---|---|---|
| P1 | Catálogo **Origen** vacío | La migración no siembra *Origen* (Parte B §13.1 lo deja por definir), así que el desplegable de la Matriz estaba vacío y la asignación automática desde la Bitácora no funcionaba. QA creó: Bitácora (código `bitacora`), Levantamiento con el grupo, Análisis documental y Equipo técnico. Con eso, ya funciona la asignación automática. |
| P2 | Los proponentes no ven sus propuestas — **resuelto:** ahora ven «Mis propuestas» con su estado | El README dice que Capitán, Guía y Equipo técnico "ven solo sus propuestas", pero el código (docstring de `_get_impacto`) indica que "no las vuelven a ver": tras enviarla, solo se muestra el código IMP-xxx. Hay que decidir cuál es el comportamiento correcto y ajustar el README o el código. |
| P3 | Patrocinador puede comentar en impactos — **confirmado como intencional** (comenta; no edita ni adjunta; cubierto por test) | Los comentarios solo exigen permiso de ver; los adjuntos exigen editar. El Patrocinador (solo lectura) pudo comentar en IMP-004, pero no adjuntar. Hay que confirmar si es intencional. |
| P4 | Definiciones de escalas vacías | Magnitud, probabilidad y severidad no tienen definición por nivel (la plataforma lo marca). Es contenido de metodología; QA no lo inventó. |

## 3. Mejoras menores

1. **Matriz – "+ Nuevo grupo":** si se escribe el nombre y se guarda el impacto sin pulsar "Crear", el nombre se descarta en silencio (IMP-014 quedó sin grupo). Sugerencia: avisar o crear el grupo al guardar.
2. **Dashboard – datos externos sin validación de rango:** se aceptan adopción de 250 %, usuarios activos negativos y una fecha de 2030.
3. ✅ **Resuelto (commit `1196731`).** **Login sin límite de intentos:** 12 contraseñas erróneas seguidas, sin bloqueo ni demora (considerar `django-axes` o similar antes de producción).
4. **Fechas pasadas sin aviso:** fecha de compromiso del impacto (2020) y vencimiento del cuestionario (2020) se aceptan.
5. **Ruta:** una actividad marcada "no planificada" acepta igualmente una fecha planificada (ACT-010).
6. **Títulos de página genéricos ("Cordada")** en: matriz/nuevo, matriz/fotos, formularios/…/resultados, listas/…/seguimiento, dashboard/datos, dashboard/indicadores, configuracion/personas.
7. **Accesibilidad:** hay campos sin `<label>` asociado (solo placeholder) en el formulario de impacto ("Nombre del grupo"), en el detalle del impacto (2) y en el detalle del ticket (3).

**No verificable por automatización:** el gesto de arrastrar en el tablero kanban. SortableJS usa drag-and-drop nativo, que las herramientas sintéticas no disparan. Sí quedaron verificados el endpoint (`mover`: permitido, prohibido, aviso de dependencia, 403 por rol) y el cableado JS (7 listas Sortable, columnas permitidas por tarjeta, token CSRF). **Recomendación: arrastrar una tarjeta a mano una vez.**

---

## 4. Comprobaciones exitosas

### 4.1 Acceso por rol (264 solicitudes, 33 páginas × 8 perfiles)
- ✅ Ninguna página devolvió 500. Cada 200/403/404 coincide con `apps/core/permissions.py` (Parte B §2).
- ✅ Los proponentes que abren `/matriz/` son redirigidos al formulario corto de propuesta.
- ✅ Líder de área: solo Guía y "Evaluar". Patrocinador: Matriz (lectura), Ruta, Dashboard y Guía.
- ✅ Solo el admin. de plataforma entra a `/plataforma/` y no ve datos del cliente (404 en `/c/…`).
- ✅ Un miembro que intenta abrir otro cliente recibe 404. Un anónimo es redirigido a `/entrar/`.

### 4.2 Configuración del cliente
- ✅ Crear grupos impactados (6, con nº de personas), unidades de los 4 tipos, cargos (4), categorías de responsable (3) y canales (4).
- ✅ Rechazos: nombre vacío, nombre duplicado, personas negativas, orden no numérico, nombre >150 caracteres, unidad sin tipo, tipo de unidad inválido.
- ✅ `<script>` en un nombre se guarda escapado (no se ejecuta).
- ✅ Editar un grupo existente.
- ✅ Asignar grupos a Capitán, Guía y Equipo de cambio (con mensaje de confirmación).

### 4.3 Administración de plataforma
- ✅ Crear ítems del catálogo Origen; el código se genera con slug (`Bitácora` → `bitacora`).
- ✅ Etiqueta vacía rechazada. Editar un ítem y guardar las 3 escalas sin cambios funciona.
- ✅ Escala con nivel sin nombre: rechazada ("Los cuatro niveles necesitan nombre").
- ✅ Cliente: guardar configuración; tamaño mínimo de grupo 0 rechazado (≥1); retención negativa rechazada.
- ✅ Invitaciones: envío (correo en Mailpit con enlace), anulación (el enlace anulado da 410), aceptación con contraseña nueva (entra al cliente) y enlace no reutilizable (410).
- ✅ Invitaciones rechazadas: a un miembro existente, con correo inválido o con rol inexistente.
- ✅ Membresía: cambio de rol, desactivación (pierde acceso → 404) y reactivación (recupera acceso).
- ✅ Guía de campo: crear tema; slug duplicado e inválido rechazados.
- ✅ Plantillas: con archivo y con URL; sin ninguno de los dos, rechazada; `.exe` y `.html` rechazados por extensión.

### 4.4 Matriz de Impactos
- ✅ 8 impactos completos creados con todos los campos (origen, tipo, tiempo, grupo, escalas, derivación, formación, responsable, criterio y certificación).
- ✅ Riesgo y prioridad correctos según §3.4 en 8 combinaciones (Bajo 1 → Crítico 16; P1 a P4) y recálculo al editar (IMP-006 → Crítico 16, P1).
- ✅ Validaciones: título o descripción vacíos, personas negativas, magnitud 5, fecha inválida, grupo inexistente.
- ✅ Ciclo de vida completo en IMP-004:
  - Propuesto → Evaluado → En atención → Atendido → Cerrado → Reabierto (exige motivo) → En atención.
  - Descartar exige motivo; Descartado → Reabierto.
  - Transición no permitida rechazada; validar un impacto incompleto lista los campos faltantes.
- ✅ Ajuste de prioridad: exige justificación; P3 → P1 aplicado; valor inválido rechazado.
- ✅ Historial con transiciones y cambios de campos.
- ✅ Comentarios: con tildes; HTML escapado; vacío ignorado.
- ✅ Adjuntos aceptados: PDF y enlace.
- ✅ Adjuntos rechazados: `javascript:`, `.exe`, más de 10 MB y vacío.
- ✅ Descarga de adjuntos solo con permiso: Líder de área → 404; anónimo → login; `/media/` → 404.
- ✅ Dependencias: crear; ciclo directo, ciclo indirecto (4→9→5→4) y autodependencia rechazados; quitar dependencia.
- ✅ Dependencias por rol: el Capitán recibe 403 al crearlas.
- ✅ Dependencias en la vista: el filtro "Bloqueados" funciona y se avisa sin bloquear.
- ✅ Grupo inline (htmx): crea el grupo, normaliza espacios, reutiliza uno existente sin distinguir mayúsculas, muestra error si está vacío y el Capitán recibe 403. También probado en el navegador: "Mantención QA" se creó y quedó seleccionado.
- ✅ 9 filtros (estado, prioridad, grupo, tiempo, extrema, descubiertos, sin criterio, texto, caracteres especiales); valores inválidos no rompen.
- ✅ Tablero: carga, mover vía endpoint, error en movimiento no permitido, aviso de dependencia y Patrocinador con 403.
- ✅ Exportar a Excel (35 columnas), que respeta los filtros.
- ✅ Fotos por etapa: crear (Admin y Equipo de cambio), etapa obligatoria, exportar a Excel; el Patrocinador recibe 403.
- ✅ Permisos: el Patrocinador recibe 403 al cambiar estado.
- ✅ Propuestas de Capitán, Guía y Equipo técnico:
  - Formulario corto; el envío muestra el código.
  - El proponente no puede abrir el detalle (404) ni inyectar magnitud o estado por POST.
- ✅ Grupo sugerido en propuestas: el filtro lo muestra y se resuelve creando "Tesorería QA".

### 4.5 Ruta
- ✅ 8 actividades en los 4 frentes, con canal, vocero, impactos, grupos, indicador, responsable y evidencia.
- ✅ Cumplimiento calculado correctamente en los 5 casos: a tiempo, con retraso, no realizada, no planificada y pendiente.
- ✅ Validaciones: título vacío, sin frente, fecha inválida, "Completado" sin fecha real y fecha real futura.
- ✅ Editar actividad (pasa a "con retraso"); "Nueva actividad" desde un impacto lo preselecciona.
- ✅ Evidencias: PDF y enlace aceptados; `.svg` rechazado; descarga.
- ✅ 11 filtros, incluido el de huérfanas.
- ✅ Capitán: solo ve las actividades de sus grupos (3 de 9); actividad ajena → 404; no edita (403).
- ✅ Guía: no sube evidencias (403).
- ✅ Exportar a Excel.
- ✅ Informe en pantalla y PDF (sin filtro, etapa, mes, frente y mes inválido): 6 PDF válidos.

### 4.6 Bitácora
- ✅ 9 tickets en las 7 categorías, con urgencia normal y grave, registrados por Capitán, Guía, Admin y Equipo de cambio; incluye uno recurrente ("Repite el caso", solo para quien clasifica).
- ✅ Validaciones: ticket vacío y urgencia inválida. Equipo técnico no registra (403); Patrocinador sin acceso (403).
- ✅ Flujo de conocimiento:
  - Capitán no clasifica; Guía clasifica → valida → resuelve → cierra. La primera respuesta se registra sola.
  - Reabrir exige motivo; ticket cerrado inmutable; un no técnico no va a TI.
- ✅ Flujo técnico:
  - Validado no se resuelve sin TI → se deriva → vista TI en vivo con refresco.
  - TI devuelve con motivo obligatorio; TI registra el nº de caso (la Guía recibe 403).
  - TI resuelve pero no cierra; la Guía cierra.
- ✅ Fallo grave técnico: derivación directa por el Capitán y validación en paralelo, que no se puede repetir. Un grave no técnico no se deriva directo. Los graves aparecen primero en la vista TI.
- ✅ "A mí también": con detalle, se puede quitar y el autor recibe 403.
- ✅ Visibilidad del Capitán: tickets propios y de su grupo; los de otro grupo dan 404.
- ✅ Comentar y editar tickets.
- ✅ Impacto no anticipado → propone IMP-020 con origen "Bitácora" y grupo heredado; no se puede proponer dos veces, y otras categorías no proponen.
- ✅ Métricas para 3 roles y con filtros (incluida fecha inválida): por tipo, por cada 100 personas y casos que más se repiten.
- ✅ Exportar a Excel y 6 filtros de la lista.

### 4.7 Formularios
- ✅ Carga de personas (CSV): vista previa con nuevas/existentes, columnas reconocidas, grupos, supervisores con estado (sin cuenta, no es correo, otro rol, líder OK) y filas con error (duplicado por mayúsculas, correo inválido, vacío).
- ✅ Carga confirmada: 13 personas.
- ✅ Re-carga: actualiza el nombre y conserva el grupo y el supervisor no enviados.
- ✅ Formatos aceptados:
  - CSV latin-1 con `;`
  - CSV de una sola columna
  - Excel con encabezados alternativos (E-mail, Depto, Jefe), creando el grupo "Bodega Norte QA"
- ✅ Cargas rechazadas con mensaje claro: archivo vacío, `.txt`, sin columna correo y Excel corrupto. Confirmar dos veces no duplica (vista previa expirada). Sin "crear grupos" se avisa el grupo inexistente.
- ✅ Desactivar persona y filtro "Incluir inactivas". La Guía no ve el listado (403).
- ✅ Cuestionarios:
  - 5 preguntas: simple, sí/no y múltiple.
  - Problemas detectados antes de publicar: dos correctas, ninguna correcta, múltiple con una sola opción, sí/no con 3 opciones y texto vacío.
  - Reparto automático (20 × 5; 33,34/33,33/33,33). Suma ≠ 100 se guarda con aviso y bloquea la publicación; puntos negativos rechazados.
  - "Repartir en partes iguales"; reparto manual 40/15/15/15/15.
  - Nota >100 e intentos 0 rechazados.
  - Publicar fija preguntas y puntos. La Guía también crea y publica cuestionarios.
- ✅ Enlaces personales: generación por grupo y para todos, sin duplicados; exportación a Excel y CSV.
- ✅ Respuestas por enlace:
  - Puntajes 100, 85, 85, 85, 60 y 45 correctos, incluido el "todo o nada" en opción múltiple.
  - Segundo intento: aprueba o falla según corresponda; al agotar los intentos y tras aprobar no se ofrece el formulario.
  - Rechazos: respuesta incompleta, opción ajena, token inválido o alterado (404) y POST sin CSRF.
- ✅ Resultados:
  - Agregados por grupo, ocultos con menos de 5 respuestas.
  - Detalle individual solo para el Equipo de cambio; Patrocinador 403.
  - El impacto IMP-005 muestra la verificación (71 %).
  - Cerrar el cuestionario hace que los enlaces den 410.
- ✅ Evaluación del líder:
  - Lista: publicar sin criterios bloqueado; agregar, borrar y editar criterios; tras publicar no se modifica.
  - El líder ve exactamente su equipo (7 personas) y puede guardar evaluaciones parciales.
  - PDF prellenado; el acta rechaza archivos no PDF o ausentes.
  - Al subir el acta firmada: 5 certificados y 1 en refuerzo, con correo a los guías.
  - El seguimiento y el impacto IMP-010 reflejan los resultados, y el acta se puede descargar.
  - Con cuestionario, solo los aprobados (5 de 7) llegan a la lista del líder.

### 4.8 Dashboard
- ✅ 21 datos externos cargados para los 7 indicadores, por Admin y Equipo de cambio.
- ✅ Datos rechazados: valor vacío, fecha vacía, indicador inexistente y valor texto. Borrar datos funciona; la Guía recibe 403.
- ✅ Configuración de los 19 indicadores: umbrales, responsable y frecuencia.
- ✅ Umbral incoherente rechazado; desactivar un indicador lo oculta. El Equipo de cambio no configura (403).
- ✅ Dashboard para 4 roles y con 5 combinaciones de filtros (incluidos valores inválidos).
- ✅ Contenido: alertas (severidad extrema, grupos bajo el umbral), semáforo con ícono y texto, gráficos y "Ver tabla". Sin errores de consola.

### 4.9 Guía de campo
- ✅ Temas, catálogos y escalas visibles; el tema creado en plataforma aparece y su HTML se escapa.
- ✅ Plantillas: descarga y enlace externo.
- ✅ Documentos del cliente: PDF y enlace aceptados; vacío y `.js` rechazados.
- ✅ Documentos por rol: Capitán, Líder y Técnico los descargan pero no suben (403); eliminar documento funciona y el Equipo de cambio recibe 403.
- ✅ Los 12 enlaces de ayuda contextual apuntan a secciones existentes.

### 4.10 Seguridad, sesión y navegador
- ✅ Login erróneo con mensaje genérico (no revela si el correo existe).
- ✅ CSRF exigido en los POST internos.
- ✅ `/admin/` exige su propio login; cerrar sesión (solo POST); `/health/` OK.
- ✅ Cabeceras: `X-Frame-Options: DENY`, `nosniff` y `Referrer-Policy`.
- ✅ 22 páginas sin recursos JS/CSS rotos; sin desbordamiento horizontal a 375 px; htmx funciona en el navegador.

---

## 5. Datos de QA que quedaron en el tenant
- **Cuentas:** 9 usuarios `qa-*@precisionqa.test`.
- **Grupos:** 6 nuevos + Bodega Sur QA, Bodega Norte QA, Tesorería QA y Mantención QA. También unidades, cargos, categorías y canales.
- **Matriz:** IMP-004 a IMP-020 (QA), 2 fotos, adjuntos, comentarios y dependencias.
- **Ruta:** ACT-002 a ACT-010.
- **Bitácora:** TCK-001 a TCK-009.
- **Formularios:** 17 personas, CUE-001 (cerrado) y CUE-002, 2 listas de observación y 1 acta.
- **Dashboard:** 21 datos manuales y la configuración de 19 indicadores.
- **Guía:** 1 documento.
- **Plataforma:** 4 orígenes (+1 duplicado desactivado), 1 tema y 2 plantillas.

Para volver al estado anterior, restaurar el respaldo `cordada-20261009-131903`.
