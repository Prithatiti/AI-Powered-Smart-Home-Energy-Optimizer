"""
Email plan-report API endpoint.

    POST /api/v1/email/plan  ->  format & send an optimization plan via email

Accepts an :class:`~Backend.Schemas.email.EmailPlanRequest` (an existing
optimization plan plus a recipient address) and hands it to the Email Report
Agent (:func:`Backend.Agents.email_agent.email_report`), which rewrites the
plan into a human-friendly email and submits it over the configured SMTP
server.  The composed report (``to`` / ``subject`` / ``body``) is returned so
callers can confirm or store it.
"""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly
# (python Backend/api/Routes/email_plan.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))

from Backend.Agents.email_agent import email_report
from Backend.Schemas import EmailPlanRequest

router = APIRouter(prefix="/api/v1/email", tags=["email"])

logger = logging.getLogger(__name__)


@router.post(
    path="/plan",
    summary="Format and send an optimization plan as an email report",
    tags=["Email"],
)
async def send_plan_email(payload: EmailPlanRequest) -> dict:
    """Compose and email an existing optimization plan.

    Args:
        payload: The validated plan payload plus the recipient address and
            (optional) name.

    Returns:
        The composed report - ``{"to", "subject", "body"}``.  Delivery is
        best-effort: when SMTP is unconfigured the email is still composed and
        returned (a warning is logged), so the report can be rendered/stored.

    Raises:
        HTTPException: 502 when the Email Report Agent fails to compose.
    """
    try:
        report = await email_report(
            recommendation=payload.plan_json,
            to=str(object=payload.email),
            name=payload.name,
        )
    except Exception as exc:
        logger.exception("Email plan workflow raised: %s", exc)
        raise HTTPException(
            status_code=502, detail="Email report agent failed."
        ) from exc

    logger.info(
        "Emailed optimization plan to %s (subject=%r).",
        report.get("to"),
        report.get("subject"),
    )
    return report


# ---- Example usage (run directly: python email_plan.py) ---------------------
if __name__ == "__main__":
    from Backend.Config import settings

    settings.setup_logging(level="INFO")

    import asyncio
    import json as _json

    request = EmailPlanRequest(
        plan_json={
            "summary": "Shift cooling and laundry off-peak to cut the bill.",
            "actions": [
                {
                    "appliance": "Air Conditioning",
                    "recommendation": "Run 23:00-03:00 off-peak.",
                    "estimated_kwh_saving": 2.0,
                    "estimated_cost_saving": 57.0,
                    "currency": "INR",
                }
            ],
        },
        email="owner@example.com",
        name="Aarav",
    )
    report = asyncio.run(
        main=email_report(
            recommendation=request.plan_json,
            to=str(object=request.email),
            name=request.name,
        )
    )
    output = _json.dumps(obj=report, indent=2, ensure_ascii=False)
    # The Windows console codepage (e.g. cp1252) cannot encode every Unicode
    # character the model may emit, so write UTF-8 bytes straight to stdout.
    sys.stdout.buffer.write(f"{output}\n".encode())