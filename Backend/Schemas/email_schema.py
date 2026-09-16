"""
Email / plan-report schema.

Defines the inbound contract of the email reporting API
(``Backend/api/Routes/email_plan.py``): a client submits an existing
optimization plan (the JSON produced by the recommendations workflow,
carried verbatim under ``plan_json``) plus the recipient's email address and
an optional name, and the Email Report Agent formats it into a human-friendly
email and sends it via SMTP.

The plan itself is intentionally left as a free-form ``dict``: it is the
workflow's recommendation payload that the LLM rewrites (never re-validated
field-by-field), so the mailer stays tolerant of plan-shaped JSON.
"""

import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic.networks import EmailStr

# Make the project root importable so `Backend.*` imports resolve even when
# this module is launched directly (python Backend/Schemas/email_schema.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(object=PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(object=PROJECT_ROOT))


class EmailPlanRequest(BaseModel):
    """Request body for the email-reporting endpoint.

    Attributes:
        plan_json: The optimization plan to mail - the recommendation payload
            (``summary`` + ``actions``) from the workflow, passed through.
        email: Recipient address, validated by pydantic's ``EmailStr``.
        name: Homeowner name used for the greeting (defaults to "User").
    """

    plan_json: dict = Field(
        description="The optimization plan (summary + actions) to email."
    )
    email: EmailStr = Field(description="Recipient email address.")
    name: str = Field(default="User", min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _name_sane(cls, value: str) -> str:
        """Keep the greeting safe by trimming surrounding whitespace."""
        return value.strip()

    @field_validator("plan_json")
    @classmethod
    def _plan_has_shape(cls, value: dict) -> dict:
        """Floor-check the plan is a recommendation-shaped dict.

        Tolerated: a plan missing the optional outlook fields, so long as it
        carries either a ``summary`` or an ``actions`` list - the two things
        the email agent actually rewrites.
        """
        has_summary = isinstance(value.get("summary"), str) and bool(value.get("summary"))
        has_actions = isinstance(value.get("actions"), list) and bool(value.get("actions"))
        if not (has_summary or has_actions):
            raise ValueError(
                "plan_json must contain a non-empty 'summary' and/or 'actions' list."
            )
        return value

    model_config = {
        "json_schema_extra": {
            "example": {
                "plan_json": {
                    "summary": "Tomorrow will be cooler than average with "
                    "temperatures between 14.9C and 26.9C, providing an "
                    "opportunity to optimize energy usage.",
                    "actions": [
                        {
                            "appliance": "Air Conditioning",
                            "recommendation": "Set to 24C and use it only between 1PM-5PM.",
                            "estimated_kwh_saving": 1.7,
                            "estimated_cost_saving": 18.5,
                            "currency": "INR",
                        },
                        {
                            "appliance": "Washing Machine",
                            "recommendation": "Run during off-peak hours (8PM-10PM) to wash full loads.",
                            "estimated_kwh_saving": 0.2,
                            "estimated_cost_saving": 2.2,
                            "currency": "INR",
                        },
                    ],
                },
                "email": "your-email@example.com",
                "name": "User Name",
            }
        }
    }


# ---- Example usage (run directly: python email.py) --------------------------
if __name__ == "__main__":
    request = EmailPlanRequest(
        plan_json={
            "summary": "Shift cooling off-peak.",
            "actions": [
                {
                    "appliance": "Air Conditioning",
                    "recommendation": "Run 23:00-03:00.",
                    "estimated_kwh_saving": 2.0,
                    "estimated_cost_saving": 57.0,
                    "currency": "INR",
                }
            ],
        },
        email="owner@example.com",
        name=" User ",
    )
    print(f"Validated request: {request.model_dump()!r}")