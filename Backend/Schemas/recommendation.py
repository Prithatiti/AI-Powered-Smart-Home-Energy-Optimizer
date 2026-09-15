"""
Optimization recommendation schema.

Defines the final response of the pipeline - what the optimizer agent returns
to the caller.  A response carries a natural-language :class:`OptimizationRecommendation.summary`,
an optional overall outlook (predicted use, energy / cost savings, currency,
weather context), a confidence indicator, and the per-appliance
:class:`ApplianceAction` list that makes the plan actionable.
"""

import sys
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Schemas/recommendation.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings

# Single-source timezone validator (kept in home.py, no re-definition here).
from Backend.Schemas.home import validate_timezone

# Reuses the weather schema so the response can echo the forecast it was
# reasoned from (single definition, no re-modelling here).
from Backend.Schemas.weather import WeatherForecast


class ApplianceAction(BaseModel):
    """One appliance-level optimization: what to do and what it saves."""

    appliance: str = Field(min_length=1)
    recommendation: str = Field(min_length=1, description="Human-readable action.")
    estimated_kwh_saving: float = Field(ge=0.0, description="Energy saved, in kWh.")
    estimated_cost_saving: float = Field(ge=0.0, description="Money saved.")
    currency: str = Field(default=settings.CURRENCY, min_length=3, max_length=3)


class OptimizationRecommendation(BaseModel):
    """The validated, final recommendation returned to the caller."""

    summary: str = Field(min_length=1, description="Natural-language plan summary.")
    actions: list[ApplianceAction] = Field(default_factory=list)

    # Overall outlook (optional - the agent may supply all or part of it).
    predicted_total_kwh: float | None = Field(default=None, ge=0.0)
    estimated_energy_saving_kwh: float | None = Field(default=None, ge=0.0)
    estimated_cost_saving: float | None = Field(default=None, ge=0.0)
    currency: str = Field(default=settings.CURRENCY, min_length=3, max_length=3)
    weather: WeatherForecast | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    factors: list[str] = Field(default_factory=list, description="Supporting considerations.")


class OptimizeEnergyRequest(BaseModel):
    """API request accepted by the recommendations endpoint.

    Carries the home configuration together with the household's time-of-use
    tariff (peak / off-peak rates and the peak window), ready to be mapped to
    a :class:`HomeProfile` and fed to the optimization workflow.
    """

    hh_size: int = Field(ge=1, le=20, description="Number of occupants.")
    appliances_present: list[str] = Field(description="Appliance names to optimize.")
    latitude: float = Field(default=18.6298, ge=-90.0, le=90.0)
    longitude: float = Field(default=73.7997, ge=-180.0, le=180.0)
    timezone: str = "Asia/Kolkata"
    rate_peak: float = Field(default=12.0, gt=0.0, description="Price per kWh (peak band).")
    rate_offpeak: float = Field(default=7.5, gt=0.0, description="Price per kWh (off-peak band).")
    tariff_peak_start: str = "18:00"
    tariff_peak_end: str = "22:00"

    @field_validator("timezone")
    @classmethod
    def _timezone_known(cls, value: str) -> str:
        """Reject timezone names the OS timezone database does not know."""
        return validate_timezone(value)

    @field_validator("tariff_peak_start", "tariff_peak_end")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        """Reject tariff-band times that are not valid 24h 'HH:MM'."""
        try:
            datetime.strptime(value, "%H:%M")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Tariff time must be 24h 'HH:MM', got {value!r}") from exc
        return value

    model_config = {
        "json_schema_extra": {
            "example": {
                "hh_size": 4,
                "appliances_present": ["Air Conditioning", "Microwave", "Computer"],
                "latitude": 18.6298,
                "longitude": 73.7997,
                "timezone": "Asia/Kolkata",
                "rate_peak": 12.0,
                "rate_offpeak": 7.5,
                "tariff_peak_start": "18:00",
                "tariff_peak_end": "22:00",
            }
        }
    }


# ---- Example usage (run directly: python recommendation.py) -----------------
if __name__ == "__main__":
    rec = OptimizationRecommendation(
        summary="Shift cooling off-peak to dodge peak pricing.",
        actions=[
            ApplianceAction(
                appliance="Air Conditioning",
                recommendation="Run 23:00-03:00 instead of 19:00-23:00.",
                estimated_kwh_saving=2.0,
                estimated_cost_saving=57.0,
            )
        ],
        estimated_energy_saving_kwh=2.0,
        estimated_cost_saving=57.0,
        confidence=0.9,
    )
    print(f"Validated recommendation: {rec.model_dump()!r}")