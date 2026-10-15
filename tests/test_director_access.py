"""Quién entra al panel del director, y lo que el panel cuenta de verdad.

La sesión se comprueba en cada petición: sin token, con uno falso o con uno
que no dice de quién es, la respuesta es 401 y no un error del servidor. Lo
demás son las cifras de rendimiento por lección y la revisión del contenido,
que tiene que avisar cuando el docente cambió la sección después de aprobarla.
"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from neon_storage import SessionLocal
from neon_storage.courses import general_course, new_join_code
from neon_storage.models import ContentReview, Course, CourseOverride, Usuario
from progress_tracking_service.infrastructure.performance_repository import PerformanceRepository
from progress_tracking_service.main import app
from user_management_service.core.security import create_access_token

client = TestClient(app)


def _user(rol: str) -> tuple[int, str, dict]:
    email = f"{rol}-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = Usuario(nombre=rol.title(), correo=email, password="x", rol=rol)
        db.add(user)
        db.commit()
        user_id = user.id_usuario

    token = create_access_token(data={"sub": str(user_id), "email": email, "rol": rol})
    return user_id, email, {"Authorization": f"Bearer {token}"}


def _bearer(claims: dict) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data=claims)}"}


def _course_with_edit(teacher_id: int, email: str, section: str) -> int:
    with SessionLocal() as db:
        course = Course(teacher_id=teacher_id, title="Python", join_code=new_join_code(db))
        db.add(course)
        db.flush()
        db.add(
            CourseOverride(
                course_id=course.id,
                scope="section",
                target_id=section,
                payload="{}",
                updated_by=email,
            )
        )
        db.commit()
        return course.id


def _lesson() -> str:
    """Un nombre de lección que no comparta ninguna otra prueba."""
    return f"Lección {uuid.uuid4().hex[:8]}"


# --- la sesión en el panel de rendimiento ------------------------------------


def test_the_performance_panel_needs_a_session():
    response = client.get("/api/director/students")

    assert response.status_code == 401


def test_the_performance_panel_refuses_a_forged_token():
    response = client.get(
        "/api/director/students", headers={"Authorization": "Bearer no-es-un-token"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token inválido"


def test_a_token_that_names_nobody_does_not_open_the_panel():
    headers = _bearer({"email": "director@example.com", "rol": "director"})

    response = client.get("/api/director/students", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Token sin usuario"


def test_a_token_whose_user_is_not_a_number_does_not_open_the_panel():
    # Bien firmado, pero el sub no es un id: antes era un 500.
    headers = _bearer({"sub": "director", "email": "director@example.com", "rol": "director"})

    response = client.get("/api/director/students", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Token sin usuario"


def test_a_token_role_is_not_enough_without_the_account():
    # El token dice director, pero esa cuenta no existe en la base.
    headers = _bearer({"sub": "987654321", "email": "nadie@example.com", "rol": "director"})

    assert client.get("/api/director/students", headers=headers).status_code == 403


# --- rendimiento por lección -------------------------------------------------


def test_the_director_sees_each_recorded_performance():
    student_id, _, _ = _user("estudiante")
    _, _, director = _user("director")
    lesson = _lesson()

    created = client.post(
        "/api/director/performances",
        json={"usuario_id": student_id, "lesson_name": lesson, "score": 70, "failed": 2},
        headers=director,
    )
    assert created.status_code == 201

    rows = client.get("/api/director/performances", headers=director).json()
    row = next(r for r in rows if r["lesson_name"] == lesson)
    assert row["id"] == created.json()["id"]
    assert row["usuario_id"] == student_id
    assert (row["score"], row["failed"], row["good"], row["excellent"]) == (70, 2, 0, 0)
    assert row["created_at"]


def test_the_aggregate_adds_up_every_record_of_a_lesson():
    first_id, _, _ = _user("estudiante")
    second_id, _, _ = _user("estudiante")
    _, _, director = _user("director")
    lesson = _lesson()

    for body in (
        {"usuario_id": first_id, "score": 60, "failed": 1, "good": 2},
        {"usuario_id": second_id, "score": 90, "good": 1, "excellent": 3},
    ):
        client.post(
            "/api/director/performances", json={"lesson_name": lesson, **body}, headers=director
        )

    aggregate = client.get("/api/director/performances/aggregate", headers=director).json()

    assert next(r for r in aggregate if r["lesson_name"] == lesson) == {
        "lesson_name": lesson,
        "score": 150,
        "failed": 1,
        "good": 3,
        "excellent": 3,
    }

    average = client.get("/api/director/performances/average", headers=director).json()
    mean = next(r for r in average if r["lesson_name"] == lesson)
    assert mean["avg_score"] == 75.0
    assert mean["records"] == 2
    assert mean["students"] == 2


def test_the_performances_of_one_student_are_only_theirs():
    ana_id, _, _ = _user("estudiante")
    luis_id, _, _ = _user("estudiante")

    with SessionLocal() as db:
        repo = PerformanceRepository(db)
        mine = repo.create_performance({"usuario_id": ana_id, "lesson_name": _lesson()})
        repo.create_performance({"usuario_id": luis_id, "lesson_name": _lesson()})

        assert [p.id for p in repo.get_performances_by_student(ana_id)] == [mine.id]


# --- la sesión en el seguimiento docente -------------------------------------


def test_the_oversight_needs_a_session():
    response = client.get("/api/oversight/teachers")

    assert response.status_code == 401


def test_the_oversight_refuses_a_forged_token():
    response = client.get(
        "/api/oversight/teachers", headers={"Authorization": "Bearer no-es-un-token"}
    )

    assert response.status_code == 401
    assert "no es válida" in response.json()["detail"]


def test_the_oversight_refuses_a_token_that_names_nobody():
    without_id = _bearer({"email": "director@example.com", "rol": "director"})
    odd_id = _bearer({"sub": "director", "email": "director@example.com", "rol": "director"})

    for headers in (without_id, odd_id):
        response = client.get("/api/oversight/teachers", headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "La sesión no identifica a nadie."


# --- docentes y valoraciones -------------------------------------------------


def test_the_activity_of_someone_who_does_not_exist_is_a_404():
    _, _, director = _user("director")

    response = client.get("/api/oversight/teachers/987654321/activity", headers=director)

    assert response.status_code == 404


def test_only_teachers_are_reviewed():
    student_id, _, _ = _user("estudiante")
    _, _, director = _user("director")

    response = client.post(
        "/api/oversight/reviews",
        json={"docente_id": student_id, "score": 3, "comment": "No es docente."},
        headers=director,
    )

    assert response.status_code == 404
    history = client.get(f"/api/oversight/reviews/{student_id}", headers=director).json()
    assert history["count"] == 0


def test_the_teacher_list_shows_the_latest_and_the_average_score():
    teacher_id, _, _ = _user("docente")
    _, _, director = _user("director")

    for score, comment in ((2, "Faltan ejemplos."), (4, "Mucho mejor.")):
        client.post(
            "/api/oversight/reviews",
            json={"docente_id": teacher_id, "score": score, "comment": comment},
            headers=director,
        )

    teachers = client.get("/api/oversight/teachers", headers=director).json()["teachers"]
    me = next(t for t in teachers if t["user_id"] == teacher_id)
    assert me["reviews"] == 2
    assert me["avg_score"] == 3.0
    assert me["edits"] == 0
    assert me["last_edit"] is None


# --- revisar el contenido ----------------------------------------------------


def test_a_review_state_must_be_one_of_the_known_ones():
    _, _, director = _user("director")

    response = client.put(
        "/api/oversight/content/m1-s1",
        json={"section_id": "m1-s1", "status": "regular"},
        headers=director,
    )

    assert response.status_code == 400
    assert "aprobado" in response.json()["detail"]


def test_flagging_a_section_needs_to_say_what_is_wrong():
    _, _, director = _user("director")

    response = client.put(
        "/api/oversight/content/m1-s1",
        json={"section_id": "m1-s1", "status": "observado", "comment": "  "},
        headers=director,
    )

    assert response.status_code == 400


def test_a_section_of_a_course_that_does_not_exist_is_a_404():
    _, _, director = _user("director")

    response = client.put(
        "/api/oversight/content/m1-s1",
        json={"section_id": "m1-s1", "status": "aprobado", "course_id": 987654321},
        headers=director,
    )

    assert response.status_code == 404


def test_without_a_course_the_review_is_of_the_general_one():
    _, _, director = _user("director")
    section = f"m{uuid.uuid4().hex[:6]}"

    response = client.put(
        f"/api/oversight/content/{section}",
        json={"section_id": section, "status": "aprobado"},
        headers=director,
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        assert response.json()["course_id"] == general_course(db).id


def test_reviewing_again_replaces_the_state_instead_of_adding_another():
    teacher_id, mail, _ = _user("docente")
    _, _, director = _user("director")
    course_id = _course_with_edit(teacher_id, mail, "m3-s1")

    def review(status, comment=""):
        body = {"section_id": "m3-s1", "status": status, "comment": comment, "course_id": course_id}
        return client.put("/api/oversight/content/m3-s1", json=body, headers=director)

    assert review("observado", "Falta el ejercicio final.").json()["status"] == "observado"
    second = review("aprobado")

    assert second.status_code == 200
    assert second.json()["status"] == "aprobado"
    assert second.json()["comment"] == ""
    with SessionLocal() as db:
        rows = (
            db.query(ContentReview)
            .filter(ContentReview.course_id == course_id, ContentReview.section_id == "m3-s1")
            .all()
        )
    assert [r.status for r in rows] == ["aprobado"]


def test_an_approval_from_before_the_last_edit_is_marked_as_outdated():
    teacher_id, mail, _ = _user("docente")
    _, _, director = _user("director")
    course_id = _course_with_edit(teacher_id, mail, "m4-s1")

    client.put(
        "/api/oversight/content/m4-s1",
        json={"section_id": "m4-s1", "status": "aprobado", "course_id": course_id},
        headers=director,
    )

    # El docente reescribe la sección una hora después de la aprobación.
    with SessionLocal() as db:
        review = (
            db.query(ContentReview)
            .filter(ContentReview.course_id == course_id, ContentReview.section_id == "m4-s1")
            .one()
        )
        edit = (
            db.query(CourseOverride)
            .filter(CourseOverride.course_id == course_id, CourseOverride.target_id == "m4-s1")
            .one()
        )
        edit.updated_at = review.reviewed_at + timedelta(hours=1)
        db.commit()

    items = client.get("/api/oversight/content", headers=director).json()["items"]
    mine = next(i for i in items if i["course_id"] == course_id and i["section_id"] == "m4-s1")
    assert mine["status"] == "aprobado"
    assert mine["outdated"] is True

    activity = client.get(f"/api/oversight/teachers/{teacher_id}/activity", headers=director)
    item = activity.json()["items"][0]
    assert item["review_status"] == "aprobado"
    assert item["review_outdated"] is True
