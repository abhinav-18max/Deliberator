"""Strict JSON schemas for structured output, generated from the wire contracts.

Strict mode has two hard requirements that pydantic's default schema does not meet: every
object must set `additionalProperties: false`, and every property must be listed as
required (optionality is expressed as a null union instead). Generating the schema from the
same class the response is parsed into means a prompt change can never leave the schema and
the parser describing different shapes.

Referee calls are sent with `require_parameters: true`, so OpenRouter will only route them
to a provider that actually honours this. Panel calls are not: that would exclude most of
the catalogue, and a panel model's formatting must never drive control flow anyway.
"""

from typing import Any

from pydantic import BaseModel

from .contracts.wire import (
    ComparisonOut,
    DebateTurnOut,
    NormalizerOut,
    PanelAnswerOut,
    RedTeamOut,
    SynthesisOut,
    VerificationOut,
)


def _strictify(node: Any) -> Any:
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node

    out = {k: _strictify(v) for k, v in node.items() if k != "default"}
    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"].keys())
    return out


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    return _strictify(model.model_json_schema())


def response_format(name: str, model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": strict_schema(model)},
    }


# Registry keyed by the name used in CallSpec.schema_name, so the trace records which
# shape a call was held to.
SCHEMAS: dict[str, type[BaseModel]] = {
    "panel_answer": PanelAnswerOut,
    "comparison": ComparisonOut,
    "debate_turn": DebateTurnOut,
    "verification": VerificationOut,
    "synthesis": SynthesisOut,
    "red_team": RedTeamOut,
    "normalizer": NormalizerOut,
}
