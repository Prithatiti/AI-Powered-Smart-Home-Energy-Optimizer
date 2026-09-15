"""
Agent 2 - Energy Optimizer and Recommendation Agent (Microsoft Agent Framework).

Agent-2 is a Microsoft Agent Framework (MAF) agent that CONSUMES Agent 1's
energy analysis and turns it into a compact, actionable savings plan.  It is
the *recommendation* layer of the pipeline: it reasons about which appliances
can shift or run leaner, prices those changes against a time-of-use tariff and
returns the whole plan as one JSON document.

The agent owns exactly three calculation tools, one per pricing capability:

    * get_tod_tariff        -> fetch the TOU tariff table for a day type
    * estimate_run_cost     -> price an appliance window against the tariff
    * reschedule_comparison -> compare a current window vs a suggested one

Each tool is a thin ``@tool`` wrapper around the deterministic facades in
``Backend/Tools/`` - all rate handling and arithmetic lives there, so this
module stays a clean MAF wiring point.

The model backend is Azure OpenAI, authenticated with the API key from
``settings`` (a ``AZURE_OPENAI_API_KEY`` in ``.env``).  The MAF chat client
builds the OpenAI SDK's ``AzureOpenAI`` client under the hood, so no Azure CLI
login / credential is required.  The system prompt is imported from
``Backend/Agents/Prompts/agent_2_prompt.py``
(``RECOMMENDATION_AGENT_INSTRUCTIONS``), keeping prompts out of code.
"""

# ============================================================================
# Imports
# ============================================================================
import asyncio  # run the async `agent.run()` in the __main__ demo
import sys  # ensure the project root is importable when run directly
from pathlib import Path  # cross-platform path handling
from typing import (
    Annotated,  # attach tool-parameter descriptions for the model
    Any,  # typing for the tool return values
    cast,  # narrow the client-specific generic returned by the framework
)

# Microsoft Agent Framework:
#   Agent      - the container that owns instructions + tools + the LLM client
#   tool       - decorator turning a plain python function into a FunctionTool
from agent_framework import Agent, tool

# Azure OpenAI chat client.  For Azure it needs the endpoint + an API key;
# `model` names the deployment on that endpoint.  MAF wires the OpenAI SDK's
# `AzureOpenAI` client internally - we never pass a CLI credential.
from agent_framework.openai import OpenAIChatClient

# Field() descriptions are turned by the framework into the tool JSON schema.
from pydantic import Field

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/Agents/agent_2_energy_optimizer.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# ============================================================================
# Logging
# ============================================================================
import logging  # structured, level-aware logging shared with the rest of the app

# Agent-2's system prompt lives in the shared prompt store, never inline here.
from Backend.Agents.Prompts.agent_2_prompt import RECOMMENDATION_AGENT_INSTRUCTIONS
from Backend.Config import settings

# Deterministic tool facades (JSON-able plain functions, fully commented):
from Backend.Tools.savings_calculator_tool import (
    estimate_run_cost as price_run,  # alias avoids clashing with the @tool name
)
from Backend.Tools.savings_calculator_tool import (
    reschedule_comparison as compare_schedules,  # alias avoids clashing
)
from Backend.Tools.tariff_tool import (
    get_tod_tariff as tariff_lookup,  # alias avoids clashing with the @tool name
)

logger = logging.getLogger(name=__name__)


# ============================================================================
# Tools (registered with the agent via the @tool decorator)
# ============================================================================
# Each tool declares its parameters with `Annotated[..., Field(...)]` so the
# framework can build an accurate JSON schema for the model and auto-parse the
# model's arguments.  Approval is never required: these are read-only lookups.
# Tool names intentionally match the tool catalogue in the prompt store.


@tool(approval_mode="never_require")
def get_tod_tariff(
    day_type: Annotated[
        str, Field(description="'weekday' or 'weekend' - the day being optimized.")
    ] = "weekday",
    currency: Annotated[
        str, Field(description="ISO-4217 currency code, e.g. 'INR'.")
    ] = "INR",
) -> dict[str, Any]:
    """Fetch the time-of-use electricity tariff for a day type."""
    # Delegates to the tariff facade; an unknown day type/currency returns an
    # empty time_of_use list (signalling "no tariff available") instead of
    # raising, so the agent can fall back to kWh-only optimization.
    return tariff_lookup(day_type=day_type, currency=currency)


@tool(approval_mode="never_require")
def estimate_run_cost(
    appliance: Annotated[str, Field(description="Appliance name being priced.")],
    kwh: Annotated[
        float, Field(description="Energy the appliance draws during the window, in kWh.")
    ],
    start_hour: Annotated[
        int, Field(description="Window start hour, 0-23. e.g. 19 for 7 PM.")
    ],
    end_hour: Annotated[
        int, Field(description="Window end hour, 1-24. <= start means overnight.")
    ],
    tariff_table: Annotated[
        dict[str, Any],
        Field(description="Tariff dict returned by GET_TOD_TARIFF (its time_of_use)."),
    ],
) -> dict[str, Any]:
    """Price an appliance's kWh across a running window against a tariff."""
    # Delegates to the calculator facade; window_cost is in the tariff's
    # currency units.  Never compute a price in the prompt - always price here.
    return price_run(
        appliance=appliance,
        kwh=kwh,
        start_hour=start_hour,
        end_hour=end_hour,
        tariff_table=tariff_table,
    )


@tool(approval_mode="never_require")
def reschedule_comparison(
    appliance: Annotated[str, Field(description="Appliance name being compared.")],
    kwh: Annotated[
        float, Field(description="Energy the appliance draws in either window, in kWh.")
    ],
    current_start: Annotated[
        int, Field(description="Current run start hour (0-23).")
    ],
    current_end: Annotated[
        int, Field(description="Current run end hour (1-24).")
    ],
    suggested_start: Annotated[
        int, Field(description="Proposed run start hour (0-23).")
    ],
    suggested_end: Annotated[
        int, Field(description="Proposed run end hour (1-24).")
    ],
    tariff_table: Annotated[
        dict[str, Any],
        Field(description="Tariff dict returned by GET_TOD_TARIFF (its time_of_use)."),
    ],
) -> dict[str, Any]:
    """Compare the cost of the current window vs a suggested window."""
    # Delegates to the calculator facade; savings_cost / savings_pct feed
    # directly into the recommendation's estimated_cost_saving.
    return compare_schedules(
        appliance=appliance,
        kwh=kwh,
        current_start=current_start,
        current_end=current_end,
        suggested_start=suggested_start,
        suggested_end=suggested_end,
        tariff_table=tariff_table,
    )


# ============================================================================
# Public API
# ============================================================================
def create_recommendation_agent(
    *,
    model: str | None = None,
    azure_endpoint: str | None = None,
    api_version: str | None = None,
    api_key: str | None = None,
) -> Agent:
    """Build the MAF "energy optimization and recommendation agent".

    Args:
        model: Azure OpenAI deployment name.  Defaults to
            ``settings.AZURE_OPENAI_CHAT_MODEL`` then
            ``settings.AZURE_OPENAI_DEPLOYMENT``.
        azure_endpoint: e.g. ``"https://my-resource.openai.azure.com"``.
            Defaults to ``settings.AZURE_OPENAI_ENDPOINT``.
        api_version: Azure OpenAI API version for the Responses API.  Defaults
            to MAF's own default (sentinel ``"preview"``, resolved by the
            SDK/env).  Note this deliberately does NOT reuse the
            Chat-Completions-tuned ``settings.AZURE_OPENAI_CHAT_VERSION``,
            which this Responses-based client rejects.
        api_key: Azure OpenAI API key.  Defaults to
            ``settings.AZURE_OPENAI_API_KEY``.

    Returns:
        A constructed ``agent_framework.Agent`` wired to the three tariff / cost
        tools.  Call ``await agent.run(...)`` to execute it.

    Note:
        Authenticates with the raw API key (via the OpenAI SDK's AzureOpenAI
        client under the hood) - no Azure CLI / credential objects needed.
    """
    client = OpenAIChatClient(
        model=model or settings.AZURE_OPENAI_CHAT_MODEL or settings.AZURE_OPENAI_DEPLOYMENT,
        azure_endpoint=azure_endpoint or settings.AZURE_OPENAI_ENDPOINT,
        api_version=api_version,
        api_key=api_key or settings.AZURE_OPENAI_API_KEY,
    )

    # The same Agent() construction pattern as Agent 1: instructions from the
    # shared prompt store, and only the calculation tools this persona needs.
    return cast(
        typ=Agent[Any],
        val=Agent(
            client=client,
            name="energy optimization and recommendation agent",
            instructions=RECOMMENDATION_AGENT_INSTRUCTIONS,
            tools=[
                get_tod_tariff,
                estimate_run_cost,
                reschedule_comparison,
            ],
        ),
    )


async def run_recommendation_agent(user_input: str, agent: Agent | None = None) -> str:
    """Run the optimizer agent on ``user_input`` and return the text reply.

    Convenience wrapper for scripts / notebooks that want one call instead of
    constructing + invoking the agent themselves.
    """
    agent = agent or create_recommendation_agent()
    logger.info("Invoking agent-2 with: %r", user_input)
    response = await agent.run(user_input)
    text = str(object=response)
    logger.info("Agent-2 replied (%d chars).", len(text))
    return text


# ============================================================================
# Example usage (run directly: python agent_2_energy_optimizer.py)
# ============================================================================
# Requires: AZURE_OPENAI_API_KEY (and endpoint/model/version) in .env or env.
if __name__ == "__main__":
    settings.setup_logging(level="INFO")
    demo_agent = create_recommendation_agent()

    # A realistic Agent-1 payload (abbreviated): forecasted AC (10 kWh, peak
    # evening window), Washing Machine (1.6 kWh, morning peak) and Fridge
    # (always-on).  The agent should price the two shiftable loads, sanity-
    # check the suggestions against the weather, and say honestly that the
    # Fridge cannot be optimised.
    agent_1_payload = {
        "forecast_date": "2026-09-16",
        "is_weekend": 0,
        "hh_size": 3,
        "weather": {
            "forecast_date": "2026-09-16",
            "min_temperature_c": 22.4,
            "max_temperature_c": 29.7,
            "weather_condition": "Moderate drizzle",
        },
        "last_usage": [
            {"appliance": "Air Conditioning", "start_time": "19:00",
             "end_time": "23:00", "kwh_consumed": 5.1},
            {"appliance": "Washing Machine", "start_time": "8:30",
             "end_time": "9:30", "kwh_consumed": 0.8},
            {"appliance": "Fridge", "start_time": "00:00", "end_time": "24:00",
             "kwh_consumed": 3.2},
        ],
        "forecasts": [
            {"appliance": "Air Conditioning", "ds": "2026-09-16", "yhat": 10.0},
            {"appliance": "Washing Machine", "ds": "2026-09-16", "yhat": 1.6},
            {"appliance": "Fridge", "ds": "2026-09-16", "yhat": 3.2},
        ],
        "analysis": {
            "summary": "Mild rainy day; AC and washing machine still run in the peak tariff hours.",
            "peak_appliance": {"appliance": "Air Conditioning",
                               "expected_kwh": 10.0, "reason": "Heaviest load, priced at peak."},
            "notes": [],
        },
    }

    prompt = (
        "Here is Agent 1's payload. Recommend optimized settings for every "
        "appliance, check each suggestion against the weather and running "
        "windows for real-world feasibility, price the savings with the tariff "
        "tools, and return JSON only.\n\n"
        f"{agent_1_payload}"
    )
    reply = asyncio.run(run_recommendation_agent(prompt, agent=demo_agent))
    # The Windows console codepage (e.g. cp1252) cannot encode every Unicode
    # character the model may emit (e.g. a non-breaking hyphen), so write UTF-8
    # bytes straight to stdout instead of letting print() fail on encoding.
    sys.stdout.buffer.write(reply.encode(encoding="utf-8") + b"\n")