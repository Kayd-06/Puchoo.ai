"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from apps.api.security import CSRFMiddleware
from apps.api.routers import workspaces, query, history, settings, sarvam

app = FastAPI(
    title="Puchoo.ai API",
    description="FastAPI Backend for Puchoo.ai",
    version="1.0.0",
)

# CORS middleware for local React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-CSRF-Token"],
)

# Session middleware for simple in-memory session (to be replaced with Redis/real session)
app.add_middleware(
    SessionMiddleware, 
    secret_key="dev-secret-key-do-not-use-in-prod"
)

# CSRF protection
app.add_middleware(CSRFMiddleware)

# Include routers
app.include_router(workspaces.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(sarvam.router, prefix="/api")

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
