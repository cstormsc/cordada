# QA de optimización y seguridad — Cordada

**Fecha:** 11/11/2026 · **Rama:** `feature/ascenso-fase2` (df7cffb) · **Alcance:** todo lo agregado desde la auditoría del 09/10 (sobre todo el módulo Aprendizaje y el túnel de Cloudflare), más mediciones de velocidad en los clientes demo.
**Método:** revisión de código, `check --deploy`, suite de pruebas, pruebas en vivo sobre la instancia local y mediciones de consultas y tiempo por página. La prueba de escala creó 1.000 personas dentro de una transacción que se deshizo: no quedó ningún dato.

## Resumen

El código nuevo está bien protegido: no encontré forma de ver datos de otro cliente ni de saltarse un rol. Los problemas serios vienen de **cómo se comparte el sitio por el túnel**, no del código de los módulos.

| # | Severidad | Hallazgo |
|---|---|---|
| N1 | **Crítica con el túnel abierto** | La clave secreta es la de ejemplo y el repositorio de GitHub es público: cualquiera puede fabricar enlaces personales |
| N2 | **Alta con el túnel abierto** | El modo de depuración está siempre activo: las páginas de error muestran configuración y código a cualquier visitante |
| N3 | Media | Por el túnel todos los visitantes comparten una dirección: 20 contraseñas erróneas de cualquiera bloquean el ingreso de todos |
| N4 | Baja (latente) | `/admin/login/` no tiene el límite de intentos |
| N5 | Baja | Aprendizaje no aplica tamaño mínimo de grupo: equipos de 1 o 2 personas revelan quién completó |
| N6 | Info | Imágenes de lecciones validadas solo por extensión; archivos reemplazados quedan en disco |
| N7 | Info | Respaldos solo en este Mac y sin cifrar; la app no vuelve sola cuando Docker se reinicia |
| O1 | **Alta a escala** | Aprendizaje hace una o dos consultas por persona: con 1.000 personas, más de 1.000 consultas y 2–3 s por página |
| O2 | Media | Dashboard (58 consultas) e inicio (48): el inicio calcula todo el dashboard para mostrar un número |
| O3 | Baja | Detalle de impacto: 28 consultas |
| O4 | Al desplegar | Servidor de desarrollo, sin compresión ni caché de archivos estáticos |

No se pudo ejecutar el escaneo de vulnerabilidades conocidas en dependencias (`pip-audit`): el entorno bloqueó el comando.

---

## Seguridad

### N1 — Clave secreta pública (Crítica mientras haya túnel)

`.env` usa `DJANGO_SECRET_KEY=change-me-local-only`, el mismo valor de `.env.example`, y el repositorio `cstormsc/cordada` es **público**. Esa clave firma los enlaces personales de cursos (`/a/<token>/`) y de cuestionarios (`/f/<token>/`).

**Probado:** firmé un enlace de curso usando solo la clave pública de ejemplo y el sitio lo aceptó (respuesta 200). Con el túnel abierto, quien conozca la dirección puede abrir el curso o el cuestionario de cualquier persona, ver su nombre, marcar avance y responder evaluaciones en su nombre.

No permite entrar como usuario del equipo: las sesiones se guardan en la base de datos y las invitaciones usan un token aleatorio propio.

**Arreglo:** generar una clave nueva en `.env`. Efectos: todos tienen que volver a iniciar sesión y los enlaces personales ya exportados dejan de servir (hay que exportarlos de nuevo). Las invitaciones pendientes siguen funcionando.

### N2 — Depuración siempre activa (Alta mientras haya túnel)

`config/settings/local.py` fija `DEBUG = True` sin mirar `DJANGO_DEBUG`. Por el túnel, cualquier dirección inexistente muestra el mapa completo de URLs, y cualquier error muestra código, variables y configuración. Verificado en `/no-existe-xyz/`.

**Arreglo:** que `local.py` respete `DJANGO_DEBUG` y apagarlo al compartir. Con la depuración apagada el servidor de desarrollo deja de servir CSS y JS, así que el arreglo va junto con O4 (WhiteNoise + gunicorn): un "modo compartir".

### N3 — Bloqueo de ingreso para todos (Media)

Detrás del túnel, Cordada ve a todos los visitantes con la misma dirección (`172.18.0.1`). El límite de 20 fallos por dirección se convierte en un límite global: 20 contraseñas erróneas de cualquier persona en Internet bloquean el ingreso de todos por 15 minutos, y se puede repetir. Además, 5 fallos con el correo de alguien bloquean a esa persona (pasó el 04/11).

**Arreglo:** leer la dirección real del visitante (`CF-Connecting-IP` o `X-Forwarded-For`) solo cuando `DJANGO_BEHIND_HTTPS_PROXY` está activo.

### N4 — `/admin/login/` sin límite de intentos (Baja, latente)

8 intentos seguidos sin bloqueo: el límite solo cubre `/entrar/`. Hoy no hay ninguna cuenta con acceso al admin de Django, así que no hay nada que adivinar. Se vuelve real en cuanto se cree un superusuario.

**Arreglo:** quitar `/admin/` (nadie lo usa) o hacer que use el mismo formulario con límite.

### N5 — Equipos pequeños en Aprendizaje (Baja)

Formularios oculta los grupos con menos de 5 respuestas. Aprendizaje no:

- **Página Personas del curso:** la tabla de equipos muestra cuántos iniciaron y completaron también en equipos de 1 o 2 personas, a roles sin permiso de detalle individual (Administración).
- **Portada del participante:** la "cuerda" muestra cuántos compañeros de su equipo completaron, sin nombres. En un equipo de 2 eso es saber si el otro completó.

Es avance de formación, no notas, así que puede ser una decisión aceptable. Conviene decidirlo explícitamente.

### N6 — Archivos (Info)

- Las imágenes de bloques e ítems se validan solo por extensión; el encabezado sí se abre con Pillow. La cabecera `nosniff` impide que el navegador las interprete como otra cosa.
- Al reemplazar o borrar un archivo (en cualquier módulo), el anterior queda en disco para siempre.

### N7 — Operación (Info)

- Los respaldos están completos y con contenido, pero viven solo en este Mac, sin cifrar. No hubo respaldos entre el 06/11 y el 11/11 porque Docker estuvo apagado.
- Solo el servicio de respaldo se reinicia solo. Cuando Docker Desktop se reinicia, la app queda apagada hasta correr `make up` (pasó el 06/11 y hoy).
- Cookies sin marca `Secure` y sin HSTS: sigue pendiente del S1 de la auditoría anterior.

### Controles verificados (sin hallazgos)

- **Pruebas:** 573 pasan; migraciones al día.
- **Enlaces de curso:** firma alterada, versión incorrecta y archivo de otro curso dan 404; `marcar` no acepta GET; los POST públicos sin token CSRF dan 403; respuestas con `no-store`, `X-Frame-Options: DENY` y `Referrer-Policy: same-origin` (el token no se filtra a YouTube ni a enlaces externos).
- **Permisos:** todas las vistas de Aprendizaje revisan rol y módulo; los archivos se buscan por su curso dentro del cliente.
- **XSS:** plantillas nuevas con escape automático; los juegos reciben datos por `json_script`; el JS no usa `innerHTML` con datos de usuario; los videos solo se incrustan desde YouTube y Vimeo.
- **Repositorio:** sin `.env`, respaldos, archivos subidos ni contraseñas reales en git.

---

## Optimización

Mediciones con los datos demo (segunda carga, servidor de desarrollo):

| Página | Consultas | Tiempo |
|---|---|---|
| Inicio del cliente | 48 | 101 ms |
| Dashboard | 58 | 168 ms |
| Detalle de impacto | 28 | 72 ms |
| Matriz (tablero y lista) | 7 | 34 ms |
| Ruta | 14 | 62 ms |
| Bitácora | 10 | 35 ms |
| Formularios, resultados, personas | 6–11 | 18–34 ms |
| Aprendizaje (lista, curso, vista previa) | 6–15 | 16–34 ms |

Con el tamaño actual todo responde rápido. Lo que no escala:

### O1 — Aprendizaje: consultas por persona (Alta a escala)

Con 1.000 personas inscritas (prueba deshecha al terminar):

| Página | Consultas | Tiempo |
|---|---|---|
| Personas del curso, sin evaluación | 2.025 | 3,2 s |
| Personas del curso, con evaluación | 1.013 | 2,0 s |
| Portada del participante, con evaluación | 1.011 | 2,1 s |
| Portada del participante, sin evaluación | 10 | 0,2 s |
| Exportar enlaces (CSV) | 6 | 0,25 s |

La causa es `avance.sincronizar()`, que se llama persona por persona en `views.inscripciones` y en `avance.cordada`. La portada del participante es la más delicada: la abre cada persona, y cada visita recalcula a todo su equipo. Mil personas entrando el mismo día serían un millón de consultas.

**Arreglo:** calcular el avance de todos en dos o tres consultas (aprobadas por persona, lecciones vistas por inscripción), y en la portada contar al equipo con una sola consulta filtrada por equipo.

### O2 — Dashboard e inicio (Media)

El dashboard hace 58 consultas, 7 de ellas repetidas sobre `ValorManual`. El inicio hace 48 porque llama a `ind.tiles()` completo solo para mostrar el avance general. No crece con los datos tanto como O1, pero es la primera página que ve todo el mundo.

**Arreglo:** cargar `ValorManual` una vez por petición y dar al inicio una función que calcule solo el indicador general, o guardar el resultado en caché unos minutos.

### O3 — Detalle de impacto (Baja)

28 consultas, 4 repetidas sobre `Impacto` (dependencias). Se resuelve con `select_related`/`prefetch_related`.

### O4 — Para publicar (junto con S1 de la auditoría anterior)

- `runserver` atiende de a una petición por vez y no es para uso real: gunicorn.
- Sin compresión ni caché larga de CSS y JS; ECharts pesa 1 MB sin comprimir: WhiteNoise.
- Actualizaciones menores disponibles: psycopg 3.3.8, asgiref 3.13, sqlparse 0.6.1. Django 5.2.18 sigue en la línea LTS.

---

## Orden sugerido

1. **Antes de volver a abrir el túnel:** N1 (clave nueva) y N2 + N3 ("modo compartir": depuración apagada, WhiteNoise, dirección real del visitante).
2. **Antes de un curso con cientos de personas:** O1.
3. **Cuando haya tiempo:** O2, N4, N5 (decisión), O3.
4. **Al desplegar:** O4, N7 y lo pendiente de S1/S8.

---

## Estado de los arreglos (11/11/2026)

- **N1 — resuelto.** `.env` tiene una clave aleatoria nueva; un enlace fabricado con la clave de ejemplo ahora da 404. La app se niega a arrancar con la clave de ejemplo si la depuración está apagada o hay túnel, y `make` genera una clave propia al crear `.env`.
- **N2 — resuelto.** `local.py` respeta `DJANGO_DEBUG` y `.env` lo tiene en `false`: una dirección inexistente muestra la página "No encontrado" normal y los errores una página simple (`templates/500.html`). WhiteNoise sirve CSS y JS con la depuración apagada.
- **N3 — resuelto.** Con `DJANGO_BEHIND_HTTPS_PROXY=true` el límite de intentos usa la dirección que informa el túnel (la última de `X-Forwarded-For`), así que cada visitante se cuenta aparte. Dos pruebas nuevas.
- **Prueba inestable corregida:** `test_lessons_in_order_until_the_summit` fallaba a veces porque firmaba un enlace nuevo en cada llamada.
- **Pendientes:** N4–N7 y O1–O4.
