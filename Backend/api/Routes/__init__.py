"""
Route modules for the Wattpilot backend API.

Organises the API into four focused modules:

    * :mod:`Backend.api.Routes.health`          - liveness / health check
    * :mod:`Backend.api.Routes.energy`          - energy history + day-ahead forecast
    * :mod:`Backend.api.Routes.recommendations` - AI energy-saving recommendations
    * :mod:`Backend.api.Routes.email_plan`      - email an optimization plan

``main.py`` imports the routers exposed in :data:`__all__` and mounts them on
the FastAPI application.
"""

from Backend.api.Routes import email_plan, energy, health, recommendations

__all__ = ["email_plan", "energy", "health", "recommendations"]