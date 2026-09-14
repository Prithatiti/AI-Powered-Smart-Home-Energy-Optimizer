"""
Next-day energy forecast using the trained Prophet models.

Loads the model registry produced by the training pipeline
(``Backend/Artifacts/Accuracy/model_registry.json``), then predicts the
expected energy consumption for a chosen appliance using its trained
Prophet model.

Workflow
--------
1. The training pipeline (:doc:`model_loader`) fits one Prophet model per
   appliance and persists a registry describing where each model lives,
   which regressors it expects (``temp``, ``hh_size``, ``is_weekend``) and
   how accurate it was on the held-out test window.
2. This module reads that registry once at import time and exposes
   :func:`predict_next_day`, which turns one day's expected context
   (temperature, household size, weekday/weekend) into a point forecast
   plus a 95% confidence band.

The public entry point ``predict_next_day`` is consumed by the agent-facing
tool ``Backend/Tools/ml_prediction_tool.py``.
"""

# ============================================================================
# Imports
# ============================================================================
import json  # read the model registry produced by the training pipeline
import pickle  # unpickle the serialised Prophet model objects
import sys  # ensure the project root is importable when run directly
from pathlib import Path  # cross-platform path handling
from typing import Any  # typing for the JSON-able forecast dict

import pandas as pd  # build the Prophet "future" frame (ds + regressors)

# Make the project root importable so `Backend.Config.settings` resolves even
# when this module is launched directly
# (python Backend/Models/energy_predictor.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Centralised configuration (artifact paths live here).
from Backend.Config import settings

# ============================================================================
# Paths
# ============================================================================
# Artifact paths are centralized in Backend/Config/settings.py so this module
# never hardcodes a location - the registry always points into the same
# Accuracy/ folder the training pipeline wrote.
ACCURACY_DIR = settings.ACCURACY_DIR
REGISTRY_FILE = settings.ACCURACY_DIR / "model_registry.json"

# ============================================================================
# Model registry (loaded once at module import)
# ============================================================================
# The registry maps each appliance name to its model path, the regressors it
# was trained with, the train/test split date and the accuracy metrics.  It
# is created by `model_loader.py` - there is no model without a registry.
#
# Validation happens HERE (import time) on purpose: if the registry is
# missing, importing this module fails fast with a clear message instead of
# letting every later call blow up with a confusing "file not found".
if not REGISTRY_FILE.exists():
    raise FileNotFoundError(
        f"Model registry file not found: {REGISTRY_FILE}. "
        "Run `model_loader.py` first."
    )

# Load the registry into a dict:
#   {appliance_name: {"model_path", "split_date", "regressors", "metrics", ...}}
with open(file=REGISTRY_FILE, mode="r", encoding="utf-8") as fh:
    model_registry = json.load(fp=fh)


# ============================================================================
# Public API
# ============================================================================
def _get_model(appliance: str):
    """Load the trained Prophet model for `appliance` from disk.

    Reads the pickle path stored in the registry for `appliance` and returns
    a fully reconstructed Prophet model, ready for ``.predict()``.
    """
    with open(file=model_registry[appliance]["model_path"], mode="rb") as fh:
        return pickle.load(file=fh)


def predict_next_day(
    appliance: str,
    ds_next: str,          # "YYYY-MM-DD"
    avg_temp: float,       # expected outdoor temperature that day (Celsius)
    hh_size: float,        # expected household size
    is_weekend: int,       # 0 (weekday) or 1 (weekend)
) -> dict[str, Any]:
    """Return the point forecast + 95% band for the next day of `appliance`.

    Args:
        appliance: Appliance name, exactly as trained (see the registry keys).
        ds_next: Forecast date ``"YYYY-MM-DD"``.
        avg_temp: Expected average outdoor temperature that day, in Celsius.
        hh_size: Expected household size (number of occupants).
        is_weekend: ``1`` for a weekend day, ``0`` for a weekday.

    Returns:
        Dict with ``appliance``, ``ds`` (forecast date), ``yhat`` (predicted
        kWh) plus the ``yhat_lower`` / ``yhat_upper`` 95% confidence band,
        and the ``model_path`` / ``split_date`` provenance from the registry.

    Raises:
        KeyError: if ``appliance`` has no trained model in the registry.
    """
    # ---- Validate the appliance -------------------------------------------
    # A wrong name would surface later as a confusing pickle/KeyError deep
    # inside the registry, so fail fast and tell the caller what IS available.
    if appliance not in model_registry:
        raise KeyError(
            f"'{appliance}' is not in the model registry. "
            f"Available: {sorted(model_registry)}"
        )

    # ---- Load the trained model ---------------------------------------------
    model = _get_model(appliance)

    # ---- Build the Prophet "future" frame -----------------------------------
    # Prophet requires one dataframe row per forecast day with a column 'ds'
    # (the date) PLUS exactly the regressor names the model was fitted with
    # (temp, hh_size, is_weekend).  Column names and dtypes must match the
    # training data - a mismatch raises inside Prophet.
    future = pd.DataFrame({
        "ds": pd.to_datetime([ds_next]),
        "temp": [float(avg_temp)],
        "hh_size": [float(hh_size)],
        "is_weekend": [int(is_weekend)],
    })

    # One row per requested day; we asked for exactly one date, so index 0.
    fc = model.predict(future)

    # ---- Assemble the JSON-able result --------------------------------------
    # Surface the point estimate, the uncertainty band and the registry
    # provenance so consumers can both quote the forecast and trace it back
    # to the model artifact that produced it.
    return {
        "appliance": appliance,
        "ds": str(object=pd.to_datetime(arg=ds_next).date()),
        "yhat": float(fc["yhat"].iloc[0]),
        "yhat_lower": float(fc["yhat_lower"].iloc[0]),
        "yhat_upper": float(fc["yhat_upper"].iloc[0]),
        "model_path": model_registry[appliance]["model_path"],
        "split_date": model_registry[appliance]["split_date"],
    }


# ============================================================================
# Example usage (run directly: python energy_predictor.py)
# ============================================================================
if __name__ == "__main__":
    # Standalone demo: forecast one appliance for tomorrow, print the result
    # and persist it to Artifacts/Accuracy/ so the registry consumer has a
    # concrete preview of the model output.
    appliance = "Fridge"
    # "Tomorrow" computed from today's (UTC) date via pandas, so the demo
    # never needs a live clock read and stays deterministic.
    ds_next = str(object=(pd.Timestamp.today().normalize() + pd.Timedelta(days=1)).date())
    avg_temp = 25.0  # expected average temperature in Celsius
    hh_size = 3.0    # expected household size
    is_weekend = 0   # 0 for weekday, 1 for weekend

    try:
        forecast = predict_next_day(appliance, ds_next, avg_temp, hh_size, is_weekend)

    # Depending on the environment, one of these may be raised; report it to
    # the user instead of crashing with an opaque traceback.
    except (FileNotFoundError, KeyError, ValueError, TypeError) as e:
        print(f"Error during prediction: {e}")

    else:
        print("Prediction successful!\n")
        print(f"Next-day forecast for {forecast['appliance']} on {forecast['ds']}:")
        print(
            f"  predicted : {forecast['yhat']:8.2f} kWh   (95% CI "
            f"{forecast['yhat_lower']:.2f} - {forecast['yhat_upper']:.2f})"
        )
        print(f"  model     : {forecast['model_path']}")

        # Persist the same forecast the agent tool would return, as a preview
        # artifact for operators / tests.
        with open(
            file=ACCURACY_DIR / "next_day_forecast.json", mode="w", encoding="utf-8"
        ) as fp:
            json.dump(obj=forecast, fp=fp, indent=2)