"""The model transport port.

Every model call in the system goes through this interface, which is what makes three
things possible: the real OpenRouter client, a deterministic fake for tests, and a replay
provider that serves recorded completions so the demo and the eval harness need no API
key.

`call_key` is the join between all three. It is the hash of everything that determines a
response, so a recorded completion can be served again only for an identical call — and
the moment a prompt version changes, the key changes and the cache correctly misses.
"""

import hashlib
import json
from typing import Any, Protocol

from pydantic import BaseModel, Field


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_micros: int = 0  # micro-USD; OpenRouter reports real cost per generation


class CallSpec(BaseModel):
    """Everything that identifies a call. Also everything that keys it."""

    role: str
    slug: str
    messages: list[dict[str, str]]
    prompt_version: str = ""
    schema_name: str | None = None
    temperature: float = 0.0
    web: bool = False  # grounded search — resolution only, never answering
    web_engine: str = "exa"  # "exa" = gateway retrieval, "native" = the model's own search
    max_results: int = 5

    def key(self) -> str:
        material = {
            "role": self.role,
            "slug": self.slug,
            "prompt_version": self.prompt_version,
            "messages": self.messages,
            "schema": self.schema_name,
            "temperature": self.temperature,
            "web": self.web,
            "web_engine": self.web_engine if self.web else None,
        }
        blob = json.dumps(material, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]


class Completion(BaseModel):
    role: str
    slug: str
    call_key: str
    text: str = ""
    parsed: dict[str, Any] | None = None

    # OpenRouter normalises citations from every provider's native search into this
    # OpenAI-shaped annotation list. The verifier's admissibility check reads it.
    annotations: list[dict[str, Any]] = Field(default_factory=list)

    usage: Usage = Field(default_factory=Usage)
    upstream_provider: str | None = None  # which backend actually served the slug
    generation_id: str | None = None
    finish_reason: str | None = None
    latency_ms: int = 0
    repaired: bool = False

    # True when strict routing found no endpoint and the call was retried without the
    # require_parameters pin. The schema was still requested and the response still parsed;
    # what is lost is the guarantee that the endpoint promised to honour it.
    routing_unpinned: bool = False


class ProviderError(RuntimeError):
    """Transport failed in a way the pipeline should treat as a dropout."""


class ProviderTimeout(ProviderError):
    pass


class ModelUnavailable(ProviderError):
    pass


class LLMPort(Protocol):
    async def complete(self, spec: CallSpec, *, timeout_s: float) -> Completion: ...
