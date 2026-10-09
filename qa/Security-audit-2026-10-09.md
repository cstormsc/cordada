# Auditoría de seguridad — Cordada

**Fecha:** 09/10/2026 · **Alcance:** código en `main` (más los 4 arreglos del QA, aún sin commit) y la instancia local con el tenant PrecisionQA Group.
**Método:** revisión de código (configuración, permisos, aislamiento de clientes, cargas y descargas, exportaciones, plantillas y JS), `manage.py check --deploy`, revisión del historial de git y pruebas en vivo con las cuentas QA. Es una revisión de aplicación, no una prueba de penetración de infraestructura.

## Resumen

No encontré vulnerabilidades explotables hoy que permitan a un usuario ver o cambiar datos de otro cliente ni saltarse su rol. Los hallazgos son:

- **Privacidad:** una fuga por inferencia en los resultados de Formularios.
- **Despliegue:** brechas de configuración que hay que cerrar **antes de publicar el sitio**.
- **Riesgos menores:** algunos, latentes.

| # | Severidad | Hallazgo |
|---|---|---|
| S1 | **Alta, al desplegar** | Configuración de producción sin endurecer: clave secreta de ejemplo, DEBUG, cookies sin HTTPS, servidor de desarrollo |
| S2 | **Media** | El tamaño mínimo de grupo se puede saltar restando agrupaciones — **resuelto** |
| S3 | **Media** | Sin límite de intentos de inicio de sesión ni bloqueo — **resuelto** |
| S4 | Baja | XSS almacenado latente: texto de ayuda editable renderizado con `\|safe` — **resuelto** |
| S5 | Baja | Grupos ocultos igual revelan cuántos respondieron (grupos de 1 persona) — **resuelto** |
| S6 | Baja | Protección contra inyección de fórmulas en Excel/CSV incompleta — **resuelto** |
| S7 | Baja | Posible carrera en el límite de intentos del cuestionario — **no aplica** (ya protegido) |
| S8 | Info | Sin recuperación de contraseña; `/admin/` expuesto; sesiones de 2 semanas sin 2FA |

---

## Hallazgos

### S1 — Configuración de producción (Alta al desplegar; hoy sin impacto, el sitio solo escucha en 127.0.0.1)

`manage.py check --deploy` reporta 6 avisos (W004, W008, W009, W012, W016, W018):

- **Clave secreta:** `.env` usa la de ejemplo (`change-me-local-only`). No es solo un aviso. Esa clave **firma los enlaces personales de los cuestionarios** (`/f/<token>/`) y las sesiones. Con la clave conocida, cualquiera podría fabricar enlaces y responder por otra persona o ver su resultado.
- **DEBUG:** `DJANGO_DEBUG=true` en `.env.example`. Con DEBUG en producción, cualquier error muestra configuración y código.
- **HTTPS:** no se definen `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` ni `SECURE_PROXY_SSL_HEADER`.
- **Servidor:** el `Dockerfile` arranca con `runserver`, el servidor de desarrollo de Django, que no es apto para producción.

**Recomendación:** antes de publicar, crear `config/settings/production.py` con lo anterior y usar gunicorn. Generar la clave secreta por entorno y nunca reutilizar la de ejemplo. Cambiar la clave invalida los enlaces de cuestionarios ya enviados.

### S2 — Inferencia de resultados en grupos pequeños (Media)

`/formularios/<n>/resultados/` oculta cada grupo con menos de 5 respuestas, también con `?por=` inválido. Pero permite agrupar el mismo cuestionario por grupo, departamento, oficina, sucursal o cargo, y **restar dos agrupaciones que se solapan reconstruye el grupo oculto**.

Ejemplo verificado en vivo, con el rol Guía (que no ve detalle individual) en CUE-001:
- **Oficina Santiago:** 8 respondieron, 7 aprobaron, promedio 89,4.
- **Grupo Operaciones Planta** (todos en Santiago): 6 respondieron, 5 aprobaron, promedio 85,8.
- **Diferencia:** Contabilidad (oculto, "menos de 5"): **2 respondieron, 2 aprobaron, promedio ≈ 100**. Con el agrupamiento por cargo se llega hasta personas concretas.

Esto contradice la promesa de confidencialidad del §7.4 y del texto que ven quienes responden.

**Opciones:**
- Supresión complementaria: si se oculta un grupo, ocultar también otro de la misma dimensión, para que la resta no cuadre.
- Permitir solo una dimensión por cuestionario.
- Exigir el mínimo también a la diferencia entre cada par de agrupaciones que se solapan.

La más simple de implementar es dejar fija la dimensión "grupo impactado" para quien no tiene VIEW_INDIVIDUAL.

### S3 — Sin límite de intentos de login (Media)

12 contraseñas erróneas seguidas no producen bloqueo, demora ni CAPTCHA. Lo mitigan los validadores de contraseña de Django (largo mínimo y contraseñas comunes) y el mensaje genérico que no revela si el correo existe.

**Recomendación:** `django-axes`, o un limitador por IP y por cuenta en `/entrar/`, antes de exponer el sitio.

### S4 — XSS almacenado latente vía texto de ayuda (Baja)

El renderer de formularios (`apps/guia/templates/guia/field.html`) muestra `{{ field.help_text|safe }}`. En el formulario de impacto, si un campo de escala no tiene ayuda propia, se usa `Scale.help_text`, que el administrador de plataforma edita en `/plataforma/escalas/`.

**Probado:** guardé `<img onerror=…>` en la escala Severidad. **No llega al formulario hoy**, porque magnitud, probabilidad y severidad tienen ayuda propia en el modelo. Bastaría quitar esa ayuda del modelo o agregar una escala nueva para que el HTML de un administrador de plataforma corra en las páginas de todos los clientes. La escala quedó restaurada.

**Recomendación:** escapar `help_text` en `field.html` (los textos de ayuda del código no usan HTML), o asignar `escape(scale.help_text)`.

### S5 — Participación visible en grupos ocultos (Baja)

Las filas ocultas siguen mostrando "con enlace" y "respondieron". Agrupando por cargo, por ejemplo "Jefa de turno | 1 | 1", se ve que la única persona con ese cargo respondió. No revela el puntaje, pero sí la participación individual.

**Recomendación:** en filas bajo el mínimo, mostrar solo "menos de 5", sin conteos.

### S6 — Inyección de fórmulas en exportaciones (Baja)

`safe_cell()` (`apps/matriz/export.py`) antepone `'` a valores que empiezan con `=`, `+`, `-` o `@`, y se usa en todas las exportaciones (Matriz, fotos, Ruta, Bitácora, enlaces CSV y Excel). OWASP también incluye el tabulador y el retorno de carro iniciales (`\t=…`).

**Recomendación:** agregar `"\t"` y `"\r"` a la lista.

### S7 — Carrera en intentos del cuestionario (Baja, no verificada)

`responder()` cuenta los intentos usados y luego crea la respuesta sin bloqueo. Dos envíos simultáneos con el mismo enlace podrían superar el límite de intentos.

**Recomendación:** `select_for_update()` sobre el `Enlace` al registrar la respuesta.

### S8 — Observaciones (Info)

- **No hay "olvidé mi contraseña":** quien la olvida depende del Django admin. Es más un riesgo de operación que de seguridad.
- **`/admin/` de Django** está activo (solo superusuarios). En producción conviene restringirlo o moverlo.
- **Sesiones:** duran 2 semanas, sin cierre por inactividad y sin 2FA. Para cuentas de Administración y de plataforma, valorar 2FA.

---

## Controles verificados (sin hallazgos)

**Permisos por rol**
- 264 combinaciones rol × página coinciden con la tabla del §2.
- Acciones POST probadas con roles sin permiso: 403 o 404.
- Un proponente no puede inyectar campos de evaluación ni cambiar el estado.

**Aislamiento de clientes**
- Todos los modelos de cliente usan el manager con alcance de cliente.
- `unscoped` aparece solo en placeholders vacíos de formularios, en la numeración y en la lectura del enlace firmado, que después fija el cliente correcto.
- Los catálogos de otro cliente se rechazan en los formularios (probado en las invitaciones nuevas).
- Un miembro que abre otro cliente recibe 404. La suite incluye pruebas cruzadas entre clientes.

**Descargas**
- Adjuntos, evidencias, actas, plantillas y documentos se buscan por su registro padre (impacto, actividad, lista) ya autorizado, y se sirven como descarga.
- `/media/` no es público y un anónimo es redirigido al login.

**Cargas**
- Lista blanca de extensiones (pdf, docx, xlsx, pptx, csv, txt, png, jpg); svg, html, js y exe rechazados.
- Límite de 10 MB; archivos bajo `clientes/<id>/`; cabecera `nosniff`.

**XSS**
- Escape automático en todas las plantillas; los únicos `|safe` son el de S4 y `format_html` en dos templatetags (seguro).
- El JS usa `textContent`. Los atributos de Alpine reciben JSON escapado. htmx solo intercambia HTML del servidor.

**CSRF y clickjacking**
- Middleware activo; POST sin token rechazado (internos y públicos).
- `X-Frame-Options: DENY`; `Referrer-Policy: same-origin`.

**SQL**
- Sin SQL crudo, `.extra()` ni `RawSQL`; solo el `SELECT 1` del health check.

**Redirecciones**
- El `next` del login usa la validación de host de Django. No hay otros redirects con parámetros del usuario.

**Invitaciones**
- Token de 32 bytes del que solo se guarda el hash SHA-256; vence en 7 días; un solo uso; se puede anular.
- Si la cuenta ya existe, hay que haber iniciado sesión con esa misma cuenta.

**Enlaces de cuestionario**
- Firmados con sal propia y marca de tiempo; vencen; una firma alterada da 404.
- Se revocan por versión. Una persona inactiva o un cuestionario cerrado no se pueden responder.
- Las opciones ajenas a la pregunta se descartan.

**Privacidad de resultados**
- Dashboard e impacto respetan el mínimo de 5 al filtrar por grupo.
- El detalle individual solo lo ve el Equipo de cambio.

**Secretos e infraestructura**
- `.env`, `backups/` y `media/` nunca se subieron a git; el historial no tiene credenciales reales (solo contraseñas de prueba en los tests).
- Postgres, Mailpit y la app escuchan solo en 127.0.0.1.

**Dependencias**
- Django 5.2.18 (último parche de la LTS 5.2), Pillow 12.3.0 y WeasyPrint 70.0 (últimas).

---

## Estado de los arreglos (09/10/2026)

- **S2:** supresión complementaria (`formularios.results.suppressed`). Lo oculto suma 0 o al menos el mínimo; si no, también se oculta el grupo visible más pequeño. Se aplica en Resultados, el detalle del impacto, la verificación y certificación del Dashboard y el índice de preparación. Quien no ve el detalle individual ya no puede reagrupar (`?por=` se ignora). **Riesgo residual:** comparar vistas con distintos filtros de tiempo, o un cuestionario contra el total del Dashboard cuando hay varios, todavía puede permitir deducciones aproximadas en casos límite.
- **S3:** `apps/core/login_throttle.py`. 5 fallos por cuenta o 20 por dirección IP en 15 minutos bloquean 15 minutos, sin probar la contraseña. Los contadores van en una caché en base de datos (`createcachetable`, ya en el entrypoint), compartida entre procesos. Detrás de un proxy hay que tomar la IP real (`X-Forwarded-For`) al desplegar.
- **S4:** `field.html` ya no usa `|safe`. También corrige que `<identificador>` desaparecía en algunos textos de ayuda.
- **S5:** las filas ocultas no muestran cuántos respondieron; los mensajes del Dashboard tampoco.
- **S6:** `safe_cell()` también neutraliza el tabulador y el retorno de carro iniciales.
- **S7:** verificado: la restricción única (enlace, intento) más el manejo de `IntegrityError` ya impiden sumar un intento con envíos simultáneos.
- **S1 y S8:** quedan para el trabajo de despliegue.
