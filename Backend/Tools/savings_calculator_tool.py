"""
Energy-cost calculation tools for the Energy Optimizer Agent.

Two deterministic, JSON-able pricing helpers the optimizer agent uses to turn
"forecast kWh + a tariff" into real money figures:

* :func:`estimate_run_cost` - price ``kwh`` of running an appliance across a
  time window ``[start_hour, end_hour)`` by splitting the energy across every
  tariff slot the window overlaps::

      {"appliance": "Air Conditioning", "kwh": 10.0, "start_hour": 19,
       "end_hour": 23, "window_cost": 100.0, "peak_kwh": 10.0,
       "average_rate": 10.0}

* :func:`reschedule_comparison` - compare the cost of the current running
  window against a suggested alternative window and report the saving::

      {"appliance": "Air Conditioning", "current_cost": 100.0,
       "suggested_cost": 60.0, "savings_cost": 40.0, "savings_pct": 40.0,
       "peak_kwh_shifted": 10.0, "average_rate_before": 10.0,
       "average_rate_after": 6.0}

Window handling
---------------
Tariff slots may *wrap* past midnight (e.g. ``23:00-06:00``).  Appliance
windows behave the same way, so ``start_hour >= end_hour`` means an
overnight run (e.g. 23:00-03:00 covers hours 23, 0, 1, 2).  All maths is plain
floating point on the tariff numbers given - this module never looks up or
invents a rate by itself.  When the tariff has no applicable slot for an hour
(a malformed table), that hour is priced at 0.0 and ``window_cost`` is left
unaffected.
"""

# ============================================================================
# Imports
# ============================================================================
import logging  # structured, level-aware logging shared with the rest of the app
import sys  # ensure the project root is importable when run directly
from pathlib import Path  # cross-platform path handling
from typing import Any  # typing for the JSON-able return dict

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Tools/savings_calculator_tool.py).
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

# ----------------------------------------------------------------------------
# Private helpers
# ----------------------------------------------------------------------------


def _rate_at_hour(hour: int, time_of_use: list[dict[str, Any]]) -> tuple[float, str]:
    """Return the (rate, label) applicable at ``hour`` from ``time_of_use``.

    Understands wrap-around slots (``start_hour > end_hour``).  Returns
    ``(0.0, "none")`` for hours with no applicable slot.  ``hour`` must be in
    ``0..23``.
    """
    for slot in time_of_use:
        start = int(slot["start_hour"])
        end = int(slot["end_hour"])
        # Normal wrap slot: e.g. 6-18 -> hour 8 matches; 23-6 -> hour 0 or 23.
        if start < end:
            matches = start <= hour < end
        else:
            matches = hour >= start or hour < end
        if matches:
            return float(slot["rate"]), str(slot.get("label", "normal"))
    logger.warning("No tariff slot for hour %d; pricing at 0.0.", hour)
    return 0.0, "none"


def _window_hours(start_hour: int, end_hour: int) -> list[int]:
    """Expand a window into the list of hours it covers (supporting overnight).

    ``[start, end)``; if ``end <= start`` the window wraps through midnight.
    """
    if end_hour <= start_hour:
        return list(range(start_hour, 24)) + list(range(0, end_hour))
    return list(range(start_hour, end_hour))


# ============================================================================
# Public API
# ============================================================================
def estimate_run_cost(
    appliance: str,
    kwh: float,
    start_hour: int,
    end_hour: int,
    tariff_table: dict[str, Any],
) -> dict[str, Any]:
    """Price ``kwh`` of an appliance running across a window against a tariff.

    Args:
        appliance: Appliance name, echoed through for traceability.
        kwh: Energy the appliance is expected to draw during the window.
        start_hour: Window start hour (0-23, inclusive).
        end_hour: Window end hour (1-24; ``<= start_hour`` means an overnight
            run wrapping through midnight).
        tariff_table: Dict from :func:`Backend.Tools.tariff_tool.get_tod_tariff`,
            i.e. containing ``"time_of_use"``; or ``None``/empty for no tariff.

    Returns:
        Dict with ``window_cost`` (currency units), ``peak_kwh`` (the portion
        of ``kwh`` consumed in ``"peak"`` labelled slots) and ``average_rate``
        (``window_cost / kwh``), plus the echoed inputs.

    Raises:
        ValueError: for out-of-range hours, non-positive ``kwh`` or an empty
            window.

    Note:
        With no tariff (empty ``time_of_use``) the cost is ``0.0`` - the agent
        should treat that as "pricing unavailable" and fall back to kWh-only.
    """
    # ---- Validate inputs ----------------------------------------------------
    if kwh <= 0:
        raise ValueError(f"kwh must be positive; got {kwh!r}.")
    for name, value in (("start_hour", start_hour), ("end_hour", end_hour)):
        if not 0 <= int(value) <= 24:
            raise ValueError(f"{name} must be within 0-24; got {value!r}.")

    # ---- Expand the window into hours --------------------------------------
    # Overnight runs (end <= start) wrap; a genuinely zero-length window has no
    # hours to price and is rejected rather than silently dividing by zero.
    hours = _window_hours(int(start_hour), int(end_hour))
    if not hours:
        raise ValueError(
            f"Empty run window [{start_hour} - {end_hour}] cannot be priced."
        )

    # ---- Price each hour proportionally -------------------------------------
    # Assumption: the appliance draws energy evenly across its run window, so
    # each hour costs kwh / len(hours) at that hour's tariff rate.  Slots come
    # straight from the tariff table - no rate is invented here.
    hours_in_window = len(hours)
    hourly_kwh = kwh / hours_in_window
    time_of_use = (tariff_table or {}).get("time_of_use", [])

    peak_kwh = 0.0
    window_cost = 0.0
    for hour in hours:
        rate, label = _rate_at_hour(hour, time_of_use)
        if label == "peak":
            peak_kwh += hourly_kwh
        window_cost += hourly_kwh * rate

    result = {
        "appliance": appliance,
        "kwh": kwh,
        "start_hour": int(start_hour),
        "end_hour": int(end_hour),
        "window_cost": round(window_cost, 4),
        "peak_kwh": round(peak_kwh, 4),
        "average_rate": round(window_cost / kwh, 4),
    }
    logger.info(
        "Estimated %s (%.1f kWh, %02d:00-%02d:00) -> cost %.2f, peak %.2f kWh.",
        appliance,
        kwh,
        result["start_hour"],
        result["end_hour"],
        result["window_cost"],
        result["peak_kwh"],
    )
    return result


def reschedule_comparison(
    appliance: str,
    kwh: float,
    current_start: int,
    current_end: int,
    suggested_start: int,
    suggested_end: int,
    tariff_table: dict[str, Any],
) -> dict[str, Any]:
    """Compare the cost of the current run window against a suggested one.

    Args:
        appliance: Appliance name, echoed through for traceability.
        kwh: Energy the appliance is expected to draw in either window.
        current_start / current_end: Current (baseline) running window.
        suggested_start / suggested_end: Candidate alternative window.
        tariff_table: Tariff dict from ``get_tod_tariff``; ``None``/empty means
            no tariff is available (both windows price at 0.0).

    Returns:
        Dict with ``current_cost``, ``suggested_cost``, ``savings_cost``
        (= current - suggested), ``savings_pct`` and the shifted peak kWh plus
        average rates before/after.  Values are derived purely via
        :func:`estimate_run_cost`.

    Raises:
        ValueError: for out-of-range hours, non-positive ``kwh`` or an empty
            window.
    """
    # Price both windows through the same helper so the two are comparable and
    # the reporting of window_cost / peak_kwh / average_rate stays consistent.
    current = estimate_run_cost(
        appliance=appliance,
        kwh=kwh,
        start_hour=current_start,
        end_hour=current_end,
        tariff_table=tariff_table,
    )
    suggested = estimate_run_cost(
        appliance=appliance,
        kwh=kwh,
        start_hour=suggested_start,
        end_hour=suggested_end,
        tariff_table=tariff_table,
    )

    current_cost = current["window_cost"]
    suggested_cost = suggested["window_cost"]
    savings_cost = round(current_cost - suggested_cost, 4)
    # Percentage guard: with no tariff both costs are 0 -> report 0% rather
    # than a division error, and let the agent decide what that means.
    savings_pct = round(savings_cost / current_cost * 100, 2) if current_cost else 0.0

    result = {
        "appliance": appliance,
        "current_cost": current_cost,
        "suggested_cost": suggested_cost,
        "savings_cost": savings_cost,
        "savings_pct": savings_pct,
        "peak_kwh_shifted": round(current["peak_kwh"] - suggested["peak_kwh"], 4),
        "average_rate_before": current["average_rate"],
        "average_rate_after": suggested["average_rate"],
    }
    logger.info(
        "Reschedule %s %02d:00-%02d:00 -> %02d:00-%02d:00: saves %.2f (%.1f%%).",
        appliance,
        current_start,
        current_end,
        suggested_start,
        suggested_end,
        savings_cost,
        savings_pct,
    )
    return result


# ============================================================================
# Example usage (run directly: python savings_calculator_tool.py)
# ============================================================================
if __name__ == "__main__":
    settings.setup_logging(level="INFO")

    from Backend.Tools.tariff_tool import get_tod_tariff

    tariff = get_tod_tariff(day_type="weekday", currency="INR")

    # AC runs 19:00-23:00 on the 18:00 peak rate; shift it to after midnight.
    current = estimate_run_cost(
        appliance="Air Conditioning", kwh=10.0, start_hour=19, end_hour=23,
        tariff_table=tariff,
    )
    print("AC current window:", current)

    comparison = reschedule_comparison(
        appliance="Air Conditioning", kwh=10.0,
        current_start=19, current_end=23,
        suggested_start=23, suggested_end=3,
        tariff_table=tariff,
    )
    print("Reschedule:", comparison)

    # Washing machine 08:30 *really* covers 08:00-09:00 peak morning slot.
    wm = estimate_run_cost(
        appliance="Washing Machine", kwh=1.6, start_hour=8, end_hour=9,
        tariff_table=tariff,
    )
    print("Washing machine window:", wm)

    # No tariff -> cost 0.0 (feeds the kWh-only fallback path).
    none_tariff = {"currency": None, "source": "none", "time_of_use": []}
    print("No tariff:", estimate_run_cost(
        appliance="Fridge", kwh=3.0, start_hour=0, end_hour=24,
        tariff_table=none_tariff,
    ))