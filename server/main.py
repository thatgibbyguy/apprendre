"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.config import settings
from server.routes import assessment, audio, conversation, drills, exercises, learners, lessons

app = FastAPI(title=settings.app_name, debug=settings.debug)


@app.on_event("startup")
def _startup_seed():
    """Ensure DB schema and test learners exist on every dev start."""
    from server.models.database import init_db
    from server.seed import seed

    init_db()
    seed()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(conversation.router, prefix="/api/conversation", tags=["conversation"])
app.include_router(lessons.router, prefix="/api/lessons", tags=["lessons"])
app.include_router(drills.router, prefix="/api/drills", tags=["drills"])
app.include_router(exercises.router, prefix="/api/exercises", tags=["exercises"])
app.include_router(assessment.router, prefix="/api/assessment", tags=["assessment"])
app.include_router(audio.router, prefix="/api/audio", tags=["audio"])
app.include_router(learners.router, prefix="/api/learners", tags=["learners"])

# Static files — served last so API routes take priority
if settings.static_dir.exists():
    app.mount("/", StaticFiles(directory=str(settings.static_dir), html=True), name="static")
