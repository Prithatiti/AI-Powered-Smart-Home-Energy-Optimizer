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

All Microsoft Agent Framework configuration - the Azure OpenAI chat client,
model/deployment selection, agent construction and the shared run helper - is
owned by ``Backend/Agents/agent_factory.py``; this module only supplies the
agent's NAME, INSTRUCTIONS and tools.  The system prompt is imported from
``Backend/Agents/Prompts/agent_1_prompt.py``
(``USAGE_COLLECTOR_INSTRUCTIONS``), keeping prompts out of code.
"""

# ============================================================================
# Imports
# ============================================================================
import asyncio  # run the async `agent.run()` in the __main__ demo
import sys  # ensure the project root is importable when run directly
from pathlib import Path  # cross-platform path handling
from typing import Annotated, Any  # tool parameter descriptions + return types

# Microsoft Agent Framework:
#   tool - decorator turning a plain python function into a FunctionTool
from agent_framework import tool

# pydantic Field() descriptions are turned by the framework into the tool JSON
# schema.  (Agent/client construction lives in the shared factory below.)
from pydantic import Field

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/Agents/agent_1_energy_analysis.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# ============================================================================
# Imports (project)
# ============================================================================
# Shared factory: Agent type, create_agent (client + tool wiring) and the
# run_agent helper used by every agent module.
from Backend.Agents.agent_factory import Agent, create_agent, run_agent

# Agent-1's system prompt lives in the shared prompt store, never inline here.
from Backend.Agents.Prompts.agent_1_prompt import USAGE_COLLECTOR_INSTRUCTIONS
from Backend.Config import settings

# Deterministic tool facades (JSON-able plain functions, fully commented):
from Backend.Tools.historical_usage_tool import get_last_usage
from Backend.Tools.ml_prediction_tool import predict_daily_kwh
from Backend.Tools.weather_forecast_tool import get_weather_forecast

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

    Configures the agent with its name, the collector system prompt and its
    three data tools; the shared factory
    (:func:`Backend.Agents.agent_factory.create_agent`) provides the Azure
    OpenAI client, model selection and wiring.

    Args:
        model / azure_endpoint / api_version / api_key: Optional connection
            overrides; all default to the project settings (see
            :func:`Backend.Agents.agent_factory.resolve_model_config`).

    Returns:
        A constructed ``agent_framework.Agent`` wired to the three collector
        tools.  Call ``await agent.run(...)`` to execute it.
    """
    return create_agent(
        name="Energy Usage Collector Agent",
        instructions=USAGE_COLLECTOR_INSTRUCTIONS,
        tools=[get_last_usage_from_csv, get_tomorrow_weather, forecast_next_day_kwh],
        model=model,
        azure_endpoint=azure_endpoint,
        api_version=api_version,
        api_key=api_key,
    )


async def run_usage_collector(user_input: str, agent: Agent | None = None) -> str:
    """Run the collector agent on ``user_input`` and return the text reply.

    Thin wrapper over the factory's shared :func:`run_agent` helper for
    scripts / notebooks that want one call instead of constructing + invoking
    the agent themselves.
    """
    return await run_agent(
        user_input,
        agent=agent,
        create=create_usage_collector_agent,
        label="Agent-1",
    )


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
    print(asyncio.run(main=run_usage_collector(user_input=prompt, agent=demo_agent)))