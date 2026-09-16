"""
Energy consumption schemas.

Models the appliance-level usage records Agent 1 collects (the ``last_usage``
key of its output).  Each record describes one run of one appliance: its date,
operating window, energy draw in kWh, the ambient temperature it ran under and
the reported weather condition.

The date / time cell formats deliberately accept both the CSV encoding
(``"M/D/YYYY"``, ``"M-D-YYYY"``, ``"19:00"``) and the ISO encoding
(``"YYYY-MM-DD"``), so rows from the historical dataset and rows echoed
back by the agent validate alike.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Schemas/energy.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Accepted date-cell formats, tried in order (mirrors energy_service.py).
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y")  # ISO, M/D/YYYY, M-D-YYYY
# Accepted time-cell formats: "19:00" and the end-of-day sentinel "24:00".
_TIME_FORMATS = ("%H:%M",)


class ApplianceUsage(BaseModel):
    """One appliance usage event, validated for types, ranges and cell formats."""

    date: str = Field(description="Usage date, ISO, M/D/YYYY or M-D-YYYY.")
    appliance: str = Field(min_length=1)
    start_time: str = Field(description="Run start, 24h 'HH:MM'.")
    end_time: str = Field(description="Run end, 24h 'HH:MM' (may be '24:00').")
    mode: str = "Normal"
    kwh_consumed: float = Field(ge=0.0, description="Energy drawn, in kWh.")
    avg_temp: float = Field(ge=-60.0, le=60.0, description="Ambient °C during the run.")
    weather_condition: str = "Unknown"

    @field_validator("date")
    @classmethod
    def _date_parsable(cls, value: str) -> str:
        """Reject dates the two supported formats cannot represent."""
        for fmt in _DATE_FORMATS:
            try:
                datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"date must match one of {_DATE_FORMATS}, got {value!r}")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        """Reject clock cells that are not 'HH:MM' (or the '24:00' end sentinel)."""
        if value == "24:00":
            return value
        try:
            datetime.strptime(value, _TIME_FORMATS[0])
        except ValueError as exc:
            raise ValueError(f"time must be 24h 'HH:MM', got {value!r}") from exc
        return value


# ---- Example usage (run directly: python energy.py) -------------------------
if __name__ == "__main__":
    row: dict[str, Any] = {
        "date": "11-08-2026",
        "appliance": "Air Conditioning",
        "start_time": "19:00",
        "end_time": "23:00",
        "mode": "Cooling",
        "kwh_consumed": 5.1,
        "avg_temp": 32.2,
        "weather_condition": "Hot",
    }
    usage = ApplianceUsage.model_validate(row)
    print(f"Validated usage: {usage.model_dump()!r}")
    try:
        ApplianceUsage.model_validate({**row, "end_time": "25:00"})
    except ValidationError as exc:
        print(f"Rejected bad clock: {exc}")
