"""One place where a model call is made, parsed, repaired and accounted for.

Parsing policy differs by seat and that difference is the architecture, not an accident.
Referee calls are sent with a strict schema and a provider that honours it, so a parse
failure there is a configuration problem. Panel calls are best-effort: OpenRouter's schema
support is per-endpoint rather than per-model, so a caller-selected model may simply ignore
the schema. Those get one targeted repair attempt and then fall through to the normalizer —
a panel model's formatting must never drive control flow.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .providers.base import CallSpec, Completion, LLMPort

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

REPAIR_INSTRUCTION = (
    "Your previous reply did not match the required JSON shape. Return only the JSON object, "
    "with no prose, no markdown fence, and every required field present."
)


@dataclass
class Call:
    completion: Completion
    parsed: BaseModel | None = None
    repaired: bool = False

    @property
    def ok(self) -> bool:
        return self.parsed is not None


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    candidates = [text]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))
    # A model that wraps JSON in a sentence is common enough to be worth one cheap attempt.
    brace = text.find("{")
    if brace > 0:
        candidates.append(text[brace:])
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None


class Caller:
    def __init__(self, provider: LLMPort, on_call: Callable[[Completion], None] | None = None):
        self.provider = provider
        self.on_call = on_call

    async def call(
        self,
        *,
        role: str,
        slug: str,
        messages: list[dict[str, str]],
        prompt_version: str = "",
        out_model: type[T] | None = None,
        schema_name: str | None = None,
        web: bool = False,
        temperature: float = 0.0,
        timeout_s: float = 90.0,
        allow_repair: bool = True,
        skip_repair_if: Callable[[Completion], bool] | None = None,
    ) -> Call:
        spec = CallSpec(
            role=role,
            slug=slug,
            messages=messages,
            prompt_version=prompt_version,
            schema_name=schema_name,
            json_schema=None,
            temperature=temperature,
            web=web,
        )
        completion = await self.provider.complete(spec, timeout_s=timeout_s)
        if self.on_call:
            self.on_call(completion)

        if out_model is None:
            return Call(completion=completion)

        parsed = self._parse(completion, out_model)
        if parsed is not None or not allow_repair:
            return Call(completion=completion, parsed=parsed)
        if skip_repair_if is not None and skip_repair_if(completion):
            # Not every unparseable reply is a formatting problem. A refusal is a refusal;
            # re-asking for JSON spends a call to be told no twice.
            return Call(completion=completion, parsed=None)

        repair_spec = spec.model_copy(
            update={
                "messages": [
                    *messages,
                    {"role": "assistant", "content": completion.text[:2000]},
                    {"role": "user", "content": REPAIR_INSTRUCTION},
                ]
            }
        )
        repaired = await self.provider.complete(repair_spec, timeout_s=timeout_s)
        if self.on_call:
            self.on_call(repaired)
        return Call(
            completion=repaired,
            parsed=self._parse(repaired, out_model),
            repaired=True,
        )

    @staticmethod
    def _parse(completion: Completion, out_model: type[T]) -> T | None:
        raw = completion.parsed or extract_json(completion.text)
        if raw is None:
            return None
        try:
            return out_model.model_validate(raw)
        except ValidationError:
            return None
