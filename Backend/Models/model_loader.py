"""
Model loader / trainer for the Smart Home Energy Optimizer.

This script is the scriptable version of `Backend/Notebook/ml_model_training.ipynb`.
It reproduces the notebook's forecasting pipeline step by step:

    1. Load the raw smart-home energy readings (500 homes, 10 appliance
       types, ~1 year) from Backend/Dataset/.
    2. Build one clean, equally-spaced DAILY time series PER appliance by
       aggregating every home together (the *global* model, trained per
       appliance). Temperature / weekend / household-size are kept as
       extra regressors.
    3. Fit a Prophet model per appliance with a chronological train/test
       split (no random shuffling => no future leakage).
    4. Forecast the held-out test window and report MAE / RMSE / MAPE.
    5. Persist the fitted models (pickle), the test-window forecasts (CSV),
       a metrics summary (JSON) and a model_registry.json for the inference
       script (`energy_predictor.py`) to consume.

Run it from anywhere in the project:

    python Backend/Models/model_loader.py
"""

# ============================================================================
# Imports
# ============================================================================
import json  # dump metric summaries / registry to disk
import logging  # quieten the noisy cmdstanpy logger (see CONFIG below)
import pickle  # persist the trained Prophet models
import sys  # ensure the project root is importable when run directly
from datetime import UTC, datetime  # UTC stamp used for artifact file names
from pathlib import Path  # cross-platform path handling
from typing import Any

import numpy as np
import pandas as pd
from prophet import Prophet  # the forecasting engine
from sklearn.metrics import (
    mean_absolute_error,  # MAE  (kWh/day)
    mean_absolute_percentage_error,  # MAPE (fraction; *100 -> percent)
    mean_squared_error,  # MSE  (kWh/day)^2 -> RMSE = sqrt(MSE)
)

# Make the project root importable so `Backend.Config.settings` resolves even
# when this module is launched directly (python Backend/Models/model_loader.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Config import settings

# ============================================================================
# Path resolution helpers (locate dataset)
# ============================================================================
# The dataset is found by SEARCHING from the canonical Backend folder (from
# settings.py) plus the possible launch points, so we never trust a fixed CWD.


def resolve_dataset() -> Path:
    """Return the absolute path to the raw CSV, wherever the script is launched."""
    # Candidate launch points: the canonical Backend folder from settings.py,
    # the current working directory, and the directory that contains this script.
    launch_points = [
        settings.BACKEND_DIR,
        Path.cwd(),
        Path(__file__).resolve().parent.parent,
    ]

    for start in launch_points:
        # Upward search (launched from Notebook/ or Backend/) ...
        for level in (start, start.parent, start.parent.parent):
            candidate = level / "Dataset" / "smart_home_energy_consumption_large.csv"
            if candidate.exists():
                return candidate
        # ... plus a downward search (launched from the repo root).
        downward = (
            start / "Backend" / "Dataset" / "smart_home_energy_consumption_large.csv"
        )
        if downward.exists():
            return downward

    # Last resort: relative to the current working directory.
    return Path.cwd() / "Dataset" / "smart_home_energy_consumption_large.csv"


# ============================================================================
# Global configuration & output directories
# ============================================================================

# --- Paths ------------------------------------------------------------------
# Canonical artifact paths are centralized in Backend/Config/settings.py; the
# dataset is located by `resolve_dataset()`.
DATASET_PATH = resolve_dataset()
ARTIFACTS_DIR = settings.ARTIFACTS_DIR
MODELS_DIR = settings.MODELS_DIR
PRED_DIR = settings.PRED_DIR
ACCURACY_DIR = settings.ACCURACY_DIR

# --- Dataset column names ----------------------------------------------------
# TARGET_COL : the numeric column we forecast (total daily energy in kWh).
TARGET_COL = "Energy Consumption (kWh)"

# TEMP_COL   : the temperature header is "Outdoor Temperature (°C)" - it
#              contains a non-ASCII degree sign, so hard-coding the string is
#              fragile against encoding/header differences. We detect it by a
#              name *search* after the CSV is loaded and store the winning
#              header name here. Left None until then.
TEMP_COL = None

# --- Chronological train / test split ----------------------------------------
# Keep the LAST N days of each daily series as a held-out test set.
# A full year of data (~366 days) with 73 test days is roughly an 80/20 split.
TEST_DAYS = 73

# --- Shared Prophet configuration (applied to EVERY appliance) ----------------
#   - yearly_seasonality=False  : we only have ~1 full yearly cycle; a yearly
#     term learned from a single cycle tends to overfit (Prophet expects >= 2).
#   - weekly_seasonality=True   : weekday/weekend behaviour is very visible in
#     household energy usage.
#   - seasonality_mode="additive": seasonal effect scales additively (safe for
#     strictly positive daily energy sums).
PROPHET_CONFIG: dict[str, Any] = {
    "growth": "linear",                 # linear trend with automatic changepoints
    "yearly_seasonality": False,        # not enough data for a stable yearly term
    "weekly_seasonality": True,         # week-day cycle
    "daily_seasonality": False,         # daily aggregates only, no intra-day info
    "seasonality_mode": "additive",
    "changepoint_prior_scale": 0.05,    # moderate trend-changer flexibility
    "seasonality_prior_scale": 10.0,    # default strength of the seasonal terms
    "n_changepoints": 25,               # max number of auto-detected trend breaks
    "interval_width": 0.95,             # width of the uncertainty bands
}

# --- Logging policy -----------------------------------------------------------
# Prophet / cmdstanpy log a LOT of benign INFO text while fitting. Raise the
# cmdstanpy logger threshold so the console stays readable - WITHOUT hiding
# real warnings from pandas / numpy.
logging.getLogger(name="cmdstanpy").setLevel(level=logging.WARNING)

# --- Output directories --------------------------------------------------------
# Create the artifact folders up front (no-op when they already exist).
for directory in (ARTIFACTS_DIR, MODELS_DIR, PRED_DIR, ACCURACY_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Small helpers
# ============================================================================

def split_train_test(series_df, test_days=TEST_DAYS):
    """Return (train, test) - the last `test_days` rows vs. the first ones.

    The split is purely CHRONOLOGICAL: no random shuffling, because
    shuffling would leak the future into training (the classic mistake).
    """
    cut = max(len(series_df) - test_days, 0)
    return series_df.iloc[:cut].copy(), series_df.iloc[cut:].copy()


def to_prophet(frame):
    """Rename/select the columns Prophet expects: ds, y, + the regressors."""
    out = frame[["measurement_datetime", "energy"]].copy()
    out.columns = ["ds", "y"]              # Prophet hard-requires 'ds' and 'y'
    out["temp"] = frame["temp"].values       # weather regressor
    out["is_weekend"] = frame["is_weekend"].values  # weekend/weekday regressor
    out["hh_size"] = frame["hh_size"].values         # household-size regressor
    return out


def mae(y_true, y_pred):
    """Mean Absolute Error (kWh/day) - robust to outliers."""
    return float(mean_absolute_error(y_true, y_pred))


def rmse(y_true, y_pred):
    """Root Mean Squared Error (kWh/day) - penalises large misses harder."""
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mape(y_true, y_pred):
    """Mean Absolute Percentage Error (%) - sklearn returns a fraction."""
    return float(mean_absolute_percentage_error(y_true, y_pred) * 100.0)


def slug(appliance: str) -> str:
    """Turn an appliance name into a safe file name: 'Air Conditioning' -> 'air_conditioning'."""
    return appliance.replace(" ", "_").lower()


def month_to_season(month: int) -> str:
    """Map a calendar month number to its season (used for defensive imputation)."""
    seasons = {
        12: "Winter", 1: "Winter", 2: "Winter",
        3: "Spring", 4: "Spring", 5: "Spring",
        6: "Summer", 7: "Summer", 8: "Summer",
        9: "Fall", 10: "Fall", 11: "Fall",
    }
    return seasons[month]


# ============================================================================
# Training pipeline
# ============================================================================

def load_and_prepare() -> tuple:
    """Read the raw CSV and build the per-appliance daily series.

    Returns
    -------
    df_raw : the cleaned raw DataFrame (one row per event reading).
    daily  : dict {appliance_name: DataFrame[measurement_datetime, energy,
             temp, is_weekend, hh_size]} - the global per-appliance input
             for Prophet.
    """
    global TEMP_COL

    print(f"Loading dataset: {DATASET_PATH.resolve()}")

    # The CSV stores the temperature header as "Outdoor Temperature (°C)".
    # Opening the file with the default UTF-8 codec either raises or garbles
    # the non-ASCII characters, so we force a latin-1 read.
    df_raw = pd.read_csv(DATASET_PATH, encoding="latin-1")

    # Strip accidental leading/trailing whitespace from the column headers.
    df_raw.columns = [col.strip() for col in df_raw.columns]

    # Identify the temperature column by name search (robust against encodings).
    TEMP_COL = next(col for col in df_raw.columns if "Temperature" in col)
    print(f"Temperature column detected -> '{TEMP_COL}'")

    # Robust numeric coercion - guarantees floats even if the CSV stored the
    # values as strings on some platform.
    df_raw[TARGET_COL] = pd.to_numeric(df_raw[TARGET_COL], errors="coerce")
    df_raw[TEMP_COL] = pd.to_numeric(df_raw[TEMP_COL], errors="coerce")

    # Combine the separate Date + Time strings into one clock timestamp.
    # `errors="coerce"` turns malformed strings into NaT instead of failing.
    df_raw["measurement_datetime"] = pd.to_datetime(
        arg=df_raw["Date"].astype(str) + " " + df_raw["Time"].astype(str),
        format="%Y-%m-%d %H:%M",
        errors="coerce",
    )

    # Drop rows with an unparseable timestamp or a missing energy value.
    before = len(df_raw)
    df_raw = df_raw.dropna(subset=["measurement_datetime", TARGET_COL]).copy()
    print(f"Dropped {before - len(df_raw)} malformed rows.")

    # Defensively (re)build any missing categorical Season from the month so
    # downstream grouping / diagnostics never hit NaN.
    df_raw["Season"] = df_raw["Season"].fillna(
        df_raw["measurement_datetime"].dt.month.map(month_to_season)
    )

    # Chronological order makes every downstream slice deterministic.
    df_raw = df_raw.sort_values("measurement_datetime").reset_index(drop=True)

    # ---- Stage 1: per-home daily panel -------------------------------------
    # One row per (home, appliance, date) with daily kWh, average temperature,
    # household size and event count. This is also the foundation a future
    # PER-HOME (personalised) model would use.
    home_daily = (
        df_raw.groupby(
            by=["Home ID", "Appliance Type", df_raw["measurement_datetime"].dt.normalize()],
            as_index=False,
        ).agg(
            daily_kwh=(TARGET_COL, "sum"),        # total kWh for that home+appliance+day
            avg_temp=(TEMP_COL, "mean"),          # mean outdoor temperature that day
            hh_size=("Household Size", "max"),    # household is fixed per home -> max is safe
            events=(TARGET_COL, "count"),         # how many event-readings fed the sum
        )
    ).rename(columns={"measurement_datetime": "Date_per_Home"})

    # Calendar feature used downstream as a regressor (1 on weekends).
    home_daily["day_of_week"] = home_daily["Date_per_Home"].dt.dayofweek  # 0 = Monday
    home_daily["is_weekend"] = (home_daily["day_of_week"] >= 5).astype(int)

    # ---- Stage 2: GLOBAL per-appliance series (SUM over all homes) ---------
    # The *global* model sees the aggregated readings of ALL 500 homes. That
    # pool is much smoother than any single home's events, which is exactly
    # what makes the forecast stable.
    daily = {}
    for app in sorted(home_daily["Appliance Type"].unique()):
        daily[app] = (
            home_daily[home_daily["Appliance Type"] == app]
            .groupby("Date_per_Home", as_index=False)
            .agg(
                energy=("daily_kwh", "sum"),   # total daily kWh across ALL homes
                temp=("avg_temp", "mean"),     # mean outdoor temperature
                is_weekend=("is_weekend", "max"),
                hh_size=("hh_size", "mean"),
            )
            .rename(columns={"Date_per_Home": "measurement_datetime"})
            .sort_values("measurement_datetime")
            .reset_index(drop=True)
        )

    print(f"Loaded {len(df_raw):,} event readings -> "
          f"{len(daily)} appliances x ~{max(len(s) for s in daily.values())} days.")
    return df_raw, daily


def train_and_evaluate(daily: dict) -> tuple:
    """Train one Prophet model per appliance, forecast the test window and
    score it.

    Returns
    -------
    models          : {appliance: {"model", "train", "test"}}
    predictions     : {appliance: DataFrame[measurement_datetime, actual,
                      yhat, yhat_lower, yhat_upper]}
    summary_df      : DataFrame of MAE / RMSE / MAPE per appliance.
    """
    models = {}      # {appliance: {"model", "train", "test"}}
    predictions = {} # {appliance: DataFrame[actual, yhat, yhat_lower, yhat_upper]}

    for app in sorted(daily.keys()):
        frame = daily[app]
        train, test = split_train_test(series_df=frame)   # chronological split
        prophet_df = to_prophet(frame=train)              # ds, y, temp, is_weekend, hh_size

        # Shared hyper-parameters + three registered regressors. The SAME
        # regressor names must appear in the future/prediction frame too.
        model = Prophet(**PROPHET_CONFIG)
        model.add_regressor(name="temp", standardize=True)        # weather-informed demand
        model.add_regressor(name="is_weekend", standardize=True)  # weekend vs weekday
        model.add_regressor(name="hh_size", standardize=True)     # household size
        # NOTE: we deliberately do NOT pass `show_progress=` to `.fit()` -
        # the installed cmdstanpy 1.3.0 does not accept that keyword.
        model.fit(prophet_df)

        models[app] = {"model": model, "train": train, "test": test}
        print(f"{app:16s} trained | train={len(train)}d test={len(test)}d")

    # ---- Forecast the held-out test window -----------------------------------
    # The known future temperatures/regressors from the dataset are fed back
    # in as regressor values (in production they would come from a weather
    # forecast). Prophet outputs the mean `yhat` plus uncertainty bands.
    for app, bag in models.items():
        model = bag["model"]
        test = bag["test"]

        # Future frame needs `ds` + every regressor ('y' is filled by Prophet).
        future = test[["measurement_datetime", "temp", "is_weekend", "hh_size"]].rename(  # ty: ignore[not-subscriptable]
            columns={"measurement_datetime": "ds"}  # Prophet.predict needs literal ds
        )
        fc = model.predict(df=future)

        predictions[app] = pd.DataFrame({
            "measurement_datetime": test["measurement_datetime"].values,  # ty: ignore[not-subscriptable]
            "actual": test["energy"].values,  # ty: ignore[not-subscriptable]
            "yhat": fc["yhat"].values,
            "yhat_lower": fc["yhat_lower"].values,
            "yhat_upper": fc["yhat_upper"].values,
        })

    # ---- Evaluate forecasts (MAE / RMSE / MAPE per appliance) ----------------
    # Energy cannot be negative -> clip the forecast at zero first (a common
    # real-world correction before the error numbers are computed).
    summary = []
    for app, preds in predictions.items():
        actual = preds["actual"].values
        yhat = np.maximum(preds["yhat"].values, 0.0)   # physical lower bound

        summary.append({
            "appliance": app,
            "mae_kwh": round(number=mae(y_true=actual, y_pred=yhat), ndigits=3),
            "rmse_kwh": round(number=rmse(y_true=actual, y_pred=yhat), ndigits=3),
            "mape_pct": round(number=mape(y_true=actual, y_pred=yhat), ndigits=2),
        })

    summary_df = pd.DataFrame(data=summary).sort_values(by="rmse_kwh").reset_index(drop=True)

    print("\nPer-appliance forecast accuracy on the held-out test window:\n")
    print(summary_df.to_string(index=False))
    return models, predictions, summary_df


def persist(models: dict, predictions: dict, summary_df: pd.DataFrame) -> None:
    """Save everything a downstream service needs:

        1. the fitted Prophet objects (pickle)   -> artifacts/Models/
        2. per-appliance test-window forecasts   -> artifacts/Predictions/
        3. a single metrics JSON                 -> artifacts/Accuracy/
        4. a model_registry JSON (per appliance: pickle path, regressors,
           train/test split date, metrics)       -> artifacts/Accuracy/
           powering next-day inference (energy_predictor.py).
    """
    # Using UTC keeps file naming deterministic across environments while
    # avoiding the timezone-naive warning from datetime.now() without tz.
    stamp = datetime.now(tz=UTC).strftime(format="%Y%m%d_%H%M%S")

    # Per-appliance accuracy -> easy lookup dict for the registry records.
    metric_lookup = {}
    for row in summary_df.to_dict(orient="records"):
        metric_lookup[row["appliance"]] = {
            "mae_kwh": row["mae_kwh"],
            "rmse_kwh": row["rmse_kwh"],
            "mape_pct": row["mape_pct"],
        }

    model_registry = {}

    for app, bag in models.items():
        # 1) Persist the fitted Prophet object as a pickle.
        model_path = MODELS_DIR / f"prophet_{slug(appliance=app)}.pkl"
        with open(file=model_path, mode="wb") as fh:
            pickle.dump(obj=bag["model"], file=fh)

        # 2) Save the test-window forecast CSV (actual vs forecast vs bands).
        pred_path = PRED_DIR / f"predictions_{slug(app)}.csv"
        predictions[app].to_csv(pred_path, index=False)

        # 3) Registration record - regressors MUST be the names the model saw
        #    at fit time (the daily series names the weather column 'temp').
        split_date = bag["train"]["measurement_datetime"].max()
        model_registry[app] = {
            "model_path": str(object=model_path.resolve()),
            "regressors": ["temp", "is_weekend", "hh_size"],
            "split_date": str(object=pd.to_datetime(arg=split_date).date()),
            "metrics": metric_lookup[app],
        }

    # 4) Machine-readable accuracy summary for the rest of the platform.
    metrics_path = ACCURACY_DIR / f"metrics_{stamp}.json"
    with open(file=metrics_path, mode="w", encoding="utf-8") as fh:
        json.dump(obj=summary_df.to_dict(orient="records"), fp=fh, indent=2)

    # 5) Save the clean registry with normalised absolute paths.
    registry_path = ACCURACY_DIR / "model_registry.json"
    with open(file=registry_path, mode="w", encoding="utf-8") as fh:
        json.dump(obj=model_registry, fp=fh, indent=2)

    print(f"\nPersisted {len(models)} models + forecasts + metrics + registry to:")
    print(f"  Models    : {MODELS_DIR.resolve()}")
    print(f"  Predictions: {PRED_DIR.resolve()}")
    print(f"  Registry  : {registry_path.resolve()}")


# ============================================================================
# Entry point
# ============================================================================

def main():
    """Run the full training pipeline end to end."""
    print(f"Dataset : {DATASET_PATH.resolve()}")
    print(f"Output  : {ARTIFACTS_DIR.resolve()}\n")

    _, daily = load_and_prepare()
    models, predictions, summary_df = train_and_evaluate(daily)
    persist(models, predictions, summary_df)

    print("\nDone - ready for next-day inference (energy_predictor.py).")


if __name__ == "__main__":
    main()