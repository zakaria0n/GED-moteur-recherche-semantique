"""Point d'entree FastAPI : application, middleware et demarrage.

Les routes sont definies dans controllers/ (auth, documents),
la logique de synchronisation dans services/sync_service.py.
"""

from contextlib import asynccontextmanager
import os
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from shared import logger
from config import FRONTEND_BASE_URL
from config.ratelimit import limiter
from repositories.setup import initialize_database
from controllers import auth as auth_router
from controllers import documents as documents_router
from services.state import search_state
from services.sync_service import start_background_startup_sync


ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", FRONTEND_BASE_URL).split(",")
    if origin.strip()
]


@asynccontextmanager
async def lifespan(app):
    try:
        initialize_database()
        search_state["database_error"] = None
        logger.info("demarrage", "Lancement de la synchronisation initiale en deux phases...")
        start_background_startup_sync()
    except Exception as exc:
        search_state["database_error"] = str(exc)
        logger.error("demarrage", f"Erreur au demarrage: {exc}")

    yield


app = FastAPI(title="Semantic GED Backend", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request, call_next):
    """Journalise chaque requete (methode, chemin, statut, duree).

    Pas d'enrichissement utilisateur : evite une requete SQL supplementaire
    a chaque requete HTTP (impacte la performance sous charge).
    """
    start = perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (perf_counter() - start) * 1000
        logger.error(
            "requete",
            f"{request.method} {request.url.path} -> erreur interne: {exc}",
        )
        raise

    duration_ms = (perf_counter() - start) * 1000
    logger.request(
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    return response


app.include_router(auth_router.router)
app.include_router(documents_router.router)
