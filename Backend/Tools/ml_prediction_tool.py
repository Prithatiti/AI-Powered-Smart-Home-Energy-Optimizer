"""
ML prediction tool for the Energy Analysis Agent.

Agent-facing wrapper around
:func:`Backend.Models.energy_predictor.predict_next_day`.  Given an
appliance, a target date and the expected context for that day (outdoor
temperature, household size, weekday/weekend), it returns the trained
Prophet model's forecast: the predicted next-day energy consumption in kWh
plus the 95% confidence band::

    {"appliance": "Fridge", "ds": "2026-09-15", "yhat": 3.21,
     "yhat_lower": 2.11, "yhat_upper": 4.31, "model_path": "...", ...}

The tool performs no model loading or math itself - all of that lives in
``energy_predictor.py``.  It exists so the agent bridge has a single,
well-documented callable with a plain-JSON signature.

Model availability
------------------
``predict_daily_kwh()`` requires the trained artifacts produced by the
training pipeline:

    python Backend/Models/model_loader.py

If the model registry is missing, the tool raises a clear ``RuntimeError``
saying so instead of a confusing import-time traceback.
"""

# ============================================================================
# Imports
# ============================================================================
import logging  # structured, level-aware logging shared with the rest of the app
import sys  # ensure the project root is importable when run directly
from pathlib import Path  # cross-platform path handling
from typing import Any  # typing for the JSON-able return dict

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/Tools/ml_prediction_tool.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Centralised configuration (logging policy, artifact paths, ...).
from Backend.Config import settings

# ============================================================================
# Logging
# ============================================================================
# Module-level logger, named after this module so log lines carry the right
# origin tag for filtering in the artifact logs.
logger = logging.getLogger(name=__name__)


# ============================================================================
# Public API
# ============================================================================
def predict_daily_kwh(
    appliance: str,
    forecast_date: str,
    avg_temp: float,
    hh_size: float,
    is_weekend: int,
) -> dict[str, Any]:
    """Forecast the total daily energy consumption of an appliance.

    Delegates to :func:`Backend.Models.energy_predictor.predict_next_day`,
    which loads the appliance's trained Prophet model from the artifact
    registry and predicts one day.

    Args:
        appliance: Name of the appliance, exactly as it appears in the
            model registry (e.g. ``"Fridge"``, ``"Air Conditioning"``).
        forecast_date: ISO date ``"YYYY-MM-DD"`` of the day to forecast.
        avg_temp: Expected average outdoor temperature that day, in Celsius.
        hh_size: Expected household size (number of occupants).
        is_weekend: ``1`` for a weekend day, ``0`` for a weekday.

    Returns:
        Dict with the point forecast under ``"yhat"`` (predicted kWh), the
        95% band under ``"yhat_lower"`` / ``"yhat_upper"``, plus the
        ``"appliance"``, ``"ds"`` (forecast date) and the ``"model_path"`` /
        ``"split_date"`` provenance from the registry.

    Raises:
        RuntimeError: if the model registry/artifacts are missing - the
            models must be trained first (``model_loader.py``).
        ValueError: if ``appliance`` has no trained model, or ``is_weekend``
            is not ``0`` or ``1``.
    """
    # ---- Log the request ----------------------------------------------------
    # Debug level: the full payload is useful when tracing a specific agent
    # conversation, but too noisy for the default console output.
    logger.debug(
        "Forecast requested: appliance=%r date=%s temp=%s hh=%s weekend=%s",
        appliance,
        forecast_date,
        avg_temp,
        hh_size,
        is_weekend,
    )

    # ---- Validate the weekday/weekend flag ---------------------------------
    # The trained model only ever saw the two categories 0 (weekday) and 1
    # (weekend); any other value would produce a nonsense forecast, so reject
    # it up front.  Accepting numeric strings like "1" is a deliberate
    # convenience for agents that forward JSON-encoded parameters.
    if int(is_weekend) not in (0, 1):
        raise ValueError(
            f"is_weekend must be 0 (weekday) or 1 (weekend); got {is_weekend!r}."
        )

    # ---- Delegate to the prediction service --------------------------------
    # Imported lazily ON PURPOSE: `energy_predictor` validates the model
    # registry at *module import* time (it raises FileNotFoundError up top if
    # the models are not trained yet).  A top-level import would therefore
    # break this tool - and every agent that imports it - whenever the
    # artifacts are missing.  Importing inside the function moves that failure
    # to call time, where we can translate it into a friendly, actionable
    # error for the agent.
    try:
        from Backend.Models.energy_predictor import predict_next_day

        forecast = predict_next_day(
            appliance=appliance,
            ds_next=forecast_date,
            avg_temp=avg_temp,
            hh_size=hh_size,
            is_weekend=int(is_weekend),
        )
    # Map low-level errors to agent-friendly ones:
    #   * registry/artifacts absent        -> tell the user to train the models
    #   * appliance not in registry        -> tell the user which ones exist
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Forecast model registry is missing. Train the models first with: "
            "python Backend/Models/model_loader.py"
        ) from exc
    except KeyError as exc:
        raise ValueError(str(object=exc)) from exc

    # ---- Report the outcome ------------------------------------------------
    # Info level: the headline number (predicted kWh + uncertainty band) is
    # what operators want to see in the logs without any debugging overhead.
    logger.info(
        "Predicted %.2f kWh for %s on %s (95%% CI %.2f - %.2f).",
        forecast["yhat"],
        appliance,
        forecast["ds"],
        forecast["yhat_lower"],
        forecast["yhat_upper"],
    )
    # Return the full forecast dict (point estimate, band, provenance) so the
    # agent can quote the prediction with its confidence interval.
    return forecast


# ============================================================================
# Example usage (run directly: python ml_prediction_tool.py)
# ============================================================================
if __name__ == "__main__":
    # Standalone demo: show a couple of real forecasts plus the graceful
    # failure path for an appliance that has no trained model.
    settings.setup_logging(level="INFO")

    import datetime as _dt  # compute "tomorrow" in a timezone-naive, safe way

    # (appliance, forecast_date, avg_temp, hh_size, is_weekend)
    # forecast_date is left None on purpose -> defaults to tomorrow.
    examples = [
        ("Fridge", None,                            25.0, 3.0, 0),   # weekday
        ("Air Conditioning", None,                  32.0, 4.0, 1),   # weekend
        ("This-Is-Not-An-Appliance", None,          20.0, 2.0, 0),   # bad name
    ]

    base = _dt.date.today() + _dt.timedelta(days=1)
    for appliance, _date, temp, hh, weekend in examples:
        forecast_date = _date or base.isoformat()
        try:
            result = predict_daily_kwh(
                appliance=appliance,
                forecast_date=forecast_date,
                avg_temp=temp,
                hh_size=hh,
                is_weekend=weekend,
            )
        except (RuntimeError, ValueError, TypeError) as exc:
            # Expected errors: missing model / unknown appliance / bad input.
            print(f"[{appliance}] {exc}")
        else:
            print(
                f"[{appliance}] {result['ds']}: "
                f"{result['yhat']:.2f} kWh "
                f"(95% CI {result['yhat_lower']:.2f} - {result['yhat_upper']:.2f})"
            )