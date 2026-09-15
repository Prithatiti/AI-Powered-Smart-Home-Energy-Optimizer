"""
Optimization recommendation schema.

Defines the final response of the pipeline - what the optimizer agent returns
to the caller.  A response carries a natural-language :class:`OptimizationRecommendation.summary`,
an optional overall outlook (predicted use, energy / cost savings, currency,
weather context), a confidence indicator, and the per-appliance
:class:`ApplianceAction` list that makes the plan actionable.
"""

import sys
from pathlib import Path

from pydantic import BaseModel, Field

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Schemas/recommendation.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings

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
        estimated_kwh_saving=2.0,
        estimated_cost_saving=57.0,
        confidence=0.9,
    )
    print(f"Validated recommendation: {rec.model_dump()!r}")