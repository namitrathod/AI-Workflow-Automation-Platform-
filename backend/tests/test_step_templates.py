from __future__ import annotations

import uuid

import pytest

from app.schemas.step import BuiltinStep
from app.steps.context import StepContext
from app.steps.handlers.builtin import BuiltinStepHandler
from app.steps.template import resolve_path, resolve_template


def test_resolve_payload_template() -> None:
    ctx = StepContext(
        tenant_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        trigger="email_received",
        payload={"subject": "Hello", "body": "World"},
        step_index=0,
        step_spec=BuiltinStep(id="s1", name="summarize_email"),
    )
    assert resolve_template("Subject: {{payload.subject}}", ctx) == "Subject: Hello"


def test_resolve_prior_step_output() -> None:
    ctx = StepContext(
        tenant_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        trigger="email_received",
        payload={},
        step_index=1,
        step_spec=BuiltinStep(id="classify", name="classify_intent"),
        prior_outputs={
            "summarize_email": {"result": {"summary": "Billing issue"}},
        },
    )
    assert resolve_path("steps.summarize_email.result.summary", ctx) == "Billing issue"


@pytest.mark.asyncio
async def test_create_ticket_tool() -> None:
    ctx = StepContext(
        tenant_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        trigger="email_received",
        payload={},
        step_index=2,
        step_spec=BuiltinStep(id="create_ticket", name="create_ticket"),
        prior_outputs={
            "summarize_email": {"result": {"summary": "Need refund"}},
            "classify_intent": {"result": {"intent": "billing", "priority": "high"}},
        },
    )
    out = await BuiltinStepHandler().run(ctx)
    assert out["type"] == "tool"
    assert out["result"]["title"] == "billing"
    assert out["result"]["priority"] == "high"
    assert out["result"]["ticket_id"].startswith("TICK-")
