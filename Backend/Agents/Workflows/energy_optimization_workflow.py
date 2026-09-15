"""
Two-agent energy optimization workflow (orchestration layer).

The end-to-end pipeline in one module.  Given a validated
:class:`~Backend.Schemas.home.HomeProfile`, it:

    1. Resolves a ``city`` to coordinates on the backend (geocoding) when the
       profile has no explicit latitude / longitude.
    2. Builds the collector prompt: dataset path, home profile, target date
       and weekday/weekend marker.
    3. Runs Agent 1 (``Energy Usage Collector Agent``) to gather historical
       usage, next-day weather and the ML forecast.
    4. Validates Agent 1's intermediate JSON through the shared schemas.
    5. Feeds the validated result to Agent 2 (recommendation agent).
    6. Validates the final recommendation through the schemas and returns it.

Schema usage is **tolerant by design**: schemas standardise and floor-check
the agent payloads, but a mismatch never kills the pipeline - the offending
part is logged and passed through so the end-to-end flow always completes.

The synchronous :func:`run_agent` wrapper is the entry point for scripts and
API handlers; :func:`run_agents` is the async core.
"""

# ============================================================================
# Imports
# ============================================================================
import asyncio  # drive the async agent runs from the sync wrapper
import json  # exchange structured payloads with the agents
import logging  # structured, level-aware logging shared with the rest of the app
import sys  # ensure the project root is importable when run directly
from datetime import datetime, timedelta, timezone  # target-date + weekend math
from pathlib import Path  # cross-platform path handling

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/Agents/Workflows/energy_optimization_workflow.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Agents.agent_1_energy_analysis import (
    create_usage_collector_agent,
    run_usage_collector,
)
from Backend.Agents.agent_2_energy_optimizer import (
    create_recommendation_agent,
    run_recommendation_agent,
)

# Centralised configuration (logging policy, paths, ...).
from Backend.Config import settings

# Shared schemas - validated at the workflow boundary (tolerant, see module doc).
from Backend.Schemas import (
    Appliance,  # appliance entries of the home profile
    ApplianceForecast,  # forecast rows of Agent 1's output
    ApplianceUsage,  # last_usage rows of Agent 1's output
    HomeProfile,  # the validated home configuration
    OptimizationRecommendation,  # the final recommendation shape
    WeatherForecast,  # the weather block of Agent 1's output
)

# Deterministic helpers used to enrich the profile / prompt.
from Backend.Services.energy_service import resolve_usage_csv
from Backend.Services.geocode_service import geocode

logger = logging.getLogger(name=__name__)


# ============================================================================
# Errors
# ============================================================================
class WorkflowError(RuntimeError):
    """Raised when an agent returns something the workflow cannot process."""


# ============================================================================
# JSON extraction (agent -> dict)
# ============================================================================
def _safe_json_extract(text: str) -> dict | None:
    """Parse an agent reply into a dict, tolerating markdown fences / prose.

    Tries plain ``json.loads`` first, then a ```json fenced block, then the
    outermost ``{ ... }`` span.  Returns ``None`` when no JSON object is
    recoverable.

    Args:
        text: The raw (stringified) agent reply.

    Returns:
        A parsed ``dict``, or ``None`` if the reply carries no JSON object.
    """
    candidate = text.strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # ```json ... ``` (or bare ```) fenced block.
    if candidate.startswith("```"):
        inner = candidate.split("```", 2)
        if len(inner) >= 3:
            block = inner[1].strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

    # Outermost braces: from first "{" to the last "}".
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(candidate[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


# ============================================================================
# Tolerant schema validation (validating intermediate results)
# ============================================================================
def _validate_collector(data: dict) -> None:
    """Floor-check Agent 1's payload against the energy / weather / forecast
    schemas.  Invalid or missing parts are logged and replaced, never fatal."""

    weather = data.get("weather")
    if isinstance(weather, dict):
        try:
            data["weather"] = WeatherForecast.model_validate(weather).model_dump()
        except Exception as exc:  # noqa: BLE001 - tolerant by contract
            logger.warning(
                "Agent-1 'weather' failed schema check; passing through: %s", exc
            )

    last_usage = data.get("last_usage")
    if isinstance(last_usage, list):
        rows: list = []
        skipped = 0
        for row in last_usage:
            try:
                rows.append(ApplianceUsage.model_validate(obj=row).model_dump())
            except Exception as exc:  # noqa: BLE001 - tolerant by contract
                skipped += 1
                logger.warning("Skipping malformed last_usage row: %s", exc)
        if skipped:
            logger.warning(
                "Dropped %d malformed last_usage rows from Agent-1.", skipped
            )
        data["last_usage"] = rows

    forecasts = data.get("forecasts")
    if isinstance(forecasts, list):
        rows = []
        for row in forecasts:
            try:
                rows.append(ApplianceForecast.model_validate(row).model_dump())
            except Exception as exc:  # noqa: BLE001 - tolerant by contract
                logger.warning("Skipping malformed forecast row: %s", exc)
        data["forecasts"] = rows


def _validate_recommendation(data: dict) -> None:
    """Floor-check Agent 2's final recommendation against the schemas.

    On success the validated fields overwrite the raw values in ``data``;
    on failure the payload passes through unchanged (logged)."""

    try:
        validated = OptimizationRecommendation.model_validate(data)
        data.update(validated.model_dump())
    except Exception as exc:  # noqa: BLE001 - tolerant by contract
        logger.warning(
            "Agent-2 recommendation failed schema check; returning as-is: %s", exc
        )


# ============================================================================
# Agent Execution
# ============================================================================
async def run_agents(profile: HomeProfile) -> dict:
    """Run both agents end-to-end for one home configuration.

    Args:
        profile: The validated home configuration (may carry a ``city`` that
            gets geocoded to coordinates on this side).

    Returns:
        The final recommendation as a plain dict (validated through
        :class:`OptimizationRecommendation` when Agent 2 complied).

    Raises:
        WorkflowError: if an agent returns no recoverable JSON object.
    """
    # ---- Initialize the two agents ----------------------------------------
    collector_agent = create_usage_collector_agent()
    recommender_agent = create_recommendation_agent()

    # ---- Resolve city -> lat/lon on the backend if a city was provided -----
    if profile.city:
        try:
            matches = geocode(city=profile.city, limit=1)
            if matches:
                best = matches[0]
                profile.latitude = float(best.get("lat", profile.latitude))
                profile.longitude = float(best.get("lon", profile.longitude))
                logger.info(
                    "Resolved city %r -> lat=%s lon=%s",
                    profile.city,
                    profile.latitude,
                    profile.longitude,
                )
        except Exception as exc:  # noqa: BLE001 - geocoding is best-effort
            logger.warning(
                "Geocoding failed for %r; keeping profile coordinates: %s",
                profile.city,
                exc,
            )

    # ---- Prepare the initial prompt ---------------------------------------=
    # Next-day target in the home's own calendar (ISO), plus its weekend flag.
    tomorrow = datetime.now(tz=timezone.utc) + timedelta(days=1)
    is_weekend = 1 if tomorrow.weekday() >= 5 else 0

    # Resolve the dataset once, so the collector does not have to rediscover
    # it; if it is missing here, the tool still falls back to its default.
    try:
        csv_path = str(object=resolve_usage_csv())
    except FileNotFoundError as exc:
        csv_path = None
        logger.warning(
            "Historical CSV not resolvable; tool default will be used: %s", exc
        )

    raw_prompt = json.dumps(
        obj={
            "csv_path": csv_path,
            "profile": profile.model_dump(mode="json"),
            "tomorrow_iso": tomorrow.date().isoformat(),
            "is_weekend": is_weekend,
        }
    )

    # ---- Execute the usage collector agent ---------------------------------
    collector_text = await run_usage_collector(
        user_input=f"Collect required info: {raw_prompt}",
        agent=collector_agent,
    )
    collector_data = _safe_json_extract(collector_text)
    if not isinstance(collector_data, dict):
        raise WorkflowError("Agent-1 (collector) did not return a JSON object.")
    _validate_collector(collector_data)

    # ---- Feed the validated collector output to the recommender ------------
    rec_input = json.dumps(collector_data)
    recommender_text = await run_recommendation_agent(
        f"Analyze and recommend: {rec_input}",
        agent=recommender_agent,
    )

    # ---- Return the final (validated) recommendation -----------------------
    recommendation = _safe_json_extract(recommender_text)
    if not isinstance(recommendation, dict):
        raise WorkflowError("Agent-2 (recommender) did not return a JSON object.")
    _validate_recommendation(recommendation)
    _log_outcome(recommendation)
    return recommendation


def _log_outcome(recommendation: dict) -> None:
    """Log a one-line summary of the recommended actions for operators."""
    actions = recommendation.get("actions", [])
    total_saving = sum(
        float(a.get("estimated_cost_saving") or 0.0)
        for a in actions
        if isinstance(a, dict)
    )
    logger.info(
        "Workflow complete: %d action(s), ~%.2f %s total estimated saving.",
        len(actions),
        total_saving,
        recommendation.get("currency") or settings.CURRENCY,
    )


# ============================================================================
# Synchronous entry point
# ============================================================================
def run_agent(profile: HomeProfile | None = None) -> dict:
    """Run the full workflow synchronously.

    Args:
        profile: Home configuration; ``None`` uses the schema defaults
            (the demo Pune household).

    Returns:
        The validated final recommendation (same shape as
        :func:`run_agents`).
    """
    return asyncio.run(main=run_agents(profile=profile or HomeProfile()))


# ============================================================================
# Example usage (run directly:
# python Backend/Agents/Workflows/energy_optimization_workflow.py)
# ============================================================================
if __name__ == "__main__":
    settings.setup_logging(level="INFO")

    print("Starting end-to-end workflow for the default profile...\n")
    profile = HomeProfile(
        hh_size=4,
        appliances=[
            Appliance(name="Air Conditioning"),
            Appliance(name="Washing Machine"),
            Appliance(name="Dishwasher"),
            Appliance(name="Microwave"),
            Appliance(name="Computer"),
        ],
    )
    result = run_agent(profile)

    # Write UTF-8 explicitly: the Windows console (cp1252) cannot encode the
    # Unicode (e.g. U+2011 non-breaking hyphen) the model sometimes emits.

    output = json.dumps(result, indent=2, ensure_ascii=False)
    sys.stdout.buffer.write(f"{output}\n".encode())
