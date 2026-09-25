"""FastAPI entrypoint for accounts and, when enabled, the analytics API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from backend.config import settings
from backend.csrf import CSRFCookieMiddleware
from backend.database import init_db
from backend.routers.auth import router as auth_router


def _validation_detail(exc: RequestValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors():
        message = str(error.get("msg", "Invalid value"))
        prefix = "Value error, "
        if message.startswith(prefix):
            message = message[len(prefix) :]
        location = [str(part) for part in error.get("loc", []) if part not in {"body", "query"}]
        field = location[-1] if location else ""
        if field in {"password", "confirm_password"} and "at least 10" not in message and "match" not in message:
            message = "Password must be at least 10 characters and include a letter and a number."
        if message not in messages:
            messages.append(message)
    return " ".join(messages) or "Check the form and try again."


def create_app(*, include_product: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        yield

    app = FastAPI(
        title="Puchoo.ai API",
        description="FastAPI is the only security boundary for Puchoo.ai.",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": _validation_detail(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(CSRFCookieMiddleware)
    app.include_router(auth_router, prefix="/api/v1")

    if include_product:
        app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax", https_only=settings.cookie_secure)
        from apps.api.routers import history, query, sarvam, settings as settings_router, workspaces

        app.include_router(workspaces.router, prefix="/api")
        app.include_router(query.router, prefix="/api")
        app.include_router(history.router, prefix="/api")
        app.include_router(settings_router.router, prefix="/api")
        app.include_router(sarvam.router, prefix="/api")

    @app.get("/api/health")
    def health_check():
        return {"status": "ok"}

    return app


app = create_app(include_product=True)


__all__ = ["app", "create_app"]
