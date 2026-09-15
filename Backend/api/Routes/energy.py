"""
Energy API endpoints (history + forecasting).

    * GET  /api/v1/energy/history   - historical appliance-level consumption
    * POST /api/v1/energy/forecast  - day-ahead, per-appliance kWh predictions

These endpoints are deterministic: they reuse the shared schemas
(:class:`HomeProfile`, :class:`ApplianceUsage`, :class:`ApplianceForecast`)
plus the forecast / weather services and the trained Prophet artifacts - no
agent / LLM round-trip is involved.

The forecast flow:

    1. Validate the request body as a :class:`HomeProfile` (the home config).
    2. Resolve coordinates (``city`` -> lat/lon when no coords are given).
    3. Fetch next-day weather and derive the expected average temperature.
    4. Predict next-day kWh per appliance with the trained Prophet models.
    5. Return the results as validated :class:`ApplianceForecast` rows.
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/api/Routes/energy.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings
from Backend.Schemas import ApplianceForecast, ApplianceUsage, HomeProfile
from Backend.Services.energy_service import get_latest_usage, read_usage_records
from Backend.Services.geocode_service import geocode
from Backend.Tools.ml_prediction_tool import predict_daily_kwh
from Backend.Tools.weather_forecast_tool import get_weather_forecast

router = APIRouter(prefix="/api/v1/energy", tags=["energy"])

logger = logging.getLogger(__name__)

# Fallback temperature (Celsius) used when the weather service is unreachable;
# the trained models cannot forecast against a broken / placeholder reading.
_FALLBACK_AVG_TEMP = 25.0


@router.get(path="/history", summary="Historical energy consumption")
def get_energy_history(
    limit: int | None = Query(
        default=None, ge=1, le=10000, description="Max records to return."
    )
) -> dict:
    """Return historical appliance-level usage records from the dataset.

    Records are validated through :class:`ApplianceUsage`; malformed rows are
    logged and skipped so one bad cell never breaks the whole response.
    """
    try:
        raw_records = read_usage_records()
    except FileNotFoundError as exc:
        logger.error("Historical dataset unavailable: %s", exc)
        raise HTTPException(
            status_code=503, detail="Historical usage dataset is unavailable."
        ) from exc

    records: list = []
    skipped = 0
    for row in raw_records:
        try:
            records.append(ApplianceUsage.model_validate(row).model_dump())
        except Exception as exc:  # noqa: BLE001 - tolerant by contract
            skipped += 1
            logger.warning("Skipping malformed usage record: %s", exc)
        if limit is not None and len(records) >= limit:
            break

    return {"total": len(records), "skipped": skipped, "records": records}


@router.post(
    path="/forecast",
    response_model=list[ApplianceForecast],
    summary="Day-ahead per-appliance forecast",
)
def forecast_next_day(profile: HomeProfile) -> list[ApplianceForecast]:
    """Forecast next-day kWh for each appliance of a home configuration.

    The request body is a :class:`HomeProfile` (which appliances exist, the
    household size, location).  When the profile carries no appliances, the
    appliance list is derived from the most recent usage records instead.
    """
    tomorrow = (datetime.now(tz=timezone.utc) + timedelta(days=1)).date()
    is_weekend = 1 if tomorrow.weekday() >= 5 else 0
    forecast_date = tomorrow.isoformat()

    # ---- Resolve coordinates: use explicit ones, else geocode the city ----
    latitude, longitude = profile.latitude, profile.longitude
    if profile.city:
        try:
            matches = geocode(city=profile.city, limit=1)
            if matches:
                latitude = float(matches[0]["lat"])
                longitude = float(matches[0]["lon"])
        except Exception as exc:  # noqa: BLE001 - geocoding is best-effort
            logger.warning("Geocoding failed for %r; keeping profile coords: %s", profile.city, exc)

    # ---- Expected temperature for the target day ----------------------------
    weather = get_weather_forecast(
        latitude=latitude,
        longitude=longitude,
        timezone=profile.timezone,
        forecast_date=forecast_date,
    )
    min_temp = weather.get("min_temperature_c")
    max_temp = weather.get("max_temperature_c")
    # Only trust the upstream numbers; fallback placeholders must not leak in.
    if weather.get("source") == "open-meteo" and min_temp is not None and max_temp is not None:
        avg_temp = (min_temp + max_temp) / 2.0
    else:
        logger.warning("Using fallback average temperature %.1f C.", _FALLBACK_AVG_TEMP)
        avg_temp = _FALLBACK_AVG_TEMP

    # ---- Which appliances to forecast ---------------------------------------
    appliances = [appliance.name for appliance in profile.appliances]
    if not appliances:
        # Derive [unique, File-ordered] appliance names from the latest slice
        # of the historical dataset when the profile lists none.
        try:
            seen: set[str] = set()
            for rec in get_latest_usage():
                name = rec.get("appliance")
                if name and name not in seen:
                    seen.add(name)
                    appliances.append(name)
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("No appliance list derivable from history: %s", exc)

    if not appliances:
        raise HTTPException(
            status_code=400,
            detail="No appliances to forecast; provide them in the profile.",
        )

    # ---- Predict next-day consumption per appliance -------------------------
    predictions: list[ApplianceForecast] = []
    untrained: list[str] = []
    for name in appliances:
        try:
            row = predict_daily_kwh(
                appliance=name,
                forecast_date=forecast_date,
                avg_temp=avg_temp,
                hh_size=profile.hh_size,
                is_weekend=is_weekend,
            )
            predictions.append(ApplianceForecast.model_validate(row))
        except RuntimeError as exc:
            # Models not trained yet -> tell the caller exactly how to fix it.
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, KeyError):
            untrained.append(name)

    if not predictions:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No trained model for appliance(s): {appliances}. "
                "Train the models first with python Backend/Models/model_loader.py"
            ),
        )

    if untrained:
        logger.warning("No trained model for appliance(s): %s", untrained)

    return predictions