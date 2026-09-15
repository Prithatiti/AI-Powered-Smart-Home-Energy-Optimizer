"""
Shared Pydantic schemas for the two-agent energy optimization pipeline.

The schemas define the *shape contract* for everything that crosses an
application boundary: the home configuration a user provides, the weather and
energy data the collector agent gathers, the forecast the ML models emit, and
the final savings recommendation the optimizer agent returns.

Working-notes on the design:

* Every schema is a Pydantic ``BaseModel`` so inbound data (API payloads,
  agent JSON, CSV rows) is validated for types and ranges at the edge, before
  the rest of the pipeline sees it.
* Models mirror the exact JSON the agents already produce / consume (keys
  like ``ds``, ``yhat``, ``time_of_use``) so existing agent output validates
  without reshaping.
* Shared validation helpers live next to their primary owner (e.g.
  :func:`Backend.Schemas.home.validate_timezone`) and are imported there,
  never re-defined, so no logic is duplicated across files.
"""

# Re-export every public model so callers can import from the package root:
#     from Backend.Schemas import HomeProfile, OptimizationRecommendation
from Backend.Schemas.email import EmailPlanRequest
from Backend.Schemas.energy import ApplianceUsage
from Backend.Schemas.forecast import ApplianceForecast, ForecastRequest
from Backend.Schemas.home import (
    Appliance,
    ElectricityTariff,
    HomeProfile,
    TimeOfUseSlot,
    UserPreferences,
    validate_timezone,
)
from Backend.Schemas.recommendation import (
    ApplianceAction,
    OptimizationRecommendation,
    OptimizeEnergyRequest,
)
from Backend.Schemas.weather import WeatherForecast, WeatherRequest

__all__ = [
    "Appliance",
    "ApplianceAction",
    "ApplianceForecast",
    "ApplianceUsage",
    "ElectricityTariff",
    "EmailPlanRequest",
    "ForecastRequest",
    "HomeProfile",
    "OptimizationRecommendation",
    "OptimizeEnergyRequest",
    "TimeOfUseSlot",
    "UserPreferences",
    "WeatherForecast",
    "WeatherRequest",
    "validate_timezone",
]