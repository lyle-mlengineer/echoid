from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.web import router as web_router
from app.core.config import Settings, get_settings
from app.domain.events import EventBus
from app.infrastructure.database import Base, build_database
from app.infrastructure.transcription import build_transcription_provider
import app.infrastructure.models  # noqa: F401


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    engine, session_factory = build_database(config.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=engine)
        config.storage_dir.mkdir(parents=True, exist_ok=True)
        yield
        engine.dispose()

    application = FastAPI(
        title="EchoID API",
        description="Speaker-aware audio transcription and credit billing.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = config
    application.state.session_factory = session_factory
    application.state.transcription_provider = build_transcription_provider(config)
    application.state.event_bus = EventBus()
    application.include_router(router, prefix="/api/v1")
    application.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    application.mount(
            "/audio",
            StaticFiles(directory=str(Path(__file__).parent / "audio")),
            name="audio",
        )
    application.include_router(web_router)
    return application


app = create_app()
