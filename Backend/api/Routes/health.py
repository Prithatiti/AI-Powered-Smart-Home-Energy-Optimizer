"""
Health-check endpoint.

Lets load balancers, container orchestrators and monitoring probes confirm
that the backend process is alive and responding.

    GET /health  ->  {"status": "healthy", "service": "wattpilot-backend"}
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check", response_model=dict)
def health_check() -> dict:
    """Return a minimal, always-200 payload confirming the service is up."""
    return {"status": "healthy", "service": "wattpilot-backend"}