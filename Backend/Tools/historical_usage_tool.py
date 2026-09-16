"""
Historical usage tool for Agent 1.

Agent-facing wrapper around :mod:`Backend.Services.energy_service`.  Gives
agents the appliance-level energy loads logged on the most recent date in
the historical dataset, e.g.::

    [{"date": "11-08-2026", "appliance": "Air Conditioning",
      "start_time": "19:00", "end_time": "23:00", "mode": "Cooling",
      "kwh_consumed": 5.1, "avg_temp": 32.2,
      "weather_condition": "Hot"}, ...]

The tool performs no CSV parsing itself - all file I/O and date grouping
live in ``energy_service.py``.  Agents hand it only a dataset path (or rely
on the default) and receive plain, JSON-serialisable dictionaries back.

The default ``data/historical/energy_consumption.csv`` path is where the
deployment fleet drops daily exports; when that file is absent,
``energy_service`` automatically falls back to the repository's sample
dataset (``Backend/Dataset/real_appliance_usage.csv``) so the tool works
out of the box in a fresh checkout.
"""

import logging
import sys
from pathlib import Path

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/Tools/historical_usage_tool.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings
from Backend.Services import energy_service

logger = logging.getLogger(name=__name__)


def get_last_usage(
    csv_path: str = "data/historical/energy_consumption.csv",
) -> list[dict]:
    """Retrieve the latest energy usage records from the CSV file.

    Args:
        csv_path: Path to the historical usage CSV.  When the file is not
            present at this location, the service resolves the repository's
            bundled dataset automatically so the call keeps working in a
            fresh checkout or from any working directory.

    Returns:
        A list of appliance-level energy consumption records from the most
        recent date in the dataset.  ``[]`` when the file has no rows.

    Raises:
        FileNotFoundError: if no historical usage CSV can be located.
        ValueError: if the file has rows but none carry a parseable date.
    """
    logger.debug("get_last_usage(csv_path=%r)", csv_path)
    return energy_service.get_latest_usage(csv_path=csv_path)


# ---- Example usage (run directly: python historical_usage_tool.py) ---------
if __name__ == "__main__":
    settings.setup_logging(level="INFO")

    records = get_last_usage()

    if not records:
        print("No historical usage records available.")
    else:
        total = sum(rec.get("kwh_consumed") or 0.0 for rec in records)
        print(f"Latest usage: {len(records)} appliance records "
              f"(total {total:.1f} kWh)")
        for rec in records:
            print(
                f"  {rec.get('appliance', '?'):<18} "
                f"{rec.get('kwh_consumed', float('nan')):>5} kWh  "
                f"{rec.get('start_time', ''):<6} - {rec.get('end_time', ''):<6} "
                f"[{rec.get('mode', '')}]"
            )