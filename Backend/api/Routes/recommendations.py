"""
Recommendation API endpoint.

    POST /api/v1/recommendations  ->  run the optimization workflow

Accepts an :class:`OptimizeEnergyRequest` (home configuration plus time-of-use
tariff) and runs the two-agent optimization workflow
(:func:`Backend.Agents.Workflows.energy_optimization_workflow.run_agents`)
against it.  The optimisation plan produced by the agents is returned in the
response; formatting / emailing that plan is handled separately by
:mod:`Backend.api.Routes.email_plan`.
"""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/api/Routes/recommendations.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Agents.Workflows.energy_optimization_workflow import (
    WorkflowError,
    run_agents,
)
from Backend.Schemas import (
    Appliance,
    ElectricityTariff,
    HomeProfile,
    OptimizeEnergyRequest,
    TimeOfUseSlot,
)

router = APIRouter(prefix="/api/v1", tags=["recommendations"])

logger = logging.getLogger(__name__)


def _to_home_profile(request: OptimizeEnergyRequest) -> HomeProfile:
    """Map an API request onto the workflow's validated home configuration.

    The time-of-use tariff becomes two ToU bands: the peak window and an
    off-peak band covering the remainder (an overnight wrap, matching the
    savings-calculator's ``end_hour <= start_hour`` convention).
    """
    peak_start = int(request.tariff_peak_start[:2])
    peak_end = int(request.tariff_peak_end[:2])

    tariff = ElectricityTariff(
        time_of_use=[
            TimeOfUseSlot(start_hour=peak_start, end_hour=peak_end, rate=request.rate_peak),
            TimeOfUseSlot(start_hour=peak_end, end_hour=peak_start, rate=request.rate_offpeak),
        ]
    )

    return HomeProfile(
        hh_size=request.hh_size,
        appliances=[Appliance(name=name) for name in request.appliances_present],
        latitude=request.latitude,
        longitude=request.longitude,
        timezone=request.timezone,
        tariff=tariff,
    )


@router.post(
    path="/recommendations",
    summary="Generate energy-saving recommendations and optimization plan",
)
async def generate_recommendations(payload: OptimizeEnergyRequest) -> dict:
    """Run the optimization workflow for one home configuration.

    Args:
        payload: The validated request - home config plus time-of-use tariff.

    Returns:
        The optimization plan produced by the agents (``summary`` +
        ``actions`` + metadata), ready to be emailed/stored by the caller.

    Raises:
        HTTPException: 502 when the upstream agent workflow fails.
    """
    profile = _to_home_profile(request=payload)

    try:
        # Await directly on the async core (not the sync wrapper) so the
        # event loop is not blocked while the LLM agents run.
        return await run_agents(profile=profile)
    except WorkflowError as exc:
        logger.error("Recommendation workflow failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Recommendation agent returned no parseable result.",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surface any upstream failure
        logger.exception("Recommendation workflow raised: %s", exc)
        raise HTTPException(
            status_code=502, detail="Upstream recommendation service failed."
        ) from exc


# ---- Example usage (run directly: python recommendations.py) -----------------
if __name__ == "__main__":
    from Backend.Config import settings

    settings.setup_logging(level="INFO")

    request = OptimizeEnergyRequest(
        hh_size=4,
        appliances_present=["Air Conditioning", "Microwave", "Computer"],
    )
    mapped = _to_home_profile(request)
    print("Request -> HomeProfile mapping:\n")
    import json as _json

    output = _json.dumps(obj=mapped.model_dump(mode="json"), indent=2, ensure_ascii=False)
    sys.stdout.buffer.write(f"{output}\n".encode())