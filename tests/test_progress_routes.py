"""El panel del director: rendimiento de estudiantes y seguimiento docente.

Aquí el rol se comprueba contra la base, no contra el token, así que las
pruebas crean los usuarios de verdad en la base temporal.
"""

import uuid

from fastapi.testclient import TestClient

from neon_storage import SessionLocal
from neon_storage.models import Usuario
from progress_tracking_service.main import app
from user_management_service.core.security import create_access_token

client = TestClient(app)


def _user(rol: str) -> tuple[int, dict]:
    email = f"{rol}-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = Usuario(nombre=rol.title(), correo=email, password="x", rol=rol)
        db.add(user)
        db.commit()
        user_id = user.id_usuario

    token = create_access_token(data={"sub": str(user_id), "email": email, "rol": rol})
    return user_id, {"Authorization": f"Bearer {token}"}


def test_the_director_lists_students_and_records_performance():
    student_id, _ = _user("estudiante")
    _, director = _user("director")

    students = client.get("/api/director/students", headers=director)
    assert students.status_code == 200
    assert any(s["id_usuario"] == student_id for s in students.json())

    created = client.post(
        "/api/director/performances",
        json={"usuario_id": student_id, "lesson_name": "Bucles", "score": 80, "good": 1},
        headers=director,
    )
    assert created.status_code == 201

    average = client.get("/api/director/performances/average", headers=director).json()
    assert any(row["lesson_name"] == "Bucles" for row in average)


def test_only_the_director_reaches_the_director_panel():
    _, teacher = _user("docente")

    assert client.get("/api/director/students", headers=teacher).status_code == 403
    assert client.get("/api/oversight/teachers", headers=teacher).status_code == 403


def test_a_teacher_review_needs_a_comment():
    teacher_id, _ = _user("docente")
    _, director = _user("director")

    empty = client.post(
        "/api/oversight/reviews",
        json={"docente_id": teacher_id, "score": 4, "comment": "  "},
        headers=director,
    )
    assert empty.status_code == 400

    saved = client.post(
        "/api/oversight/reviews",
        json={"docente_id": teacher_id, "score": 4, "comment": "Buen material."},
        headers=director,
    )
    assert saved.status_code == 201

    history = client.get(f"/api/oversight/reviews/{teacher_id}", headers=director).json()
    assert history["count"] == 1
