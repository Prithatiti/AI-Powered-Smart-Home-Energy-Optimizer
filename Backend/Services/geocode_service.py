"""
Geocoding service for agents.

Resolves a free-text place name (e.g. ``"Pune"``) into structured locations
using the Nominatim (OpenStreetMap) API.  Each match carries a
human-readable ``display_name``, geographic coordinates (``lat`` / ``lon``)
and the OSM ``type`` / ``class`` so agents can pick the most relevant
candidate.

Usage policy
------------
Nominatim is free, but its operators ask you to be gentle:

  * Send a descriptive ``User-Agent`` / ``Referer`` so they can contact you
    if something goes wrong.  This module sets it once from
    ``settings.WEATHER_USER_AGENT``.
  * Keep to at most ~1 request per second.  Requests are paced by sleeping
    ``MIN_INTERVAL`` seconds between calls (see ``NominatimClient._throttle``);
    agents that batch lookups share one client so the throttle actually
    applies across the whole process.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests

# Make the project root importable so `Backend.Config.settings` resolves even
# when this module is launched directly
# (python Backend/Services/geocode_service.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings

logger = logging.getLogger(name=__name__)

# Identifies this app to the Nominatim operators. Configured centrally in
# Backend/Config/settings.py (env var: WEATHER_USER_AGENT).
USER_AGENT = settings.WEATHER_USER_AGENT
# Nominatim's public API allows roughly one request per second; stay under it.
MIN_INTERVAL = 1.1
# How long a single geocoding HTTP request may take before giving up, in s.
TIMEOUT = 10

# ============================================================================
# Data model
# ============================================================================


class GeoLocation:
    """A single geocoding result returned by Nominatim.

    Attributes capture the fields agents care about: a human-readable
    ``display_name`` plus the geographic coordinates (``lat`` / ``lon``).
    ``osm_type`` / ``osm_class`` record the OSM object (e.g. ``city`` /
    ``place``, ``residential`` / ``highway``) and are kept as parsed strings.
    """

    __slots__ = ("display_name", "lat", "lon", "osm_class", "osm_type")

    def __init__(
        self,
        display_name: str,
        lat: float,
        lon: float,
        osm_type: str,
        osm_class: str,
    ) -> None:
        self.display_name = display_name
        self.lat = lat
        self.lon = lon
        self.osm_type = osm_type
        self.osm_class = osm_class

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"GeoLocation(display_name={self.display_name!r}, lat={self.lat!r}, "
            f"lon={self.lon!r}, type={self.osm_type!r}, class={self.osm_class!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain dictionary form, ready for JSON serialisation for agents."""
        return {
            "display_name": self.display_name,
            "lat": self.lat,
            "lon": self.lon,
            "type": self.osm_type,
            "class": self.osm_class,
        }


# ============================================================================
# HTTP client
# ============================================================================


class NominatimClient:
    """Thin, rate-limited client for the Nominatim ``/search`` endpoint.

    A fresh connection is opened per lookup but a single client keeps a
    class-level timestamp so repeated lookups are spaced by ``MIN_INTERVAL``
    seconds regardless of how many client instances were created.
    """

    # Most recent request timestamp, shared across every instance so the
    # throttle is honoured process-wide, not just per client.
    _last_request_ts: float = 0.0

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.WEATHER_GEOCODING_URL
        self.session = requests.Session()
        # A descriptive User-Agent is required by the Nominatim usage policy.
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _throttle(self) -> None:
        """Wait long enough that we never blast Nominatim with rapid calls."""
        now = time.monotonic()
        elapsed = now - NominatimClient._last_request_ts
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        NominatimClient._last_request_ts = time.monotonic()

    def search(self, query: str, limit: int = 5) -> list[GeoLocation]:
        """Return up to ``limit`` locations matching ``query`` (case-insensitive)."""
        self._throttle()

        params = {
            "q": query,
            "format": "json",
            "limit": max(1, int(limit)),
            "addressdetails": 0,
        }
        logger.debug("Nominatim lookup q=%r limit=%s", query, params["limit"])

        resp = self.session.get(url=self.base_url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()

        results: list[GeoLocation] = []
        for item in resp.json():
            try:
                results.append(
                    GeoLocation(
                        display_name=item.get("display_name", ""),
                        lat=float(item["lat"]),
                        lon=float(item["lon"]),
                        osm_type=str(object=item.get("type", "")),
                        osm_class=str(object=item.get("class", "")),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Dropping malformed Nominatim result %r: %s", item, exc)
        return results


# Shared client so every geocode in the process is throttled as one.
_shared_client = NominatimClient()

# ============================================================================
# Public API
# ============================================================================


def geocode(city: str, limit: int = 5) -> list[dict[str, Any]]:
    """Geocode a city name into a list of matching locations.

    Args:
        city: Free-text place name, e.g. ``"Pune"``.
        limit: Maximum number of candidates to return (default 5).

    Returns:
        List of dictionaries, each with ``display_name``, ``lat``, ``lon``
        plus the Nominatim ``type`` and ``class``.  Empty when nothing matches.

    Raises:
        requests.HTTPError: Nominatim unreachable or rejected the request.
    """
    if not city or not city.strip():
        raise ValueError("City name must be a non-empty string.")

    logger.info("Geocoding city=%r", city)
    results = _shared_client.search(query=city.strip(), limit=limit)

    if not results:
        logger.warning("No geocoding results for city=%r", city)
        return []

    for location in results:
        logger.debug(
            "  candidate: %s | lat=%s lon=%s (%s/%s)",
            location.display_name,
            location.lat,
            location.lon,
            location.osm_type,
            location.osm_class,
        )
    return [location.to_dict() for location in results]


# ---- Example usage (run directly: python geocode_service.py) ---------------
if __name__ == "__main__":
    from Backend.Config import settings as _settings

    _settings.setup_logging(level="INFO")

    for place in ("Pune", "Delhi"):
        try:
            matches = geocode(city=place)
        except requests.RequestException as exc:
            print(f"Geocoding failed for {place!r}: {exc}")
        else:
            print(f"Locations for {place!r}:")
            for match in matches:
                print(
                    f"  - {match['display_name']} "
                    f"(lat={match['lat']}, lon={match['lon']}, "
                    f"type={match['type']}, class={match['class']})"
                )