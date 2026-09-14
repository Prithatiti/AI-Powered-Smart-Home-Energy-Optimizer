"""
Next-day energy forecast using the trained Prophet models.

Loads the model registry produced by the training pipeline
(Backend/Artifacts/Accuracy/model_registry.json), then predicts the
expected energy consumption for a chosen appliance using its Prophet model.
"""

import json
import pickle
from pathlib import Path
from typing import Any

import pandas as pd

# ---- Paths ------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent  # <project>/Backend
ARTIFACTS_DIR = BACKEND_DIR / "Artifacts"
ACCURACY_DIR = ARTIFACTS_DIR / "Accuracy"
REGISTRY_FILE = ACCURACY_DIR / "model_registry.json"

# ---- Load the model registry ------------------------------------------------
# The registry maps each appliance name to its model path, regressors,
# split date and accuracy metrics. It is created by `train_models.py`.
if not REGISTRY_FILE.exists():
    raise FileNotFoundError(
        f"Model registry file not found: {REGISTRY_FILE}. "
        "Run `model_loader.py` first."
    )

# Load the registry into a dict: {appliance_name: {model_path, split_date, ...}}
with open(file=REGISTRY_FILE, mode="r", encoding="utf-8") as fh:
    model_registry = json.load(fh)


def _get_model(appliance: str):
    """Load the trained Prophet model for `appliance` from disk."""
    with open(file=model_registry[appliance]["model_path"], mode="rb") as fh:
        return pickle.load(file=fh)


def predict_next_day(
    appliance: str,
    ds_next: str,          # "YYYY-MM-DD"
    avg_temp: float,       # expected outdoor temperature that day (Celsius)
    hh_size: float,        # expected household size
    is_weekend: int,       # 0 (weekday) or 1 (weekend)
) -> dict[str, Any]:
    """Return the point forecast + 95% band for the next day of `appliance`."""
    if appliance not in model_registry:
        raise KeyError(
            f"'{appliance}' is not in the model registry. "
            f"Available: {sorted(model_registry)}"
        )

    model = _get_model(appliance)

    # Prophet needs one dataframe row per forecast day with 'ds' plus the exact
    # regressor names used during training (temp, hh_size, is_weekend).
    future = pd.DataFrame({
        "ds": pd.to_datetime([ds_next]),
        "temp": [float(avg_temp)],
        "hh_size": [float(hh_size)],
        "is_weekend": [int(is_weekend)],
    })

    fc = model.predict(future)  # one row per requested day

    return {
        "appliance": appliance,
        "ds": str(pd.to_datetime(ds_next).date()),
        "yhat": float(fc["yhat"].iloc[0]),
        "yhat_lower": float(fc["yhat_lower"].iloc[0]),
        "yhat_upper": float(fc["yhat_upper"].iloc[0]),
        "model_path": model_registry[appliance]["model_path"],
        "split_date": model_registry[appliance]["split_date"],
    }


# ---- Example usage (run directly: python energy_predictor.py) --------------
if __name__ == "__main__":
    appliance = "Fridge"
    ds_next = str(object=(pd.Timestamp.today().normalize() + pd.Timedelta(days=1)).date())
    avg_temp = 25.0  # expected average temperature in Celsius
    hh_size = 3.0    # expected household size
    is_weekend = 0   # 0 for weekday, 1 for weekend

    try:
        forecast = predict_next_day(appliance, ds_next, avg_temp, hh_size, is_weekend)
    
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

        with open(
            file=ACCURACY_DIR / "next_day_forecast.json", mode="w", encoding="utf-8"
        ) as fp:
            json.dump(obj=forecast, fp=fp, indent=2)