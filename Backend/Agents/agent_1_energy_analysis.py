"""
Agent 1 - Energy Usage Collector Agent (Microsoft Agent Framework).

Agent-1 is a Microsoft Agent Framework (MAF) agent that COLLECTS the data
needed for next-day energy analysis and returns it as raw JSON.  It is the
*data-gathering* layer of the pipeline: downstream reasoning (Agent-1's
narrative analysis) consumes everything it returns.

The agent owns exactly three tools, one per data source:

    * get_last_usage_from_csv  -> historical appliance-level consumption
    * get_tomorrow_weather     -> next-day forecast weather at the home
    * forecast_next_day_kwh    -> Prophet ML forecast per appliance

Each tool is a thin ``@tool`` wrapper around the deterministic facades in
``Backend/Tools/`` - all real I/O and model math lives there, so this module
stays a clean MAF wiring point.

The model backend is Azure OpenAI, authenticated with the API key from
``settings`` (A ``AZURE_OPENAI_API_KEY`` in ``.env``).  The MAF chat client
builds the OpenAI SDK's ``AzureOpenAI`` client under the hood, so no Azure CLI
login / credential is required.  The system prompt is imported from
``Backend/Agents/Prompts/agent_1_prompt.py``
(``USAGE_COLLECTOR_INSTRUCTIONS``), keeping prompts out of code.
"""

# ============================================================================
# Imports
# ============================================================================
import asyncio  # run the async `agent.run()` in the __main__ demo
import sys  # ensure the project root is importable when run directly
from pathlib import Path  # cross-platform path handling
from typing import (
    Annotated,  # attatch tool-parameter descriptions for the model
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
# (python Backend/Agents/agent_1_energy_analysis.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Centralised configuration (Azure endpoint / api version / model name).
# ============================================================================
# Logging
# ============================================================================
# Module-level logger, named after this module so log lines from any agent
# carry the right origin tag for filtering in the artifact logs.
import logging

# Agent-1's system prompt lives in the shared prompt store, never inline here.
from Backend.Agents.Prompts.agent_1_prompt import USAGE_COLLECTOR_INSTRUCTIONS
from Backend.Config import settings

# Deterministic tool facades (JSON-able plain functions, fully commented):
from Backend.Tools.historical_usage_tool import get_last_usage
from Backend.Tools.ml_prediction_tool import predict_daily_kwh
from Backend.Tools.weather_forecast_tool import get_weather_forecast

logger = logging.getLogger(name=__name__)


# ============================================================================
# Tools (registered with the agent via the @tool decorator)
# ============================================================================
# Each tool declares its parameters with `Annotated[..., Field(...)]` so the
# framework can build an accurate JSON schema for the model and auto-parse the
# model's arguments.  Approval is never required: these are read-only lookups.


@tool(approval_mode="never_require")
def get_last_usage_from_csv(
    csv_path: Annotated[
        str,
        Field(
            description=(
                "Path to the historical appliance-usage CSV. When the file is "
                "absent the bundled sample dataset is used automatically."
            )
        ),
    ] = "data/historical/energy_consumption.csv",
) -> list[dict[str, Any]]:
    """Load the household's most recent appliance-level usage records."""
    return get_last_usage(csv_path=csv_path)


@tool(approval_mode="never_require")
def get_tomorrow_weather(
    latitude: Annotated[float, Field(description="Latitude of the home.")],
    longitude: Annotated[float, Field(description="Longitude of the home.")],
    timezone: Annotated[
        str, Field(description="IANA timezone name, e.g. 'Asia/Kolkata'.")
    ] = "Asia/Kolkata",
    forecast_date: Annotated[
        str,
        Field(description="ISO date 'YYYY-MM-DD' to forecast; defaults to tomorrow."),
    ] = "",
) -> dict[str, Any]:
    """Get the weather forecast (min/max temperature + condition) for one day."""
    # Empty forecast_date is interpreted as "tomorrow" by the underlying tool.
    return get_weather_forecast(
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        forecast_date=forecast_date,
    )


@tool(approval_mode="never_require")
def forecast_next_day_kwh(
    appliance: Annotated[
        str, Field(description="Appliance name as in the model registry (e.g. 'Fridge').")
    ],
    forecast_date: Annotated[
        str, Field(description="ISO date 'YYYY-MM-DD' of the day to forecast.")
    ] = "",
    avg_temp: Annotated[
        float,
        Field(description="Expected average outdoor temperature that day, in Celsius."),
    ] = 25.0,
    hh_size: Annotated[
        float, Field(description="Expected household size (number of occupants).")
    ] = 3.0,
    is_weekend: Annotated[
        int, Field(description="1 for a weekend day, 0 for a weekday.")
    ] = 0,
) -> dict[str, Any]:
    """Forecast one appliance's expected total consumption (kWh) for a day."""
    # The underlying tool resolves an empty date to "tomorrow" when needed.
    return predict_daily_kwh(
        appliance=appliance,
        forecast_date=forecast_date,
        avg_temp=avg_temp,
        hh_size=hh_size,
        is_weekend=is_weekend,
    )


# ============================================================================
# Public API
# ============================================================================
def create_usage_collector_agent(
    *,
    model: str | None = None,
    azure_endpoint: str | None = None,
    api_version: str | None = None,
    api_key: str | None = None,
) -> Agent:
    """Build the MAF "Energy Usage Collector Agent".

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
        A constructed ``agent_framework.Agent`` wired to the three collector
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

    return cast(
        typ=Agent[Any],
        val=Agent(
            client=client,
            name="Energy Usage Collector Agent",
            instructions=USAGE_COLLECTOR_INSTRUCTIONS,
            tools=[
                get_last_usage_from_csv,
                get_tomorrow_weather,
                forecast_next_day_kwh,
            ],
        ),
    )


async def run_usage_collector(user_input: str, agent: Agent | None = None) -> str:
    """Run the collector agent on ``user_input`` and return the text reply.

    Convenience wrapper for scripts / notebooks that want one call instead of
    constructing + invoking the agent themselves.
    """
    agent = agent or create_usage_collector_agent()
    logger.info("Invoking agent-1 with: %r", user_input)
    response = await agent.run(user_input)
    text = str(object=response)
    logger.info("Agent-1 replied (%d chars).", len(text))
    return text


# ============================================================================
# Example usage (run directly: python agent_1_energy_analysis.py)
# ============================================================================
# Requires: AZURE_OPENAI_API_KEY (and endpoint/model/version) in .env or env.
if __name__ == "__main__":
    settings.setup_logging(level="INFO")
    demo_agent = create_usage_collector_agent()
    prompt = (
        "Collect tomorrow's energy usage data for the home at "
        "latitude 18.5204, longitude 73.8567 (timezone Asia/Kolkata), "
        "household size 3. Return JSON only."
    )
    print(asyncio.run(run_usage_collector(prompt, agent=demo_agent)))