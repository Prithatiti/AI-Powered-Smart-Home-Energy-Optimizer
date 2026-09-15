"""
Weather request / response schemas.

Defines the two weather payloads the pipeline touches:

    * :class:`WeatherRequest`  - what the collector agent asks for
      (coordinates + timezone + optional forecast date).
    * :class:`WeatherForecast` - what the weather tool returns (the
      ``"weather"`` key of Agent 1's output), validated for the expected
      types and field set.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Schemas/weather.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Single-source timezone validator (kept in home.py, no re-definition here).
from Backend.Schemas.home import validate_timezone


class WeatherRequest(BaseModel):
    """Inputs the collector agent passes to the weather tool."""

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    timezone: str = "Asia/Kolkata"
    # Convention accepted by the weather tool: None means "tomorrow".
    forecast_date: str | None = Field(
        default=None, description="ISO date 'YYYY-MM-DD'; None means tomorrow."
    )

    @field_validator("timezone")
    @classmethod
    def _timezone_known(cls, value: str) -> str:
        """Reject timezone names the OS timezone database does not know."""
        return validate_timezone(value)

    @property
    def effective_date(self) -> str:
        """Return the requested date, defaulting to tomorrow (UTC)."""
        if self.forecast_date:
            return self.forecast_date
        return (date.today() + timedelta(days=1)).isoformat()


class WeatherForecast(BaseModel):
    """A one-day weather forecast (the ``weather`` key of Agent 1's output).

    Owns the exact field set the weather tool returns, so agent JSON validates
    against it without reshaping.
    """

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    forecast_date: str = Field(description="ISO date the forecast applies to.")
    min_temperature_c: float
    max_temperature_c: float
    weather_condition: str = "Unknown"
    source: str = "unknown"


# ---- Example usage (run directly: python weather.py) ------------------------
if __name__ == "__main__":
    req = WeatherRequest(latitude=18.5204, longitude=73.8567)
    print(f"Request effective date: {req.effective_date}")

    forecast = WeatherForecast(
        latitude=18.5204,
        longitude=73.8567,
        forecast_date="2026-09-16",
        min_temperature_c=22.4,
        max_temperature_c=29.7,
        weather_condition="Moderate drizzle",
        source="open-meteo",
    )
    print(f"Validated forecast: {forecast.model_dump()!r}")