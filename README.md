# progress-tracking-backend-service
Repositorio Back-end para el módulo Progreso y Seguimiento.

El panel del director: el rendimiento de los estudiantes por lección y el
seguimiento del trabajo docente (qué editó cada docente, sus valoraciones y la
revisión del contenido de cada sección).

| Rutas | Quién |
|---|---|
| `GET /api/director/students`, `GET /api/director/performances*`, `POST /api/director/performances` | Director |
| `GET /api/oversight/teachers`, `GET /api/oversight/teachers/{user_id}/activity` | Director |
| `POST /api/oversight/reviews`, `GET /api/oversight/reviews/{user_id}` | Director |
| `PUT /api/oversight/content/{section_id}`, `GET /api/oversight/content` | Director |

**Tablas que escribe:** `student_performance`, `TeacherReview`,
`ContentReview`. Lee `Usuario` y `CourseOverride`.

**Sesión:** el rol de director se comprueba contra la base, no contra el
token: a quien deja de ser director se le corta el acceso en el momento.

## Cómo lo monta el gateway

`progress_tracking_service/routes.py` tiene `register(app)`, que añade las rutas de este
servicio a una aplicación de FastAPI. El gateway lo llama para cada servicio, y
`progress_tracking_service/main.py` hace lo mismo para arrancarlo solo.

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

```bash
pytest tests
```

No tocan Neon: usan una base SQLite temporal. Buscan `neon-storage` y
`user-management` en los repos hermanos, así que funcionan igual con los repos
clonados uno al lado del otro que dentro de `services/` del gateway.
