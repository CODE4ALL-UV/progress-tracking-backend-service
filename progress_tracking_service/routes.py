"""Lo que este microservicio aporta al API Gateway.

El gateway (repo Back-end) llama a `register(app)` de cada servicio, y el
`main.py` de este paquete hace lo mismo para arrancarlo solo. Así las rutas se
declaran una sola vez, se arranque como se arranque.
"""

from fastapi import FastAPI

from progress_tracking_service.presentation.api.director_oversight_routes import router as oversight_router
from progress_tracking_service.presentation.api.director_routes import router as director_router


def register(app: FastAPI) -> None:
    app.include_router(director_router)
    app.include_router(oversight_router)
