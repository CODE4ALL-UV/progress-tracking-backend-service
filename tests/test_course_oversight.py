"""La dirección revisa el contenido curso por curso.

Dos docentes pueden reescribir la misma sección cada uno en su curso. Aprobar
la versión de uno no puede dar por aprobada la del otro.
"""

import uuid

from fastapi.testclient import TestClient

from neon_storage import SessionLocal
from neon_storage.courses import new_join_code
from neon_storage.models import Course, CourseEnrollment, CourseOverride, Usuario
from progress_tracking_service.main import app
from user_management_service.core.security import create_access_token

client = TestClient(app)


def _user(rol: str) -> tuple[int, str, dict]:
    email = f"{rol}-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        user = Usuario(nombre=f"{rol.title()} {email[:6]}", correo=email, password="x", rol=rol)
        db.add(user)
        db.commit()
        user_id = user.id_usuario

    token = create_access_token(data={"sub": str(user_id), "email": email, "rol": rol})
    return user_id, email, {"Authorization": f"Bearer {token}"}


def _course_with_edit(teacher_id: int, email: str, section: str, *students: int) -> int:
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
        for student_id in students:
            db.add(CourseEnrollment(course_id=course.id, student_id=student_id))
        db.commit()
        return course.id


def test_approving_one_teachers_section_does_not_approve_the_others():
    ana_id, ana_mail, _ = _user("docente")
    luis_id, luis_mail, _ = _user("docente")
    _, _, director = _user("director")
    ana_course = _course_with_edit(ana_id, ana_mail, "m1-s2")
    luis_course = _course_with_edit(luis_id, luis_mail, "m1-s2")

    approved = client.put(
        "/api/oversight/content/m1-s2",
        json={"section_id": "m1-s2", "status": "aprobado", "course_id": ana_course},
        headers=director,
    )
    assert approved.status_code == 200
    assert approved.json()["course_id"] == ana_course

    reviews = client.get("/api/oversight/content", headers=director).json()["items"]
    reviewed = {(r["course_id"], r["section_id"]) for r in reviews}
    assert (ana_course, "m1-s2") in reviewed
    assert (luis_course, "m1-s2") not in reviewed

    activity = client.get(f"/api/oversight/teachers/{luis_id}/activity", headers=director)
    item = activity.json()["items"][0]
    assert item["course_id"] == luis_course
    assert item["review_status"] is None


def test_the_coordination_sees_each_course_with_its_teacher_and_edits():
    teacher_id, mail, _ = _user("docente")
    student_id, _, _ = _user("estudiante")
    _, _, director = _user("director")
    course_id = _course_with_edit(teacher_id, mail, "m2-s3", student_id)

    listed = client.get("/api/oversight/courses", headers=director).json()["courses"]
    assert listed[0]["is_general"] is True

    course = next(c for c in listed if c["id"] == course_id)
    assert course["teacher"]["id"] == teacher_id
    assert course["students"] == 1
    assert [e["section_id"] for e in course["edited_sections"]] == ["m2-s3"]

    teachers = client.get("/api/oversight/teachers", headers=director).json()["teachers"]
    assert next(t for t in teachers if t["user_id"] == teacher_id)["courses"] == 1


def test_only_the_coordination_lists_the_courses():
    _, _, teacher = _user("docente")

    assert client.get("/api/oversight/courses", headers=teacher).status_code == 403
