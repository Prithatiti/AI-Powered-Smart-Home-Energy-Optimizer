"""
Weather tool for the agents.

Provides forecast data for a given day at a given place.  It accepts
coordinates (``latitude`` / ``longitude``), a ``timezone`` and a
``forecast_date``, and returns the day's minimum / maximum temperature,
a human-readable weather condition and the date the forecast applies to.

The tool calls Open-Meteo for the forecast (no API key required) and may
internally use ``geocode_service.py`` to geocode a city name when the agent
hands it a place instead of raw coordinates.

Both the tool and its helper fall back to deterministic values when the
network / upstream service is unavailable, so agents always get a usable,
logged answer instead of an exception.
"""

import datetime as _dt
import logging
import sys
from pathlib import Path
from typing import Any

import requests

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Tools/weather_forecast_tool.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings
from Backend.Config.settings import (
    WEATHER_FORECAST_URL,
    WEATHER_MAX_FORECAST_DAYS,
    WEATHER_TIMEOUT,
    WEATHER_UNKNOWN_CONDITION,
    WMO_CONDITIONS,
)
from Backend.Services.geocode_service import geocode

logger = logging.getLogger(name=__name__)


def _parse_date(forecast_date: str) -> _dt.date:
    """Parse ``YYYY-MM-DD`` and reject dates outside the forecast window."""
    try:
        parsed = _dt.date.fromisoformat(forecast_date)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"forecast_date must be an ISO date 'YYYY-MM-DD', got {forecast_date!r}"
        ) from exc

    if parsed < _dt.date.today():
        raise ValueError(
            f"forecast_date {forecast_date} is in the past; weather tools "
            "only forecast today and up to 16 days ahead."
        )
    if (parsed - _dt.date.today()).days > WEATHER_MAX_FORECAST_DAYS:
        raise ValueError(
            f"forecast_date {forecast_date} is beyond the {WEATHER_MAX_FORECAST_DAYS}-day "
            f"forecast horizon of the weather provider."
        )
    return parsed


def _condition_from_codes(codes: list[int], index: int) -> str:
    """Map an Open-Meteo WMO code to a human-readable condition."""
    if index < 0 or index >= len(codes):
        return WEATHER_UNKNOWN_CONDITION
    return WMO_CONDITIONS.get(codes[index], WEATHER_UNKNOWN_CONDITION)


def _fallback(lat: float, lon: float, date: _dt.date) -> dict[str, Any]:
    """Deterministic values used when the upstream forecast is unreachable."""
    logger.warning(
        msg="Weather service unreachable; returning deterministic fallback values."
    )
    return {
        "latitude": lat,
        "longitude": lon,
        "forecast_date": date.isoformat(),
        "min_temperature_c": -1.0,
        "max_temperature_c": -1.0,
        "weather_condition": "Unavailable",
        "source": "fallback",
    }


def get_weather_forecast(
    latitude: float,
    longitude: float,
    timezone: str,
    forecast_date: str,
) -> dict[str, Any]:
    """Return the weather forecast for one day at the given coordinates.

    Args:
        latitude: Geographic latitude (e.g. ``18.5204``).
        longitude: Geographic longitude (e.g. ``73.8567``).
        timezone: IANA timezone name (e.g. ``"Asia/Kolkata"``). The forecast
            day is interpreted in this timezone.
        forecast_date: ISO date ``"YYYY-MM-DD"`` for which to fetch weather.

    Returns:
        A dict with ``forecast_date``, ``min_temperature_c``,
        ``max_temperature_c``, ``weather_condition`` (plus the input
        ``latitude`` / ``longitude`` and a ``source`` marker).

    Notes:
        * Latitudes outside ``[-90, 90]`` and longitudes outside
          ``[-180, 180]`` raise ``ValueError``.
        * On network errors the tool logs a warning and returns deterministic
          placeholder values rather than raising.
    """

    # Normalize the requested forecast date in a timezone-aware way. If the
    # agent doesn't supply a date, fall back to the next day using UTC, which
    # satisfies the naive `datetime.now()` lint warning.
    if not forecast_date:
        forecast_date = (
            _dt.datetime.now(tz=_dt.timezone.utc) + _dt.timedelta(days=1)
        ).date().isoformat()

    lat = float(latitude)
    lon = float(longitude)
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude must be in [-90, 90], got {latitude!r}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"longitude must be in [-180, 180], got {longitude!r}")

    date = _parse_date(forecast_date)
    logger.info(
        "Fetching weather for lat=%s lon=%s tz=%r date=%s",
        lat,
        lon,
        timezone,
        date.isoformat(),
    )

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_min,temperature_2m_max,weather_code",
        "timezone": timezone,
        "start_date": date.strftime(format="%Y-%m-%d"),
        "end_date": date.strftime(format="%Y-%m-%d"),
    }
    headers = {"User-Agent": settings.WEATHER_USER_AGENT}

    try:
        resp = requests.get(
            url=WEATHER_FORECAST_URL,
            params=params,
            headers=headers,
            timeout=WEATHER_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        return _fallback(lat, lon, date)

    data = resp.json()
    daily = data.get("daily", {}) or {}
    times = daily.get("time", [])
    if not times:
        logger.warning("Open-Meteo returned no daily series; using fallback.")
        return _fallback(lat, lon, date)

    # Index 0 is the requested day because start_date == end_date == forecast_date.
    codes = daily.get("weather_code", []) or []
    condition = _condition_from_codes(codes, index=0)

    return {
        "latitude": lat,
        "longitude": lon,
        "forecast_date": date.isoformat(),
        "min_temperature_c": _first_or(daily.get("temperature_2m_min", []), None),
        "max_temperature_c": _first_or(daily.get("temperature_2m_max", []), None),
        "weather_condition": condition,
        "source": "open-meteo",
    }


def _first_or(seq: list, default: Any) -> Any:
    """Return ``seq[0]`` (used for the one requested day), else ``default``."""
    return seq[0] if seq else default


# ---- Tool facade for agents -------------------------------------------------
# A single callable with a plain-JSON payload keeps agent bridge code simple.
def weather_tool(
    latitude: float, longitude: float, timezone: str, forecast_date: str
) -> dict[str, Any]:
    """Agent-facing wrapper around :func:`get_weather_forecast`.

    Convenience for tools runners that expect one function with a JSON-able
    signature.  Identical validation and output as the underlying function.
    """
    return get_weather_forecast(
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        forecast_date=forecast_date,
    )


# ---- Example usage (run directly: python weather_tool.py) ------------------
if __name__ == "__main__":
    settings.setup_logging(level="INFO")

    # Resolve a city via the geocoding service, then forecast the next day.
    try:
        places = geocode(city="Pune", limit=1)
    except requests.RequestException as exc:
        places = []
        print(f"Geocoding failed: {exc}")

    target_date = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()

    if places:
        place = places[0]
        print(f"Using {place['display_name']} (lat={place['lat']}, lon={place['lon']})")
        forecast = weather_tool(
            latitude=place["lat"],
            longitude=place["lon"],
            timezone="Asia/Kolkata",
            forecast_date=target_date,
        )
    else:
        print("No location resolved; demonstrating direct coordinate lookup for Pune.")
        forecast = weather_tool(
            latitude=18.5204,
            longitude=73.8567,
            timezone="Asia/Kolkata",
            forecast_date=target_date,
        )

    print(f"\nForecast for {forecast['forecast_date']}:")
    print(
        f"  min / max : {forecast['min_temperature_c']} / {forecast['max_temperature_c']} C"
    )
    print(f"  condition : {forecast['weather_condition']}")
    print(f"  source    : {forecast['source']}")
