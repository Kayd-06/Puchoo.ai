"""Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from apps.api.routers import workspaces, query, history, notifications, settings, sarvam
from backend.config import settings as backend_settings
from backend.csrf import CSRFCookieMiddleware
from backend.database import init_db
from backend.routers.auth import router as auth_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Puchoo.ai API",
    description="FastAPI Backend for Puchoo.ai",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for local React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=backend_settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-CSRF-Token"],
)

# Session middleware supports the analytics UI; account auth uses server-bound JWTs.
app.add_middleware(
    SessionMiddleware, 
    secret_key=backend_settings.session_secret,
    same_site="lax",
    https_only=backend_settings.cookie_secure,
)

# CSRF protection
app.add_middleware(CSRFCookieMiddleware)

# Include routers
app.include_router(workspaces.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(sarvam.router, prefix="/api")
app.include_router(auth_router, prefix="/api/v1")

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
