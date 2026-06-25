from app.llm.json_parse import parse_json_content
from app.schemas.workflow import WorkflowDefinition


def test_string_steps_normalize_to_builtin() -> None:
    wf = WorkflowDefinition.model_validate(
        {
            "trigger": "email_received",
            "steps": ["summarize_email", "classify_intent"],
        }
    )
    assert len(wf.steps) == 2
    assert wf.steps[0].type == "builtin"
    assert wf.steps[0].id == "summarize_email"


def test_rich_llm_step() -> None:
    wf = WorkflowDefinition.model_validate(
        {
            "trigger": "manual",
            "steps": [
                {
                    "type": "llm",
                    "id": "greet",
                    "prompt": "Say hi to {{payload.name}} as JSON: {\"message\": \"...\"}",
                    "output_schema": {"message": "string"},
                }
            ],
        }
    )
    assert wf.steps[0].type == "llm"


def test_parse_json_plain() -> None:
    assert parse_json_content('{"summary": "ok"}') == {"summary": "ok"}


def test_parse_json_codeblock() -> None:
    text = 'Here is the result:\n```json\n{"intent": "support"}\n```'
    assert parse_json_content(text) == {"intent": "support"}
