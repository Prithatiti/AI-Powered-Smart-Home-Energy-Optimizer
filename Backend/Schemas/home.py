"""
Home configuration schema.

Defines - and validates - the configuration a household supplies about
itself before the two-agent pipeline runs.  This is the *input* half of the
pipeline: the workflow turns a :class:`HomeProfile` into the payload handed
to the collector agent.

Validated here:

    * Location           - ``city`` plus validated ``latitude`` / ``longitude``
    * Timezone           - IANA name (e.g. ``"Asia/Kolkata"``)
    * Household size     - ``hh_size`` occupants
    * Appliances         - the home's ``appliance`` names
    * Electricity tariff - time-of-use rate table the savings are priced against
    * User preferences   - comfort-vs-savings goal and automation flags
"""

import sys
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# Make the project root importable so `Backend.Config.settings` resolves even
# when this module is launched directly (python Backend/Schemas/home.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings


# ============================================================================
# Shared field validation (imported by other schema modules - single source)
# ============================================================================
def validate_timezone(value: str) -> str:
    """Validate an IANA timezone name (``"Asia/Kolkata"``, ``"UTC"``, ...).

    Raises:
        ValueError: if ``value`` is not present in the system timezone database.
    """
    try:
        ZoneInfo(key=value)  # raises ZoneInfoNotFoundError for unknown names
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid IANA timezone: {value!r}") from exc
    return value


# ============================================================================
# Home configuration models
# ============================================================================
class Appliance(BaseModel):
    """A single appliance the home wants optimized (e.g. ``"Air Conditioning"``)."""

    name: str = Field(
        min_length=1, description="Appliance name, e.g. 'Air Conditioning'."
    )


class TimeOfUseSlot(BaseModel):
    """One time-of-use tariff band: a price per kWh valid over a window.

    ``end_hour <= start_hour`` is allowed and means an overnight wrap
    (e.g. ``23`` -> ``03``), matching the savings-calculator tool.
    """

    start_hour: int = Field(ge=0, le=23, description="Window start hour, 0-23.")
    end_hour: int = Field(
        ge=1, le=24, description="Window end hour, 1-24; <= start wraps overnight."
    )
    rate: float = Field(gt=0, description="Price per kWh for this band.")


class ElectricityTariff(BaseModel):
    """The time-of-use tariff used to price appliance runs."""

    currency: str = Field(default=settings.CURRENCY, min_length=3, max_length=3)
    source: str = "computed"
    time_of_use: list[TimeOfUseSlot] = Field(default_factory=list)


class UserPreferences(BaseModel):
    """User-level optimization goals and automation flags."""

    goal: Literal["comfort", "balanced", "savings"] = "balanced"
    auto_apply: bool = Field(
        default=False, description="Apply recommended schedules automatically."
    )


class HomeProfile(BaseModel):
    """Validated home configuration consumed by the optimization workflow.

    Defaults mirror the demo household used by the agent demos (Pune,
    18.5204 N / 73.8567 E, household of 3).  ``latitude`` / ``longitude`` can
    be filled in from a ``city`` name by the workflow's geocoding step.

    Unknown fields are rejected (``extra="forbid"``) so a typos like
    ``appliances_present`` fails loudly instead of being silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    city: str | None = Field(
        default=None, description="Optional city name, resolved to coordinates."
    )
    latitude: float = Field(default=18.5204, ge=-90.0, le=90.0)
    longitude: float = Field(default=73.8567, ge=-180.0, le=180.0)
    timezone: str = Field(default="Asia/Kolkata", description="IANA timezone name.")
    hh_size: int = Field(default=3, ge=1, le=20, description="Number of occupants.")
    appliances: list[Appliance] = Field(default_factory=list)
    tariff: ElectricityTariff | None = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)

    @field_validator("timezone")
    @classmethod
    def _timezone_known(cls, value: str) -> str:
        """Reject timezone names the OS timezone database does not know."""
        return validate_timezone(value)


# ---- Example usage (run directly: python home.py) ---------------------------
if __name__ == "__main__":
    settings.setup_logging(level="INFO")

    profile = HomeProfile()  # defaults model the demo Pune household
    print(f"Default profile: {profile.model_dump()!r}")
    try:
        HomeProfile(latitude=181.0)  # out of range -> ValidationError
    except ValidationError as exc:
        print(f"Rejected invalid latitude: {exc}")
