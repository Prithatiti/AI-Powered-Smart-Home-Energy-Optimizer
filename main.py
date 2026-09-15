"""
Wattpilot backend - FastAPI application entry point.

The main entry point for the backend HTTP API.  Boots the FastAPI app, mounts
the route modules under :mod:`Backend.api.Routes` and exposes them to clients.

Run locally:

    python main.py

or, for hot reload during development:

    uvicorn main:app --reload

Interactive API docs are served at ``/docs`` while the app is running.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Route modules (health check, energy, recommendations, email).
from Backend.api.Routes import email_plan, energy, health, recommendations

# Centralised configuration (logging policy, environment, secrets).
from Backend.Config import settings

logger = logging.getLogger(name=__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application startup / shutdown lifecycle.

    Startup: configure the shared logging policy and fail fast in production
    when required secrets are missing.  Shutdown: log the stop (identity is
    useful in logs and in deployment/monitoring tooling).
    """
    settings.setup_logging()
    logger.info("Wattpilot backend starting...")
    if settings.IS_PRODUCTION:
        settings.require_secrets()
    yield
    logger.info("Wattpilot backend stopped.")


app = FastAPI(
    title="WattPilot AI Backend: AI-Powered-Smart-Home-Energy-Optimizer",
    description="AI-powered smart home energy optimization API.",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount the route modules on the application.
app.include_router(health.router)            # GET  /health
app.include_router(energy.router)            # GET  /api/v1/energy/history
                                             # POST /api/v1/energy/forecast
app.include_router(recommendations.router)   # POST /api/v1/recommendations
app.include_router(email_plan.router)        # POST /api/v1/email/plan


@app.get(path="/", summary="Service overview")
def root() -> dict:
    """Advertise the service name, its endpoints and the API documentation."""
    return {
        "service": "wattpilot-backend",
        "status": "healthy",
        "documentation": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app="main:app", host="127.0.0.1", port=8000, reload=False)