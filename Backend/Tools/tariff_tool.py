"""
Tariff lookup tool for the Energy Optimizer Agent.

Agent-facing wrapper that returns the household's time-of-use (TOU)
electricity tariff.  Given a day type ("weekday" | "weekend") and a currency
code it returns a JSON-able tariff table::

    {"currency": "INR", "source": "resident_india_tou",
     "time_of_use": [
        {"start_hour": 6,  "end_hour": 9,  "rate": 9.0,  "label": "peak"},
        {"start_hour": 9,  "end_hour": 18, "rate": 8.5,  "label": "normal"},
        {"start_hour": 18, "end_hour": 23, "rate": 10.5, "label": "peak"},
        {"start_hour": 23, "end_hour": 6,  "rate": 6.0,  "label": "off-peak"}
     ]}

Tariff data
-----------
There is no live tariff provider wired up yet, so this module ships with a
documented *reference* Indian residential TOU table (``REFERENCE_TARIFFS``).
It is intentionally exposed as a plain dict so it can later be swapped for a
real utility/provider API without changing the agent signature.  The Missing
Data policy of the agents depends on one behaviour here: an *unknown* currency
or day type yields an EMPTY ``time_of_use`` list - never a made-up rate.
"""

# ============================================================================
# Imports
# ============================================================================
import logging  # structured, level-aware logging shared with the rest of the app
import sys  # ensure the project root is importable when run directly
from copy import deepcopy  # return a fresh copy so callers cannot mutate the table
from pathlib import Path  # cross-platform path handling
from typing import Any  # typing for the JSON-able return dict

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Tools/tariff_tool.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Centralised configuration (logging policy, ...).
from Backend.Config import settings

# ============================================================================
# Logging
# ============================================================================
# Module-level logger, named after this module so log lines carry the right
# origin tag for filtering in the artifact logs.
logger = logging.getLogger(name=__name__)


# ============================================================================
# Reference tariff data
# ============================================================================
# Indian residential per-unit (INR/kWh) TOU stand-in.  Slots use half-open
# ranges [start_hour, end_hour) and may wrap past midnight (e.g. "23-6" rates
# hours 23..24 and 0..6).  Together the slots of each table cover 24 hours with
# no gaps or overlaps.
REFERENCE_TARIFFS: dict[str, list[dict[str, Any]]] = {
    # Weekday: morning + evening peaks with a cheaper overnight band - the
    # classic shape that makes off-peak shifting worthwhile.
    "weekday": [
        {"start_hour": 6, "end_hour": 9, "rate": 9.0, "label": "peak"},
        {"start_hour": 9, "end_hour": 18, "rate": 8.5, "label": "normal"},
        {"start_hour": 18, "end_hour": 23, "rate": 10.5, "label": "peak"},
        {"start_hour": 23, "end_hour": 6, "rate": 6.0, "label": "off-peak"},
    ],
    # Weekend: flatter profile - no morning/evening peak, just a late-night
    # off-peak band.  Reflects lower commercial load on weekends.
    "weekend": [
        {"start_hour": 6, "end_hour": 23, "rate": 8.0, "label": "normal"},
        {"start_hour": 23, "end_hour": 6, "rate": 6.0, "label": "off-peak"},
    ],
}

# The only currency this reference data is priced in.
_REFERENCE_CURRENCY = "INR"


# ============================================================================
# Public API
# ============================================================================
def get_tod_tariff(day_type: str = "weekday", currency: str = "INR") -> dict[str, Any]:
    """Return the time-of-use tariff table for a given day type and currency.

    Args:
        day_type: ``"weekday"`` or ``"weekend"``.  Any other value yields an
            empty tariff (see Returns).
        currency: ISO-4217 currency code.  Only ``"INR"`` is configured for the
            reference table; anything else yields an empty tariff.

    Returns:
        Dict with ``"currency"``, ``"source"`` and ``"time_of_use"``.  The
        ``time_of_use`` list is EMPTY (and ``"source"`` is ``"none"``) when the
        requested day type or currency is not available, so agents can fall
        back to kWh-only optimization without special-casing errors.

    Example:
        >>> get_tod_tariff("weekday", "INR")["time_of_use"][0]
        {"start_hour": 6, "end_hour": 9, "rate": 9.0, "label": "peak"}
    """
    # ---- Log the request ----------------------------------------------------
    # Debug level: tariff lookups happen once per optimization run, so the
    # detail is only interesting when tracing an agent conversation.
    logger.debug("Tariff requested: day_type=%r currency=%r", day_type, currency)

    # ---- Resolve the table (or an empty one) --------------------------------
    # Normalise casing so "Weekday"/"WEEKEND" and "inr" still match; anything
    # genuinely unknown must NOT guess a rate, so it falls through to empty.
    key = day_type.strip().lower()
    if key in REFERENCE_TARIFFS and currency.strip().upper() == _REFERENCE_CURRENCY:
        return {
            "currency": _REFERENCE_CURRENCY,
            "source": "resident_india_tou_reference",
            "time_of_use": deepcopy(REFERENCE_TARIFFS[key]),
        }

    # Unknown day type / unsupported currency: honest empty tariff for the
    # agent's missing-data path.
    logger.warning(
        "No tariff for day_type=%r currency=%r; returning empty table.",
        day_type,
        currency,
    )
    return {"currency": None, "source": "none", "time_of_use": []}


# ============================================================================
# Example usage (run directly: python tariff_tool.py)
# ============================================================================
if __name__ == "__main__":
    settings.setup_logging(level="INFO")

    for day_type in ("weekday", "weekend", "sunday", "holiday"):
        table = get_tod_tariff(day_type=day_type, currency="INR")
        print(f"[{day_type}] source={table['source']} slots={len(table['time_of_use'])}")
        for slot in table["time_of_use"]:
            print(
                f"    {slot['start_hour']:>2}:00-{slot['end_hour']:>2}:00 "
                f"{slot['label']:<8} {slot['rate']} INR/kWh"
            )

    # Unsupported currency -> empty table (feeds the kWh-only fallback path).
    print("[USD] ", get_tod_tariff(day_type="weekday", currency="USD"))