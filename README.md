# progress-tracking-backend-service · Progreso y seguimiento

Este es el microservicio de **progreso y seguimiento** de Code4All. Es lo que
hay detrás del panel de la **dirección** (en la app, «la coordinación»): las
herramientas con las que el director vigila que el curso esté bien hecho y que
los docentes estén haciendo su trabajo.

Responde tres preguntas, y conviene no mezclarlas:

1. **¿Qué ha hecho cada docente?** Qué secciones del curso tocó y cuándo. Esto
   no lo apunta nadie a mano: sale de lo que ya se guarda cuando un docente
   edita contenido.
2. **¿El contenido está bien?** El director revisa cada sección de cada curso y
   la deja **aprobada** u **observada**, con un comentario.
3. **¿Cómo lo está haciendo el docente?** Una valoración del 1 al 5 con
   comentario, que se guarda con su fecha para poder ver si mejora.

Además conserva las rutas de **rendimiento de los estudiantes por lección** que
venían del monolito (ver la sección 4).

> El avance de cada estudiante (qué actividades completó, qué respondió en los
> quices) **no** está aquí: lo lleva
> [assessment-backend-service](https://github.com/CODE4ALL-UV/assessment-backend-service).

## Quién puede usarlo

**Solo el director.** Todas las rutas piden el token en la cabecera
`Authorization: Bearer <token>`, y un docente o un estudiante recibe 403.

El rol se comprueba **contra la base de datos**, no contra lo que dice el
token. Así, a alguien que deja de ser director se le corta el acceso en el
momento, sin esperar a que caduque su sesión.

| Código | Cuándo |
|---|---|
| 401 | No llegó el token, está vencido o no identifica a nadie. |
| 403 | La persona no es director. |

## 1. Seguimiento de los docentes

### `GET /api/oversight/teachers`

La lista de todos los docentes, ordenada por nombre, incluso los que todavía no
han editado nada. De cada uno dice:

| Campo | Qué es |
|---|---|
| `edits` | Cuántas secciones o módulos tienen a este docente como último editor. |
| `last_edit` | Fecha de su última edición. |
| `courses` | Cuántos cursos propios tiene (sin contar el Curso general). |
| `reviews`, `last_score`, `avg_score` | Cuántas valoraciones tiene, la nota de la última y el promedio. |

### `GET /api/oversight/teachers/{user_id}/activity`

El detalle de lo que editó un docente, de lo más reciente a lo más antiguo.
Por cada sección o módulo dice en qué curso fue, cuándo, cómo quedó la
revisión del director (`review_status`, `review_comment`) y si esa revisión
**quedó vieja** (`review_outdated`), es decir, si el docente volvió a editar
después de que el director la revisara.

### De dónde salen las ediciones

Cuando un docente edita una sección, el servicio de contenidos
([course-content](https://github.com/CODE4ALL-UV/course-content-backend-service))
guarda la versión editada en la tabla `CourseOverride`, con el **correo** de
quien la editó (`updated_by`) y la fecha (`updated_at`). Este servicio solo lee
esa tabla. Por eso:

- `edits` cuenta las secciones cuyo **último** editor es ese docente, no cuántas
  veces guardó. Si otra persona edita después la misma sección, deja de
  contarle.
- La relación es por correo. Si un docente cambia de correo, su historial
  anterior deja de aparecerle.

## 2. Revisión del contenido

### `PUT /api/oversight/content/{section_id}`

El director aprueba u observa una sección de un curso. `section_id` es el
identificador de la sección dentro del curso, por ejemplo `m1-s2` (módulo 1,
sección 2).

```json
{
  "section_id": "m1-s2",
  "status": "observado",
  "comment": "El ejemplo del bucle for tiene un error en la línea 3.",
  "course_id": 7
}
```

- `status` solo puede ser `aprobado` u `observado`.
- Si es `observado`, el comentario es **obligatorio**: hay que explicar qué
  está mal. En `aprobado` es opcional.
- `course_id` dice de qué curso es la sección. Si no se manda, la revisión va
  al **Curso general**.
- La revisión es **por sección y por curso**: aprobar `m1-s2` en el curso de
  una docente no aprueba la misma sección en el curso de otro.
- Hay un solo estado vigente por sección y curso. Si el director la vuelve a
  revisar, se sobrescribe la anterior.

| Código | Cuándo |
|---|---|
| 400 | El estado no es válido, o es `observado` sin comentario. |
| 404 | El curso no existe. |

### `GET /api/oversight/content`

Todas las revisiones de contenido, cada una con su estado, su comentario, la
fecha y el campo `outdated`, que vale `true` si el docente editó la sección
después de la revisión.

### `GET /api/oversight/courses`

Todos los cursos, primero el Curso general y después los de los docentes por
fecha de creación. De cada uno dice quién es el docente, cuántos estudiantes
tiene y qué secciones se han editado y cuándo. En el Curso general, el número
de estudiantes es el de **todos** los estudiantes, porque todos lo ven sin
inscribirse.

## 3. Valoraciones de los docentes

### `POST /api/oversight/reviews`

```json
{ "docente_id": 12, "score": 4, "comment": "Buen material, falta un ejemplo más en funciones." }
```

- `score` va del 1 al 5.
- El comentario es **obligatorio**: la nota sola no explica nada.
- Cada valoración se **añade** al historial, no reemplaza a la anterior. Así se
  ve la evolución del docente.

| Código | Cuándo |
|---|---|
| 400 | El comentario está vacío. |
| 404 | La persona no existe o no es docente. |
| 422 | La nota está fuera del 1 al 5. |

### `GET /api/oversight/reviews/{user_id}`

El historial de valoraciones de un docente, de la más reciente a la más
antigua.

## 4. Rendimiento por lección (`/api/director`)

Son las rutas que tenía el monolito para registrar y resumir el rendimiento de
los estudiantes en cada lección. Se guardan en la tabla `student_performance`,
con un puntaje y tres contadores (`failed`, `good`, `excellent`).

| Ruta | Qué hace |
|---|---|
| `GET /api/director/students` | La lista de estudiantes (id, nombre, correo, foto). |
| `GET /api/director/performances` | Todos los registros, del más reciente al más antiguo. |
| `GET /api/director/performances/aggregate` | Las sumas por lección. |
| `GET /api/director/performances/average` | Los promedios por lección, con cuántos registros y cuántos estudiantes distintos hay. |
| `POST /api/director/performances` | Crea un registro (`lesson_name` obligatorio; `usuario_id`, `score`, `failed`, `good` y `excellent` opcionales). Responde 201. |

Hoy la app no las usa: el avance real de los estudiantes se calcula en
assessment. Se mantienen porque el gateway debe exponer las mismas rutas que el
monolito (`tests/test_route_parity.py` en el repo `Back-end`).

## Dónde lo usa la app

En el [Front-end](https://github.com/CODE4ALL-UV/Front-end),
`lib/data/course/director_oversight_store.dart` llama a `teachers`, `content` y
`courses` al abrir el panel, y a `activity`, `reviews` y `content/{id}` cuando
el director entra a un docente, lo valora o revisa una sección. Si
`/api/oversight/courses` responde 404, la app entiende que habla con el
servidor anterior y sigue con un solo curso.

## Tablas que usa

Las tablas están definidas en
[neon-storage](https://github.com/CODE4ALL-UV/neon-storage-backend-service).

| Tabla | Qué hace con ella |
|---|---|
| `TeacherReview` | Escribe y lee las valoraciones de los docentes. |
| `ContentReview` | Escribe y lee la revisión de cada sección por curso (una fila por curso y sección). |
| `student_performance` | Escribe y lee el rendimiento por lección. |
| `Usuario` | Lee: comprobar que quien llama es director, listar docentes y estudiantes. |
| `CourseOverride` | Lee: el rastro de lo que editó cada docente. La escribe course-content. |
| `Course`, `CourseEnrollment` | Lee: los cursos y cuántos inscritos tiene cada uno. Si el Curso general no existe todavía, lo crea. |

## Cómo lo monta el gateway

Todos los servicios de Code4All siguen el mismo contrato:
`progress_tracking_service/routes.py` tiene una función `register(app)` que
añade las rutas de este servicio a una aplicación de FastAPI. El
[gateway](https://github.com/CODE4ALL-UV/Back-end) trae este repositorio como
submódulo en `services/` y llama a esa función al arrancar.
`progress_tracking_service/main.py` hace lo mismo para correrlo solo.

Depende de otros dos repositorios: **neon-storage** para la base de datos y
**user-management** para leer el token.

## Estructura

```
progress_tracking_service/
├── routes.py                          register(app): lo único que llama el gateway
├── main.py                            arranque independiente (lee el .env y prepara la base)
├── infrastructure/
│   └── performance_repository.py      consultas de student_performance
└── presentation/api/
    ├── director_routes.py             /api/director/*  (rendimiento por lección)
    └── director_oversight_routes.py   /api/oversight/* (docentes, revisiones, valoraciones, cursos)
tests/
├── conftest.py
├── test_progress_routes.py
└── test_course_oversight.py
```

## Variables de entorno

| Variable | Para qué | ¿Obligatoria? |
|---|---|---|
| `DATABASE_URL` | La cadena de conexión de Neon. Mejor la del *pooler* (el host lleva `-pooler`). | Sí |
| `SECRET_KEY` | Para comprobar los tokens. Tiene que ser **la misma** que usa user-management para firmarlos. | Sí |
| `ALGORITHM` | Algoritmo del token. Por defecto `HS256`. | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración del token. Aquí solo se usa en las pruebas. | No |

Están en `.env.example`.

## Correrlo

Lo normal es correrlo dentro del gateway (repo `Back-end`), que monta todos
los servicios juntos. Para correrlo solo hacen falta `neon-storage` y
`user-management` clonados al lado:

```powershell
$env:PYTHONPATH = "..\neon-storage-backend-service;..\user-management-backend-service"
pip install -r requirements.txt -r ..\neon-storage-backend-service\requirements.txt -r ..\user-management-backend-service\requirements.txt
copy .env.example .env
uvicorn progress_tracking_service.main:app --reload
```

## Pruebas

```powershell
pytest tests
```

No tocan Neon: `conftest.py` fuerza una base SQLite temporal. Buscan
`neon-storage` y `user-management` en los repos hermanos, así que funcionan
igual con los repos clonados uno al lado del otro que dentro de `services/`
del gateway.

- `test_progress_routes.py`: el director lista estudiantes y registra
  rendimiento; un docente no entra al panel; una valoración sin comentario se
  rechaza.
- `test_course_oversight.py`: aprobar la sección de una docente no aprueba la
  de otro; la coordinación ve cada curso con su docente, sus inscritos y sus
  secciones editadas; solo la dirección puede listar los cursos.

En GitHub, cada push o pull request a `main` corre las pruebas con cobertura y
la sube a Codacy (`.github/workflows/codacy-coverage.yml`).

## Cosas a tener en cuenta

- `GET /api/oversight/courses` y `PUT /api/oversight/content/...` sin
  `course_id` crean el Curso general si todavía no existe.
- La revisión de contenido no guarda historial: solo el último estado.
- Los listados no tienen paginación.
- Las ediciones de módulos cuentan en `edits` y en la actividad del docente,
  pero la revisión de contenido y la lista de cursos solo miran secciones.
- Los dos archivos de rutas comprueban el rol de director cada uno a su manera
  (con mensajes distintos). Si se toca uno, conviene revisar el otro.

## Los repositorios de Code4All

| Parte | Repositorio |
|---|---|
| App (Flutter) | [Front-end](https://github.com/CODE4ALL-UV/Front-end) |
| API Gateway | [Back-end](https://github.com/CODE4ALL-UV/Back-end) |
| Gestión de usuarios | [user-management-backend-service](https://github.com/CODE4ALL-UV/user-management-backend-service) |
| Curso y contenidos de Python | [course-content-backend-service](https://github.com/CODE4ALL-UV/course-content-backend-service) |
| Ejercicios y evaluación | [assessment-backend-service](https://github.com/CODE4ALL-UV/assessment-backend-service) |
| **Progreso y seguimiento** | **este repositorio** |
| Accesibilidad y adaptación | [accessibility-backend-service](https://github.com/CODE4ALL-UV/accessibility-backend-service) |
| Interacción multimodal | [multimodal-interaction-backend-service](https://github.com/CODE4ALL-UV/multimodal-interaction-backend-service) |
| Infraestructura y dispositivos | [device-management-backend-service](https://github.com/CODE4ALL-UV/device-management-backend-service) |
| Capa de datos compartida (Neon) | [neon-storage-backend-service](https://github.com/CODE4ALL-UV/neon-storage-backend-service) |
