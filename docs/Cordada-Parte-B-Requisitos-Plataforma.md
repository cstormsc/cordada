Markdown · Cordada-Parte-B-Requisitos-Plataforma.md

# Cordada: marco de gestión del cambio

## Parte B. Requisitos de la plataforma

*Borrador 0.1 para revisión · Octubre de 2026*

Este documento reúne las decisiones tomadas sobre la plataforma de Cordada, como insumo para el desarrollo. La metodología está en la Parte A. Aún no hay nada desarrollado. Lo no decidido aparece como **\[por definir\]** y lo propuesto, pendiente de aprobación, como **\[propuesta\]**. Hay maquetas de referencia del dashboard, la matriz y la Bitácora: [https://claude.ai/artifact/Rs6nUCSnHmKtJp4YAQY8YF](https://claude.ai/artifact/Rs6nUCSnHmKtJp4YAQY8YF)

---

## 1. Alcance y principios técnicos

**Qué es:** una aplicación web (responsive, se usa también desde el celular) que apoya la ejecución de Cordada. Se prueba primero en local y luego se publica en un servidor.

**Módulos:** Matriz de Impactos, Ruta, Bitácora, Formularios (verificación de competencias), Dashboard, Guía de campo y Administración. El consultor virtual queda para la versión 2.

**Principios**

1. **Más selección que texto libre.** Solo los campos de contenido son texto; lo que alimenta indicadores es selección, escala, fecha o número.
2. **Dos tipos de catálogos:** del sistema (fijos, iguales para todos los clientes) y del cliente (configurables).
3. **Estados estandarizados** para que los porcentajes de cumplimiento sean comparables entre proyectos.
4. **Ayuda contextual:** cada campo muestra una nota de ayuda y cada nivel de las escalas muestra su definición al seleccionarlo.
5. **El registro es un subproducto del trabajo,** no una carga extra: lo que se planifica y ejecuta en la plataforma genera los datos del dashboard.
6. **Multi-cliente:** cada cliente tiene su espacio con los datos aislados. Se propone una sola base de datos con el identificador del cliente en cada registro **\[propuesta\]**.
7. **Historial:** cada cambio queda registrado (quién, cuándo y qué) y se guarda una foto de la matriz al cerrar cada etapa.
8. **Idioma:** español desde el inicio, preparado para sumar otros idiomas.

**Stack acordado (local primero)**

| Capa | Tecnología |
| --- | --- |
| Aplicación | Django (Python) |
| Base de datos | PostgreSQL |
| Interfaz | Plantillas de Django con HTMX o Alpine.js |
| Gráficos | Chart.js o ECharts |
| PDF | WeasyPrint |
| Importar y exportar | openpyxl y CSV |
| Correo en pruebas | Mailpit (captura correos sin enviarlos) |
| Entorno | Docker y Docker Compose; control de versiones con Git |

---

## 2. Usuarios, roles y permisos

Las cuentas se crean por invitación dentro del espacio del cliente. Las personas que responden los cuestionarios **no tienen cuenta:** acceden con un enlace personal.

**\[propuesta\]** E = edita · V = ve · P = propone · R = registra

| Rol | Matriz | Ruta | Bitácora | Dashboard | Formularios | Guía de campo |
| --- | --- | --- | --- | --- | --- | --- |
| **Administración** (consultora) | E | E | E | V | E | E |
| **Equipo de cambio** | E | E | E | V | E y ve el detalle individual | V |
| **Capitán** | P | V (su grupo) | R | no | no | V |
| **Guía** | P | V | E (clasifica) | V | E (diseña instrumentos) | V |
| **Equipo técnico** | P | no | V y E (tickets derivados) | no | no | V |
| **Patrocinador y PMO** | V | V | no | V (agregado) | no | V |
| **Líder de área** | no | no | no | no | evaluación práctica de su equipo | V |

---

## 3. Catálogos y reglas de cálculo

### 3.1 Catálogos del sistema (fijos)

Tiempos (Horizonte, Travesía, Cumbre, Legado) · Tipos de impacto (proceso, tecnología, rol o función, estructura, cultura, conocimiento) · Origen de la detección · Escalas · Estados · Categorías de ticket.

### 3.2 Catálogos del cliente (configurables)

Grupos impactados · Categorías de responsable (por ejemplo, equipo técnico, PMO, gerencia) · Áreas, oficinas, sucursales y departamentos · Cargos. El cliente los crea al configurar su espacio y se guardan para agrupar resultados.

### 3.3 Escalas (cuatro niveles, con definición escrita para cada uno)

- **Magnitud:** Leve (1) · Moderado (2) · Alto (3) · Profundo (4).
- **Probabilidad:** Improbable (1) · Posible (2) · Probable (3) · Casi segura (4).
- **Severidad:** Menor (1) · Notable (2) · Mayor (3) · Extrema (4).
- **Resistencia esperada y preparación del grupo:** **\[por definir\]**, dependen del diagnóstico.

### 3.4 Cálculos

- **Nivel de riesgo** = probabilidad × severidad. Bandas: **Bajo** (1 a 3) · **Medio** (4 a 6) · **Alto** (8 y 9) · **Crítico** (12 a 16). Toda severidad *Extrema* genera una alerta, sin importar la probabilidad.
- **Prioridad** = valor de magnitud (1 a 4) + valor del nivel de riesgo (Bajo 1, Medio 2, Alto 3, Crítico 4). Suma 7 a 8: **P1 Inmediata**; 5 a 6: **P2 Prioritaria**; 4: **P3 Planificada**; 2 a 3: **P4 De seguimiento**. El equipo de cambio puede ajustarla con una justificación registrada **\[propuesta\]**.

| Riesgo ↓ / Magnitud → | Leve | Moderado | Alto | Profundo |
| --- | --- | --- | --- | --- |
| **Crítico** | P2 | P2 | P1 | P1 |
| **Alto** | P3 | P2 | P2 | P1 |
| **Medio** | P4 | P3 | P2 | P2 |
| **Bajo** | P4 | P4 | P3 | P2 |

Estas tablas dan resultados exactos, así que sirven como **pruebas automáticas** del desarrollo.

---

## 4. Módulo Matriz de Impactos

**Campos** (tipo entre paréntesis) **\[propuesta\]**

| Bloque | Campos |
| --- | --- |
| Identificación | ID (automático) · Título (texto corto) · **Descripción del impacto** (texto largo, con guía de redacción y archivos o enlaces opcionales) · Situación actual y futura (texto) · Origen (selección del sistema) |
| Clasificación | Tipo de impacto · Tiempo del marco |
| Quién | Grupo impactado (catálogo del cliente) · Número de personas impactadas (numérico) |
| Evaluación | Magnitud · Resistencia esperada · Preparación del grupo (escalas) |
| Riesgo | Descripción (texto) · Probabilidad · Severidad · Nivel de riesgo (calculado) |
| Derivación | Requiere comunicación, movilización, formación (sí/no cada uno) · Tipo de cambio en el conocimiento (función nueva, función modificada, herramienta o proceso nuevo, sin aprendizaje) · Criticidad y momento requerido de la formación · Actividades vinculadas (relación con Ruta) |
| Mitigación y acción | Medida (texto) · Responsable (usuario, con su categoría del cliente) · Fecha compromiso · Estado |
| Cierre | **Criterio de cierre:** tipo de evidencia (formación completada, adopción medida, tickets bajo un umbral, verificación con el grupo, aprobación del responsable), meta numérica y descripción breve · Requiere certificación del líder (sí/no) |
| Control | Prioridad (calculada) · Registrado por · Fechas de registro y actualización · Comentarios |

Campos obligatorios sugeridos: título, tipo, grupo, magnitud, derivación, responsable, fecha, estado y criterio de cierre **\[por definir la lista final\]**.

**Ciclo de vida del impacto:** Propuesto → Evaluado → En atención → Atendido → Cerrado, más **Descartado** (con motivo) y **Reabierto**. Reglas:

- Pueden proponer impactos el equipo de cambio, los capitanes, los guías y el equipo técnico. El equipo de cambio valida antes de pasar a *Evaluado*.
- El criterio de cierre se define al pasar a *Evaluado*, no al final.
- Un impacto pasa a *Atendido* cuando cumple su criterio de cierre.
- Foto de la matriz al cerrar cada etapa, y historial de cambios.

**Vistas y filtros:** por prioridad, estado, grupo y tiempo; impactos sin criterio de cierre; impactos sin actividades (descubiertos). Exportable a Excel.

---

## 5. Módulo Ruta

Plan de actividades de los cuatro frentes, con lo planificado y lo ejecutado en el mismo registro (el registro de comunicaciones es un tipo de actividad).

**Campos comunes:** frente · tiempo · grupo impactado · **impacto de la matriz al que responde** · responsable · fecha planificada y fecha real · estado · canal o formato · evidencia · indicador asociado. En comunicaciones, además, el **líder o vocero** que firma el mensaje.

**Estados:** no iniciado · en curso · completado · verificado.

**Cumplimiento:** hecha a tiempo · hecha con retraso · no realizada · **no planificada** (surgió sobre la marcha).

**Controles de coherencia:** una actividad sin impacto asociado se marca como "huérfana", y un impacto sin actividades como "descubierto".

**Salidas:** el informe de cumplimiento para las sesiones de cierre y apertura de etapa y el resumen mensual para el patrocinador, generados desde la plataforma **\[propuesta\]**.

---

## 6. Módulo Bitácora

Registro de tickets y consultas durante la implementación.

- **Categorías:** técnico · conocimiento · adopción · proceso · comunicación · impacto no anticipado · sugerencia de mejora.
- **Quién registra:** capitanes y guías. **Quién clasifica:** capitanes y guías validan si un caso es realmente técnico o de conocimiento antes de derivarlo a TI.
- **Estados:** nuevo → en clasificación → validado → derivado a TI → resuelto → cerrado.
- **Urgencia:** un fallo grave se deriva de inmediato y se valida en paralelo. TI puede devolver un ticket mal clasificado.
- **Campos:** grupo impactado · quien lo registra · categoría · urgencia · impacto de la matriz vinculado (opcional) · **número del caso en el sistema del cliente** · fechas de primera respuesta y de resolución.
- **Sistema del cliente:** los casos técnicos se ingresan también, en paralelo, en el sistema de mesa de ayuda del cliente. No hay integración en la primera versión.
- **Vista en tiempo real** para el equipo técnico con los tickets derivados.
- Un ticket de *impacto no anticipado* permite **proponer un impacto** en la matriz.
- **Métricas:** tickets por cada 100 usuarios, por tipo, tiempos y recurrencia.

---

## 7. Módulo Formularios (verificación de competencias)

### 7.1 Carga de personas

Archivo CSV o Excel con: **correo (único campo obligatorio)**, nombre, oficina, sucursal, departamento, supervisor y cargo. Una de las columnas (normalmente el departamento) se asigna al **grupo impactado** de la matriz, para que los resultados alimenten el criterio de cierre. Se valida el formato y se evitan correos duplicados.

### 7.2 Cuestionario

- **Tipos de pregunta:** selección simple · sí o no · opción múltiple de hasta 5 opciones.
- **Puntaje:** cada pregunta vale 100 % dividido entre el número de preguntas.
- Nota mínima para aprobar: **\[por definir\]**. Puntaje de la opción múltiple con varias respuestas correctas: **\[por definir\]** (supuesto: se suma completa solo si se marcan todas bien).
- Creado por el equipo de formación (guías) y vinculado al impacto que verifica.

### 7.3 Enlaces personalizados

- Un enlace único por correo. En la **primera fase la plataforma exporta un archivo con los enlaces** para enviarlos desde el correo del cliente. El **módulo de envío de correos** viene después.
- Vigencia e intentos permitidos: **\[por definir\]**.

### 7.4 Confidencialidad

- Los resultados son **confidenciales, no anónimos:** la plataforma sabe quién respondió, y así se le informa en la invitación.
- **Solo el equipo de cambio ve el detalle individual.** Patrocinadores y los demás roles ven resultados agregados.
- **Tamaño mínimo de grupo** en las vistas agregadas, para evitar la reidentificación: **\[por definir\]**.
- Los resultados se agrupan por área, departamento y los demás campos de la carga.

### 7.5 Evaluación práctica del líder (opcional, último paso)

- Se configura **por impacto** (requiere certificación del líder: sí o no). Si no aplica, no cuenta como pendiente en el dashboard ni en el índice de preparación.
- Instrumento: **lista de observación** definida por el equipo de formación, con resultado cumple o no cumple por criterio y observaciones.
- La plataforma arma la lista del equipo del líder con el campo **supervisor** de la carga. **\[propuesta\]** Solo llegan a ella quienes aprobaron el cuestionario.
- Flujo: el líder ingresa los resultados en un **formulario web** → la plataforma genera un **PDF prellenado** con el equipo, los criterios, los resultados y el bloque de firma → el líder **lo imprime, lo firma y lo carga** como evidencia asociada al impacto.
- Resultado por persona: **certificado** o **en refuerzo** (el refuerzo activa al guía). Estados de certificación: pendiente · aplicado · certificado · en refuerzo.
- El resumen firmado (evaluados, certificados y en refuerzo) alimenta el criterio de cierre y el índice de preparación.

---

## 8. Dashboard

Se alimenta en vivo de los estados de la Matriz, Ruta, Bitácora y Formularios.

**Indicadores en cuatro niveles** (ejecución, respuesta, adopción y resultados), por frente:

- **Impactos:** porcentaje con plan y responsable · críticos abiertos frente a mitigados · impactos no anticipados.
- **Comunicación:** mensajes a tiempo frente a planificados · cobertura de grupos · eventos detectados por iniciativa propia.
- **Movilización:** participación · comprensión del cambio · tickets por tipo, tiempos y recurrencia.
- **Formación:** impactos con formación asignada · personas formadas antes de la salida · verificación de competencia.
- **Transversales:** usuarios activos y adopción sostenida a 30, 60 y 90 días · **índice de preparación por grupo** · comparación del diagnóstico antes y después.

**Cada indicador debe tener** fórmula, escala o porcentaje de cumplimiento con semáforo, fuente del dato, frecuencia y responsable. Los umbrales **\[por definir\]**. Los datos que no salen de la plataforma (usuarios activos del sistema nuevo, beneficios del proyecto) se cargan manualmente **\[por definir\]**.

**Alertas:** impactos P1 sin criterio de cierre · riesgos de severidad Extrema · grupos por debajo del umbral de preparación.

**Vistas:** por tiempo del marco y por grupo, con el tamaño mínimo de grupo aplicado.

---

## 9. Guía de campo y Administración

**Guía de campo:** material de la metodología (frentes, tiempos, regla de decisión), plantillas, definiciones de las escalas y documentos del cliente, con **ayuda contextual**: enlaces directos desde cada campo al material correspondiente. Gestionable por la consultora.

**Administración:** crear clientes y sus espacios · invitar usuarios y asignar roles · configurar los catálogos del cliente · cargar listados de personas · activar o desactivar módulos.

---

## 10. Requisitos no funcionales

- **Seguridad:** contraseñas con hash, HTTPS en producción, claves fuera de Git (archivo `.env` ignorado), roles verificados en cada acción, aislamiento de datos entre clientes.
- **Privacidad:** confidencialidad según 7.4, política de privacidad y plazos de conservación de datos **\[por definir\]**, cumpliendo la normativa de protección de datos aplicable a cada cliente.
- **Respaldos:** copias automáticas de la base de datos.
- **Pruebas automáticas** de los cálculos (riesgo y prioridad) y de los permisos.
- **Uso desde el celular** para capitanes y líderes.
- **Despliegue:** local con Docker Compose; después, un servidor (VPS) con los mismos contenedores y proxy con HTTPS **\[por definir\]**.

---

## 11. Fuera del alcance de la primera versión

- Módulo de envío de correos masivos (después de exportar el archivo de enlaces).
- Constructor avanzado de exámenes: bancos de preguntas, aleatorización, límites de tiempo, certificados.
- Integración con el sistema de mesa de ayuda del cliente.
- Consultor virtual (versión 2).
- Inicio de sesión único (SSO).

---

## 12. Orden de construcción sugerido **\[propuesta\]**

1. Base: acceso, espacios por cliente y roles.
2. Catálogos del sistema y del cliente, y reglas de cálculo con sus pruebas.
3. **Matriz de Impactos.**
4. Ruta.
5. Bitácora.
6. Formularios y verificación de competencias.
7. Dashboard.

Cada paso se construye por incrementos pequeños, se prueba y se guarda en Git. Se sugiere cargar datos de ejemplo (por ejemplo, la fila de cuentas por cobrar) para validar el dashboard.

---

## 13. Pendientes de la Parte B

1. Lista final de campos obligatorios y catálogos del sistema (tipos de impacto y origen).
2. Escalas de resistencia esperada y preparación del grupo.
3. Umbrales de los indicadores y del índice de preparación.
4. Nota mínima de aprobación, puntaje de la opción múltiple, y vigencia e intentos de los enlaces.
5. Tamaño mínimo de grupo en las vistas agregadas.
6. Permisos finales por rol y detalle visible para cada uno.
7. Carga manual de los indicadores externos.
8. Conservación de datos y política de privacidad.
9. Hosting y despliegue.