"""
Centralized application configuration and environment management.

Everything the rest of the app needs to know about its environment lives
here: Azure OpenAI endpoints/credentials, the weather geocoding + forecast
provider (Nominatim / Open-Meteo, including the WMO condition-code table),
logging policy, artifact/dataset paths and application-level constants.

Importing this module reads from the process environment and any ``.env``
file at the project root; secret values are never hardcoded in this file.

Policy
------
Secrets (API keys / endpoints) are loaded from environment variables or
a secret manager - they are NEVER hardcoded. A ``.env`` file at the
project root is read when present (see python-dotenv), which keeps local
development convenient while remaining safe for production (real secrets
stay in the environment / secret store, not in the repo).
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# ============================================================================
# Environment bootstrap
# ============================================================================
# Pops the process' environment over with any key=value pairs found in
# <project>/.env (a no-op when the file is absent, e.g. in production where
# real secrets come from the process environment). Read before every setting
# below so the rest of this module sees the merged environment.
load_dotenv()

# ============================================================================
# Project layout (derived from this file's location)
# ============================================================================
BACKEND_DIR = Path(__file__).resolve().parent.parent  # <project>/Backend
# Project root = <project>/; artifact sub-folders hang off it below.
PROJECT_ROOT = BACKEND_DIR.parent                     # <project>/
# Runtime outputs are kept under <project>/Backend/Artifacts, split by purpose:
ARTIFACTS_DIR = BACKEND_DIR / "Artifacts"   # root of all generated outputs
MODELS_DIR = ARTIFACTS_DIR / "Models"       # trained forecasting artifacts
PRED_DIR = ARTIFACTS_DIR / "Predictions"    # generated forecast results
ACCURACY_DIR = ARTIFACTS_DIR / "Accuracy"   # model evaluation summaries

# ============================================================================
# Application environment
# ============================================================================
# One of: development / staging / production.  Drives log verbosity and
# whether missing secrets are treated as a fatal misconfiguration.
ENVIRONMENT = os.getenv(key="ENVIRONMENT", default="development")
IS_PRODUCTION = ENVIRONMENT.lower() == "production"

# ============================================================================
# Application constants
# ============================================================================
# Location of the appliance-usage dataset consumed by training / evaluation.
CSV_PATH = "./data/appliance_usage.csv"
# Currency used whenever reports express energy-cost figures.
CURRENCY = "INR"
# Nominatim (OpenStreetMap) geocoding endpoint: resolves a free-text place
# name to structured coordinates. Free service - no API key required.
WEATHER_GEOCODING_URL = "https://nominatim.openstreetmap.org/search"
# Identifies this app to the Nominatim/Open-Meteo API operators; override with
# the WEATHER_USER_AGENT env var when deploying under your own identity.
WEATHER_USER_AGENT = os.getenv(
    key="WEATHER_USER_AGENT",
    default="AI-Powered-Smart-Home-Energy-Optimizer/1.0 "
    "(smart home energy optimization research project)",
)

# ============================================================================
# SMTP (outbound email reports)
# ============================================================================
# Outbound SMTP server used to deliver the email reports composed by the
# Email Report agent.  Credentials are loaded from the environment / .env:
#     SMTP_HOST      - SMTP server hostname (e.g. "smtp.gmail.com")
#     SMTP_PORT      - submission port (587 for STARTTLS)
#     SMTP_USERNAME  - mailbox login used to authenticate
#     SMTP_PASSWORD  - mailbox password / app-password
# The placeholder host "smtp.example.com" is treated as "not configured".
SMTP_HOST = os.getenv(key="SMTP_HOST")
SMTP_PORT = int(os.getenv(key="SMTP_PORT", default="587"))
SMTP_USERNAME = os.getenv(key="SMTP_USERNAME")
SMTP_PASSWORD = os.getenv(key="SMTP_PASSWORD")
# Sender "From" address - usually the same mailbox that authenticates.  The
# default recipient for reports comes from SMTP_TO_EMAIL when set.
SMTP_FROM = os.getenv(key="SMTP_FROM", default=SMTP_USERNAME)
SMTP_TO_EMAIL = os.getenv(key="SMTP_TO_EMAIL")
# STARTTLS is required on the classic submission port (587); keep it on
# unless the mail server is a private endpoint without TLS.
SMTP_USE_STARTTLS = os.getenv(key="SMTP_USE_STARTTLS", default="true").lower() == "true"
# Seconds to wait for the SMTP server before giving up.
SMTP_TIMEOUT = int(os.getenv(key="SMTP_TIMEOUT", default="15"))

# ============================================================================
# Azure OpenAI (LLM) configuration
# ============================================================================
# Chat completions for the LLM agents. Provide endpoint, deployment name and
# API key via environment variables (see .env / secret manager). The API
# version pins the client against a specific Azure OpenAI release.
AZURE_OPENAI_ENDPOINT = os.getenv(key="AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
AZURE_OPENAI_DEPLOYMENT = os.getenv(key="AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_KEY = os.getenv(key="AZURE_OPENAI_API_KEY")

# Foundry-style aliases used by some endpoints (.env uses CHAT_MODEL /
# CHAT_VERSION for the deployment name and preview API version).  Agents fall
# back on AZURE_OPENAI_DEPLOYMENT / AZURE_OPENAI_API_VERSION when unset.
AZURE_OPENAI_CHAT_MODEL = os.getenv(key="AZURE_OPENAI_CHAT_MODEL")
AZURE_OPENAI_CHAT_VERSION = os.getenv(key="AZURE_OPENAI_CHAT_VERSION")

# ============================================================================
# Weather API configuration
# ============================================================================
# Optional key for paid weather providers; Nominatim / Open-Meteo are free and
# work without one, so this may legitimately stay unset.
WEATHER_API_KEY = os.getenv(key="WEATHER_API_KEY")

# Open-Meteo forecast endpoint (free, no API key).
WEATHER_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# How long we wait for the upstream forecast before falling back.
WEATHER_TIMEOUT = 10
# Open-Meteo's forecast window. Dates further out than this are treated as
# "beyond forecast range" and reported as such.
WEATHER_MAX_FORECAST_DAYS = 16
# Condition label used when an Open-Meteo WMO code is unknown.
WEATHER_UNKNOWN_CONDITION = "Unknown"

# WMO weather interpretation codes -> short human-readable conditions.
# Reference: http://open-meteo.com/en/docs (weather interpretation codes)
WMO_CONDITIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

# ============================================================================
# Model artifacts / dataset
# ============================================================================
# Path to the trained forecasting models. Overridable via MODEL_PATH;
# defaults to the artifacts directory produced by the model loader.
MODEL_PATH = os.getenv(key="MODEL_PATH", default=str(object=MODELS_DIR))

# ============================================================================
# Logging configuration
# ============================================================================
# LOG_LEVEL env var wins; otherwise DEBUG locally, INFO in production.
# LOG_FORMAT controls the single-line shape shared across the app.
LOG_LEVEL = os.getenv(
    "LOG_LEVEL", default="INFO" if IS_PRODUCTION else "DEBUG"
)
LOG_FORMAT = os.getenv(
    key="LOG_FORMAT",
    default="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger (idempotent) using the module defaults.

    Call once at application startup; imported modules then get consistent,
    well-formatted logs without repeating the boilerplate.
    """
    logging.basicConfig(
        level=getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO),
        format=LOG_FORMAT,
    )


def smtp_configured() -> bool:
    """Return whether an outbound SMTP server is actually configured.

    ``True`` only when a real host (not the ``smtp.example.com`` placeholder),
    a username and a password are all present - the minimum a submission
    server needs to authenticate.
    """
    return bool(
        SMTP_HOST
        and SMTP_HOST != "smtp.example.com"
        and SMTP_USERNAME
        and SMTP_PASSWORD
    )


def require_secrets() -> None:
    """Fail fast when an expected secret is missing in production.

    In non-production environments a missing key simply stays ``None`` so
    the app can still boot against mock/placeholder data.
    """
    if not IS_PRODUCTION:
        return

    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT),
            ("AZURE_OPENAI_API_KEY", AZURE_OPENAI_API_KEY),
            ("AZURE_OPENAI_DEPLOYMENT", AZURE_OPENAI_DEPLOYMENT),
            ("WEATHER_API_KEY", WEATHER_API_KEY),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s) in production: "
            + ", ".join(missing)
        )