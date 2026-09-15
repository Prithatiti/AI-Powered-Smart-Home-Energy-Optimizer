"""
Agent factory - centralized Microsoft Agent Framework (MAF) configuration.

This module is the single place that builds MAF agents wired to the project's
Azure OpenAI deployment.  It owns the bits every agent shares:

    * Azure OpenAI client configuration (build_chat_client)
    * model / deployment selection      (resolve_model_config)
    * agent creation                     (create_agent)
    * tool registration                  (create_agent's ``tools=`` list)
    * the shared run helper              (run_agent)
    * shared defaults                    (module constants + settings)

The specialized agents (``agent_1_energy_analysis.py``,
``agent_2_energy_optimizer.py``) therefore only supply what makes them
distinct - a NAME, the INSTRUCTIONS from the prompt store and their tool list -
and delegate every line of Azure OpenAI / MAF configuration here.  This keeps
setup code out of the agent modules and guaranteed consistent across the app.
"""

# ============================================================================
# Imports
# ============================================================================
import logging  # structured, level-aware logging shared with the rest of the app
import sys  # ensure the project root is importable when run directly
from collections.abc import Callable  # callable type annotations
from pathlib import Path  # cross-platform path handling
from typing import Any, cast  # generics + narrowing for the framework client

# Microsoft Agent Framework:
#   Agent - the container that owns instructions + tools + the LLM client.
#   OpenAIChatClient - chat client that MAF wires to the OpenAI SDK's
#   `AzureOpenAI` client under the hood (API-key based, no CLI credential).
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Agents/agent_factory.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Centralised configuration (Azure endpoint / deployment / api version / key).
from Backend.Config import settings

logger = logging.getLogger(name=__name__)

# ============================================================================
# Shared configuration
# ============================================================================
# The API-version policy: agents run against the Azure OpenAI *Responses* API
# (which is what MAF's client calls).  Keeping the default to ``None`` lets
# MAF use its own ``"preview"`` sentinel instead of the Chat-Completions-tuned
# ``settings.AZURE_OPENAI_CHAT_VERSION``, which the Responses endpoint rejects.
DEFAULT_API_VERSION: str | None = None


# ============================================================================
# Model / deployment selection
# ============================================================================
def resolve_model_config(
    *,
    model: str | None = None,
    azure_endpoint: str | None = None,
    api_version: str | None = None,
    api_key: str | None = None,
) -> dict[str, str | None]:
    """Resolve the four Azure OpenAI connection inputs for an agent.

    Explicit call arguments win; anything not supplied falls back to the
    project settings (see ``Backend/Config/settings.py``).

    Args:
        model: Deployment/model name.  Defaults to
            ``AZURE_OPENAI_CHAT_MODEL`` then ``AZURE_OPENAI_DEPLOYMENT``.
        azure_endpoint: e.g. ``"https://my-resource.openai.azure.com"``.
            Defaults to ``AZURE_OPENAI_ENDPOINT``.
        api_version: Azure API version for the Responses API.  ``None`` keeps
            MAF's ``"preview"`` default (see :data:`DEFAULT_API_VERSION`).
        api_key: Azure OpenAI API key.  Defaults to ``AZURE_OPENAI_API_KEY``.

    Returns:
        A settings-keyed dict ready to splat into a client/agent constructor.
    """
    return {
        "model": model or settings.AZURE_OPENAI_CHAT_MODEL or settings.AZURE_OPENAI_DEPLOYMENT,
        "azure_endpoint": azure_endpoint or settings.AZURE_OPENAI_ENDPOINT,
        "api_version": api_version or DEFAULT_API_VERSION,
        "api_key": api_key or settings.AZURE_OPENAI_API_KEY,
    }


# ============================================================================
# Azure OpenAI client construction
# ============================================================================
def build_chat_client(
    *,
    model: str | None = None,
    azure_endpoint: str | None = None,
    api_version: str | None = None,
    api_key: str | None = None,
) -> OpenAIChatClient:
    """Build the MAF chat client for an agent.

    Applies :func:`resolve_model_config` then constructs an
    ``OpenAIChatClient``.  The underlying OpenAI SDK builds an ``AzureOpenAI``
    client from the API key, so no Azure CLI / credential is required.

    Returns:
        A configured ``agent_framework.openai.OpenAIChatClient``.
    """
    config = resolve_model_config(
        model=model,
        azure_endpoint=azure_endpoint,
        api_version=api_version,
        api_key=api_key,
    )
    client = OpenAIChatClient(
        model=config["model"],
        azure_endpoint=config["azure_endpoint"],
        api_version=config["api_version"],
        api_key=config["api_key"],
    )
    logger.debug("Built chat client: model=%r endpoint=%r", config["model"], config["azure_endpoint"])
    return client


# ============================================================================
# Agent creation + tool registration
# ============================================================================
def create_agent(
    name: str,
    instructions: str,
    tools: list,
    *,
    model: str | None = None,
    azure_endpoint: str | None = None,
    api_version: str | None = None,
    api_key: str | None = None,
) -> Agent:
    """Create a fully wired MAF agent from just its identity + tools.

    The one-stop constructor used by every agent module: it builds the shared
    chat client, registers ``tools`` on the ``Agent``, attaches ``name`` and
    ``instructions`` and returns a typed ``Agent``.

    Args:
        name: Display name of the agent (used in logs and telemetry).
        instructions: System prompt from the shared prompt store.
        tools: The ``@tool``-decorated functions the agent may call.
        model / azure_endpoint / api_version / api_key: Optional overrides for
            the connection config (see :func:`resolve_model_config`).

    Returns:
        A constructed ``agent_framework.Agent``.  Run with ``await agent.run(...)``.
    """
    # cast() keeps the framework's generic client type from leaking into the
    # public signature - callers just see `Agent`.
    return cast(
        typ=Agent[Any],
        val=Agent(
            client=build_chat_client(
                model=model,
                azure_endpoint=azure_endpoint,
                api_version=api_version,
                api_key=api_key,
            ),
            name=name,
            instructions=instructions,
            tools=list(tools),
        ),
    )


# ============================================================================
# Shared run helper
# ============================================================================
async def run_agent(
    user_input: str,
    *,
    agent: Agent | None = None,
    create: Callable[[], Agent] | None = None,
    label: str = "Agent",
) -> str:
    """Run an agent on ``user_input`` and return its text reply.

    Shared by every agent module so the logging/run pattern lives in exactly
    one place.  Provide either a ready-made ``agent`` or a zero-argument
    ``create`` callable (e.g. ``create_usage_collector_agent``).

    Args:
        user_input: The prompt / payload to hand to the agent model.
        agent: An already-constructed agent.  If omitted, ``create`` is used.
        create: Zero-argument callable returning an ``Agent``; used when
            ``agent`` is ``None``.
        label: Name used in the log lines (e.g. ``"Agent-1"``).

    Returns:
        The agent's reply as text.

    Raises:
        ValueError: if neither ``agent`` nor ``create`` is provided.
    """
    if agent is None:
        if create is None:
            raise ValueError("Pass an `agent` or a `create` callable to run_agent.")
        agent = create()
    logger.info("Invoking %s with: %r", label, user_input)
    response = await agent.run(user_input)
    text = str(object=response)
    logger.info("%s replied (%d chars).", label, len(text))
    return text


# ============================================================================
# Example usage (run directly: python agent_factory.py)
# ============================================================================
# Requires: AZURE_OPENAI_API_KEY (and endpoint/model/version) in .env or env.
if __name__ == "__main__":
    settings.setup_logging(level="INFO")

    config = resolve_model_config()
    print(
        "Resolved model config: "
        f"model={config['model']!r} endpoint={config['azure_endpoint']!r} "
        f"api_version={config['api_version']!r} key={'set' if config['api_key'] else 'MISSING'}"
    )
    client = build_chat_client()
    print(f"Client built: {type(client).__name__}")
    print("Use create_agent(name, instructions, tools) from the agent modules.")