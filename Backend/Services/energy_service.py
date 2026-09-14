"""
Energy data service for the agent tools.

Owns all CSV I/O for historical, appliance-level energy-consumption
records.  Agent tools (e.g. ``historical_usage_tool.py``) call the public
functions in this module and receive plain, JSON-serialisable dictionaries
- they never touch file formats, encodings or paths themselves.

Dataset format
--------------
The service expects a CSV with one row per appliance usage event and, at a
minimum, the following columns:

    date, appliance, start_time, end_time, mode,
    kwh_consumed, avg_temp, weather_condition

Dates may be stored as ``YYYY-MM-DD`` or ``M/D/YYYY``.  All records sharing
the highest (most recent) date form the "latest" slice returned by
:func:`get_latest_usage`.

Path resolution
---------------
:func:`resolve_usage_csv` accepts an explicit path but is forgiving when the
file is not at that location (e.g. a deployment-time placeholder).  It then
searches the canonical repository folders - ``Backend/Dataset/`` next to
this package, the current working directory and the repo root - so the
result never depends on where the script was launched.
"""

import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Make the project root importable so `Backend.Config.settings` resolves even
# when this module is launched directly
# (python Backend/Services/energy_service.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings

logger = logging.getLogger(name=__name__)

# Canonical appliance-level dataset shipped with the repository (distinct
# from the event-level ML training file used by model_loader.py).
DEFAULT_DATASET_NAME = "real_appliance_usage.csv"

# Columns holding numeric values are coerced to floats so downstream
# consumers never see a string "5.10" where a number is expected.
NUMERIC_COLUMNS = ("kwh_consumed", "avg_temp")

# Accepted date-cell formats, tried in order when parsing a date column.
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y")


# ============================================================================
# Path resolution (locate the dataset)
# ============================================================================
def resolve_usage_csv(csv_path: str | Path | None = None) -> Path:
    """Return the existing, absolute path to the historical usage CSV.

    Args:
        csv_path: Explicit path to check first.  ``None`` (or an
            unresolvable path) falls through to the repository search.

    Returns:
        ``Path`` to an existing CSV file.

    Raises:
        FileNotFoundError: if ``csv_path`` was given and exists as a file
            but proves unreadable, or if no candidate can be found.
    """
    if csv_path:
        direct = Path(csv_path)
        if direct.is_file():
            return direct
        logger.debug(
            "Configured historical CSV not found at %s; searching project folders.",
            direct.resolve(),
        )

    found = _find_dataset()
    if not found.exists():
        raise FileNotFoundError(f"Historical usage CSV not found: {found}")
    logger.info("Using historical usage dataset: %s", found.resolve())
    return found


def _find_dataset() -> Path:
    """Locate the historical dataset from any working directory.

    Mirrors ``model_loader.resolve_dataset()``: the file is searched for by
    walking upward (``<start>/Dataset/<file>`` at ``<start>`` and up to two
    parent levels) and downward (``<start>/Backend/Dataset/<file>``) from
    several launch points, so a fixed CWD is never assumed.
    """
    filename = DEFAULT_DATASET_NAME
    launch_points = (
        settings.BACKEND_DIR,                          # canonical <project>/Backend
        Path.cwd(),                                    # wherever the user ran it
        Path(__file__).resolve().parent.parent,        # Backend/ (this file: Backend/Services/)
    )

    for start in launch_points:
        # Upward search: launched from Backend/, its parents, or sub-folders.
        for level in (start, start.parent, start.parent.parent):
            candidate = level / "Dataset" / filename
            if candidate.exists():
                return candidate
        # Downward search: launched from the repository root.
        downward = start / "Backend" / "Dataset" / filename
        if downward.exists():
            return downward

    # Last resort: relative to the current working directory.
    return Path.cwd() / "Dataset" / filename


# ============================================================================
# Parsing helpers
# ============================================================================
def _parse_date(value: str) -> datetime | None:
    """Parse a date cell, accepting every format seen in the datasets.

    Returns ``None`` when the string matches none of :data:`_DATE_FORMATS`
    so callers can skip malformed rows instead of crashing.
    """
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


# ============================================================================
# Public API
# ============================================================================
def read_usage_records(csv_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read the historical usage CSV into plain dictionaries.

    Args:
        csv_path: Optional explicit path (see :func:`resolve_usage_csv`).

    Returns:
        One dictionary per row with the CSV column names as keys.  Numeric
        columns are coerced to floats; rows with an empty or missing date
        are dropped with a logged warning rather than killing the read.

    Raises:
        FileNotFoundError: if no existing CSV can be resolved.
    """
    path = resolve_usage_csv(csv_path=csv_path)

    records: list[dict[str, Any]] = []
    # utf-8-sig strips a leading BOM that Excel/Windows exports often add.
    with open(file=path, mode="r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(f=fh)
        for row in reader:
            record = dict(row)

            # Coerce numeric fields (e.g. "4.2") to floats; keep other values
            # untouched so records stay faithful to the source file.
            for col in NUMERIC_COLUMNS:
                raw = record.get(col)
                if raw is not None and str(object=raw).strip():
                    try:
                        record[col] = float(raw)
                    except ValueError:
                        logger.warning(
                            "Non-numeric %r value %r in %s; leaving as-is.", col, raw, path.name
                        )
            records.append(record)

    logger.info("Read %d usage records from %s.", len(records), path.name)
    return records


def get_latest_usage(csv_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return the appliance-level records logged on the most recent date.

    Scans the CSV, groups rows by parsed date and returns the slice whose
    date is the highest (latest) in the file, preserving original row order.

    Args:
        csv_path: Optional explicit path to the historical usage CSV.

    Returns:
        The latest-date records, each with the CSV columns as keys and
        numeric fields already coerced to floats.  ``[]`` when the file has
        no rows at all.

    Raises:
        FileNotFoundError: if no existing CSV can be resolved.
        ValueError: if the file has rows but none carry a parseable date.
    """
    records = read_usage_records(csv_path=csv_path)

    # Group records under their normalised (ISO) date; malformed cells are
    # logged and skipped instead of aborting the whole lookup.
    by_date: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        raw = str(object=rec.get("date", "")).strip()
        parsed = _parse_date(raw)
        if parsed is None:
            logger.warning("Skipping record with unparseable date %r.", raw)
            continue
        by_date.setdefault(parsed.date().isoformat(), []).append(rec)

    if not by_date:
        raise ValueError("No usable dates found in the historical usage CSV.")

    latest_date = max(by_date)
    latest = by_date[latest_date]
    logger.info("Latest usage date: %s (%d appliance records).", latest_date, len(latest))
    return latest

if __name__ == "__main__":
    # Quick sanity check when this module is run directly.
    settings.setup_logging(level="DEBUG")
    latest = get_latest_usage()
    print(f"Latest usage: {len(latest)} appliance records\n")
    print(f"Latest records: {latest}")