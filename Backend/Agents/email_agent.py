"""
Email Report Agent (Microsoft Agent Framework) + SMTP delivery.

Turns a validated recommendation payload (the output of the two-agent
optimization workflow) into a human-friendly customer email and sends it via
SMTP::

    recommendation = await run_agents(profile)     # workflow result (dict)
    report        = await email_report(recommendation)  # {to, subject, body} + send

Two layers:

    1. *Agent layer* - :func:`create_email_agent`, :func:`run_email_agent` and
       :func:`compose_report` use the shared MAF factory (Azure OpenAI) to
       turn the recommendation JSON into an email (``subject`` + ``body``).
       The agent never invents figures - the writing rules live in
       :mod:`Backend.Agents.Prompts.agent_email_prompt`.
    2. *Delivery layer* - :func:`send_report_email` sends that report over
       SMTP using the credentials from ``Backend.Config.settings`` (env vars
       ``SMTP_HOST`` / ``SMTP_PORT`` / ``SMTP_USERNAME`` / ``SMTP_PASSWORD``).

SMTP is best-effort: when the server is not configured (missing or
placeholder values), the email is still composed and returned while a clear
warning is logged, so the API never fails just because mail is unset.
"""

# ============================================================================
# Imports
# ============================================================================
import html  # entity-unescape for the plain-text mirror of the HTML body
import json  # exchange the recommendation / report payloads
import logging  # structured, level-aware logging shared with the rest of the app
import re  # strip HTML tags when building the text/plain alternative
import smtplib  # SMTP delivery of the composed report
import sys  # ensure the project root is importable when run directly
from email.message import EmailMessage  # MIME-free text message builder
from pathlib import Path  # cross-platform path handling
from typing import Any  # typing for the JSON-able report dict

# Microsoft Agent Framework - the Agent type for type annotations.
from agent_framework import Agent

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Agents/email_agent.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

# Shared factory: create_agent (client + wiring) and the run_agent helper.
from Backend.Agents.agent_factory import create_agent, run_agent

# The email-writing instructions live in the prompt store, never inline here.
from Backend.Agents.Prompts.agent_email_prompt import EMAIL_AGENT_INSTRUCTIONS
from Backend.Config import settings

logger = logging.getLogger(name=__name__)


# ============================================================================
# Agent layer (compose the email with the LLM)
# ============================================================================
def create_email_agent(
    *,
    model: str | None = None,
    azure_endpoint: str | None = None,
    api_version: str | None = None,
    api_key: str | None = None,
) -> Agent:
    """Build the MAF "Email Report Agent".

    The agent has no tools - it only rewrites the supplied recommendation into
    an email.  All Azure OpenAI wiring comes from the shared factory
    (:func:`Backend.Agents.agent_factory.create_agent`).

    Args:
        model / azure_endpoint / api_version / api_key: Optional connection
            overrides; all default to the project settings.

    Returns:
        A constructed ``agent_framework.Agent``.  Call ``await agent.run(...)``.
    """
    return create_agent(
        name="Email Report Agent",
        instructions=EMAIL_AGENT_INSTRUCTIONS,
        tools=[],
        model=model,
        azure_endpoint=azure_endpoint,
        api_version=api_version,
        api_key=api_key,
    )


async def run_email_agent(user_input: str, agent: Agent | None = None) -> str:
    """Run the email agent on ``user_input`` and return the text reply.

    Thin wrapper over the factory's shared :func:`run_agent` helper.
    """
    return await run_agent(
        user_input,
        agent=agent,
        create=create_email_agent,
        label="Email Agent",
    )


def _extract_report(text: str) -> dict[str, str]:
    """Parse the agent reply into a ``{subject, body}`` report.

    Tries ``json.loads`` on the whole reply first, then on the outermost
    ``{ ... }`` span.  Falls back to a generic subject + the raw text when no
    JSON object is recoverable, so the pipeline still delivers *something*.
    """
    candidate = text.strip()
    for attempt in (candidate,):
        try:
            parsed = json.loads(attempt)
            if (
                isinstance(parsed, dict)
                and parsed.get("subject")
                and parsed.get("body")
            ):
                return {
                    "subject": str(object=parsed["subject"]),
                    "body": str(object=parsed["body"]),
                }
        except json.JSONDecodeError:
            pass

    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(s=candidate[start : end + 1])
            if (
                isinstance(parsed, dict)
                and parsed.get("subject")
                and parsed.get("body")
            ):
                return {
                    "subject": str(object=parsed["subject"]),
                    "body": str(object=parsed["body"]),
                }
        except json.JSONDecodeError:
            pass

    logger.warning("Email agent reply had no JSON report; using raw text fallback.")
    return {"subject": "Your WattPilot energy report", "body": candidate}


def _to_plain_text(html_fragment: str) -> str:
    """Strip HTML tags from a report body to build the ``text/plain`` mirror.

    Tags are removed and HTML entities unescaped so the plain-text
    alternative reads naturally in clients that ignore ``multipart/alternative``
    HTML parts (or where the user prefers no rich content).
    """
    text = re.sub(pattern=r"<[^>]+>", repl=" ", string=html_fragment)
    text = html.unescape(s=text)
    text = re.sub(pattern=r"[ \t]{2,}", repl=" ", string=text)
    return re.sub(pattern=r" *\n *", repl="\n", string=text).strip()


def _is_html(fragment: str) -> bool:
    """Whether a report body is HTML (contains an actual opening tag)."""
    return bool(re.search(pattern=r"<[a-z][^>]*>", string=fragment, flags=re.IGNORECASE))


def _body_to_html(body: str) -> str:
    """Render a plain-text mailer body as an HTML fragment with line breaks.

    HTML email clients collapse literal newlines to spaces, so every line of
    the body is terminated with ``<br>`` for the breaks to survive.  Non-list
    lines use a double ``<br><br>`` for a larger gap between sections; lines
    in the appliance bullet list (starting with ``-`` / ``*``) keep a single
    ``<br>`` so the bullets read tightly.  Blank lines are ignored (section
    gaps come from the ``<br>`` spacing, not from the literal body).  The
    optional ``<strong>`` tags already in the body are preserved as-is.
    """
    rows: list[str] = []
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        break_tag = "<br>" if re.match(pattern=r"^[-*]\s", string=line) else "<br><br>"
        rows.append(f"{line}{break_tag}")
    return "\n".join(rows)


async def compose_report(
    recommendation: dict[str, Any],
    *,
    to: str | None = None,
    name: str | None = None,
    agent: Agent | None = None,
) -> dict[str, str]:
    """Compose an email report for a recommendation payload.

    Args:
        recommendation: The validated recommendation dict (``summary`` +
            ``actions``) from the optimization workflow.
        to: Recipient email address; ``None`` falls back to the configured
            defaults in :data:`~Backend.Config.settings.SMTP_TO_EMAIL` /
            :data:`~Backend.Config.settings.SMTP_USERNAME`.
        name: Optional recipient name used in the email greeting.
        agent: Optional pre-built email agent (usually left ``None``).

    Returns:
        ``{"to": ..., "subject": ..., "body": ...}``.
    """
    recipient = (to or settings.SMTP_TO_EMAIL or settings.SMTP_USERNAME) or ""
    payload = json.dumps(obj=recommendation, ensure_ascii=False)
    greeting = (
        f" Address the homeowner by name ({name})." if name else ""
    )
    prompt = (
        "Write the customer email for this recommendation. "
        f"Return the JSON report only.{greeting}\n\n{payload}"
    )
    reply = await run_email_agent(prompt, agent=agent)
    report = _extract_report(reply)
    report["to"] = recipient
    return report


# ============================================================================
# Delivery layer (send the email over SMTP)
# ============================================================================
def send_report_email(report: dict[str, str]) -> None:
    """Send a composed report over SMTP using the configured credentials.

    The ``body`` is enriched HTML (bold/italic, from the email agent), so the
    message is sent as ``multipart/alternative`` with a ``text/html`` part and
    a plain-text mirror built by :func:`_to_plain_text`.  If a caller supplies
    a plain-text body (no HTML tags) the message is sent as simple text.

    Args:
        report: ``{"to", "subject", "body"}`` as produced by
            :func:`compose_report`.

    Raises:
        RuntimeError: if SMTP is not configured, login fails, or the upstream
            server rejects the message.
    """
    if not settings.smtp_configured():
        raise RuntimeError(
            "SMTP is not configured: set SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD "
            "in .env (SMTP_HOST must not be the placeholder 'smtp.example.com')."
        )
    smtp_host = settings.SMTP_HOST
    if smtp_host is None:
        raise RuntimeError("SMTP is not configured: SMTP_HOST is missing.")
    smtp_username = settings.SMTP_USERNAME
    smtp_password = settings.SMTP_PASSWORD
    if smtp_username is None or smtp_password is None:
        raise RuntimeError(
            "SMTP is not configured: SMTP_USERNAME and SMTP_PASSWORD are required."
        )

    message = EmailMessage()
    message["Subject"] = report["subject"]
    message["From"] = settings.SMTP_FROM
    message["To"] = report["to"]
    if _is_html(report["body"]):
        message.set_content(_to_plain_text(report["body"]))
        message.add_alternative(_body_to_html(report["body"]), subtype="html")
    else:
        message.set_content(report["body"])

    try:
        with smtplib.SMTP(
            host=smtp_host,
            port=settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT,
        ) as server:
            if settings.SMTP_USE_STARTTLS:
                server.starttls()  # port 587 submission server
            server.login(user=smtp_username, password=smtp_password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(f"SMTP send failed: {exc}") from exc

    logger.info(
        "Email report sent to %s (subject=%r).", report["to"], report["subject"]
    )


# ============================================================================
# Combined flow (compose + deliver)
# ============================================================================
async def email_report(
    recommendation: dict[str, Any],
    *,
    to: str | None = None,
    name: str | None = None,
    agent: Agent | None = None,
) -> dict[str, str]:
    """Compose the customer email for a recommendation and send it via SMTP.

    SMTP is best-effort: if the mail server is not configured the email is
    still composed and returned (with a warning logged), so callers always get
    the report to render or store.

    Args:
        recommendation: The validated recommendation dict from the workflow.
        to: Optional recipient override (defaults from settings).
        name: Optional recipient name used in the email greeting.
        agent: Optional pre-built email agent.

    Returns:
        ``{"to": ..., "subject": ..., "body": ...}`` (the agent's output).
    """
    report = await compose_report(
        recommendation=recommendation, to=to, name=name, agent=agent
    )
    try:
        send_report_email(report)
    except RuntimeError as exc:
        logger.warning("Email report composed but not sent: %s", exc)
    return report


# ============================================================================
# Example usage (run directly: python email_agent.py)
# ============================================================================
# Requires: AZURE_OPENAI_API_KEY (and endpoint/model/version) in .env or env.
if __name__ == "__main__":
    import asyncio

    settings.setup_logging(level="INFO")

    sample_recommendation = {
        "summary": "Tomorrow looks cooler with slight rain; shift laundry and "
        "the dishwasher to after 23:00 to dodge peak pricing.",
        "actions": [
            {
                "appliance": "Washing Machine",
                "recommendation": "Delay start to 23:00-00:00 off-peak.",
                "estimated_kwh_saving": 0.0,
                "estimated_cost_saving": 95.36,
                "currency": "INR",
            },
            {
                "appliance": "Air Conditioning",
                "recommendation": "Keep 19:00-23:00 but raise the set-point to 25-26 C.",
                "estimated_kwh_saving": 9.7,
                "estimated_cost_saving": 101.93,
                "currency": "INR",
            },
        ],
        "confidence": 0.9,
    }

    report = asyncio.run(main=email_report(sample_recommendation))
    output = json.dumps(obj=report, indent=2, ensure_ascii=False)
    # The Windows console codepage (e.g. cp1252) cannot encode every Unicode
    # character the model may emit, so write UTF-8 bytes straight to stdout.
    sys.stdout.buffer.write(f"{output}\n".encode())
