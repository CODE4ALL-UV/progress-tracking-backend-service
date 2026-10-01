"""El rendimiento de los estudiantes por lección, para el panel del director.

Estas consultas vivían en el repositorio de usuarios del monolito. Pasaron
aquí porque solo las usa el seguimiento del director: user-management se queda
con lo que es suyo, las cuentas.
"""

from typing import Any

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from neon_storage.models import StudentPerformance, Usuario


class PerformanceRepository:
    def __init__(self, db_session: Session):
        self.db = db_session

    def get_user_by_id(self, user_id: int) -> Any:
        return self.db.query(Usuario).filter(Usuario.id_usuario == user_id).first()

    def list_students(self) -> list[Usuario]:
        """Devuelve todos los usuarios cuyo rol sea 'estudiante'."""
        return self.db.query(Usuario).filter(Usuario.rol == 'estudiante').all()

    def create_performance(self, performance_data: dict) -> Any:
        new = StudentPerformance(**performance_data)
        self.db.add(new)
        self.db.commit()
        self.db.refresh(new)
        return new

    def get_all_performances(self) -> list[StudentPerformance]:
        return self.db.query(StudentPerformance).order_by(StudentPerformance.created_at.desc()).all()

    def get_performances_by_student(self, usuario_id: int) -> list[StudentPerformance]:
        return self.db.query(StudentPerformance).filter(StudentPerformance.usuario_id == usuario_id).all()

    def aggregate_by_lesson(self) -> list[dict]:
        """Retorna agregados simples por lección: suma de score, failed, good, excellent."""
        rows = (
            self.db.query(
                StudentPerformance.lesson_name,
                func.sum(StudentPerformance.score).label('score'),
                func.sum(StudentPerformance.failed).label('failed'),
                func.sum(StudentPerformance.good).label('good'),
                func.sum(StudentPerformance.excellent).label('excellent'),
            )
            .group_by(StudentPerformance.lesson_name)
            .all()
        )

        return [
            {
                "lesson_name": r.lesson_name,
                "score": int(r.score or 0),
                "failed": int(r.failed or 0),
                "good": int(r.good or 0),
                "excellent": int(r.excellent or 0),
            }
            for r in rows
        ]

    def aggregate_avg_by_lesson(self) -> list[dict]:
        """Retorna promedio por lección: avg score, cantidad de registros y cantidad de estudiantes únicos."""
        rows = (
            self.db.query(
                StudentPerformance.lesson_name,
                func.avg(StudentPerformance.score).label('avg_score'),
                func.avg(StudentPerformance.failed).label('avg_failed'),
                func.avg(StudentPerformance.good).label('avg_good'),
                func.avg(StudentPerformance.excellent).label('avg_excellent'),
                func.count(StudentPerformance.id).label('records'),
                func.count(distinct(StudentPerformance.usuario_id)).label('students'),
            )
            .group_by(StudentPerformance.lesson_name)
            .all()
        )

        return [
            {
                "lesson_name": r.lesson_name,
                "avg_score": float(r.avg_score) if r.avg_score is not None else 0.0,
                "avg_failed": float(r.avg_failed) if r.avg_failed is not None else 0.0,
                "avg_good": float(r.avg_good) if r.avg_good is not None else 0.0,
                "avg_excellent": float(r.avg_excellent) if r.avg_excellent is not None else 0.0,
                "records": int(r.records or 0),
                "students": int(r.students or 0),
            }
            for r in rows
        ]
