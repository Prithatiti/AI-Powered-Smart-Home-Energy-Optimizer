"""
Energy forecast schemas.

Models the inputs and outputs of the Prophet-based day-ahead forecast:

    * :class:`ForecastRequest`   - the per-appliance features the ML tool needs
      (appliance, target date, expected temperature, household size, weekend?).
    * :class:`ApplianceForecast` - one appliance's forecast row (the ``yhat``
      point estimate plus confidence band), identical to the rows the collector
      agent returns under its ``forecasts`` key.

Field names mirror the Prophet output contract (``ds``, ``yhat``, ...) so ML
output validates against the schema without any renaming.
"""

import sys
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Schemas/forecast.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))


def _iso_date(value: str) -> str:
    """Reject strings that are not a valid ISO 'YYYY-MM-DD' date."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"date must be ISO 'YYYY-MM-DD', got {value!r}") from exc
    return value


class ForecastRequest(BaseModel):
    """Input features for forecasting one appliance's next-day consumption."""

    appliance: str = Field(min_length=1)
    forecast_date: str = Field(description="ISO 'YYYY-MM-DD' of the target day.")
    avg_temp: float = Field(ge=-60.0, le=60.0, description="Expected outdoor °C.")
    hh_size: int = Field(ge=1, le=20, description="Number of occupants.")
    is_weekend: int = Field(ge=0, le=1, description="1 for a weekend day, else 0.")

    @field_validator("forecast_date")
    @classmethod
    def _date_iso(cls, value: str) -> str:
        """Enforce the ISO date contract on the request field."""
        return _iso_date(value)


class ApplianceForecast(BaseModel):
    """One appliance's day-ahead forecast row (Prophet output shape)."""

    appliance: str = Field(min_length=1)
    ds: str = Field(description="Forecast day, ISO 'YYYY-MM-DD'.")
    yhat: float = Field(description="Predicted kWh for the day.")
    yhat_lower: float | None = Field(default=None, description="95% CI lower bound.")
    yhat_upper: float | None = Field(default=None, description="95% CI upper bound.")
    model_path: str | None = Field(default=None, description="Artifact used for the forecast.")
    split_date: str | None = Field(default=None, description="Model train/validate split date.")

    @field_validator("ds")
    @classmethod
    def _ds_iso(cls, value: str) -> str:
        """Enforce the ISO date contract on the Prophet day column."""
        return _iso_date(value)


# ---- Example usage (run directly: python forecast.py) -----------------------
if __name__ == "__main__":
    req = ForecastRequest(
        appliance="Air Conditioning",
        forecast_date="2026-09-16",
        avg_temp=26.0,
        hh_size=3,
        is_weekend=0,
    )
    print(f"Validated request: {req.model_dump()!r}")

    row = ApplianceForecast(
        appliance="Air Conditioning",
        ds="2026-09-16",
        yhat=10.0,
        yhat_lower=5.0,
        yhat_upper=15.0,
        model_path="Backend/Artifacts/Models/prophet_air_conditioning.pkl",
        split_date="2023-10-20",
    )
    print(f"Validated forecast: {row.model_dump()!r}")