"""OpenRouter transport: one key, one schema, every model.

Three details here matter more than they look:

*   **`require_parameters` is set for referees only.** Structured-output support on OpenRouter
    is per-endpoint, not per-model, so this forces routing to a provider that actually honours
    the schema. Panel calls deliberately do not set it — that would exclude much of the
    catalogue, and a caller-selected model's formatting must never drive control flow.
    The pin can also be *too* strict: `supported_parameters` in the catalogue is the union
    across a model's endpoints, so a model advertising `structured_outputs` may still have no
    single endpoint that honours it alongside everything else we send, and the request 404s.
    That case is retried once unpinned — schema still requested, response still parsed — and
    the completion is marked `routing_unpinned` so the trace shows the weaker guarantee.
*   **Retrieval engine is a config choice, and citations are normalised either way.**
    `engine: "native"` drives the model's own search; `engine: "exa"` has OpenRouter run the
    search and inject the results. Both come back as OpenAI-shaped `url_citation` annotations,
    so one parser covers every provider. The default is `exa` because the catalogue shows
    native search advertised by only a handful of models — none of them Gemini — and pinning
    the verifier to that list would mean pinning it to a stale-knowledge model, which is the
    opposite of what a verifier is for.
*   **The upstream provider and generation id are recorded.** A slug can be served by several
    backends with different quantisations, and `seed` is not honoured everywhere. So we do not
    promise determinism — we promise replay, and the trace carries what actually served the call.
"""

import asyncio
from typing import Any

import httpx

from ..schemas import SCHEMAS, response_format
from ..settings import Settings
from .base import (
    CallSpec,
    Completion,
    ModelUnavailable,
    ProviderError,
    ProviderTimeout,
    Usage,
)

BASE_URL = "https://openrouter.ai/api/v1"

# Seats whose output drives control flow. These get strict schemas and pinned routing.
REFEREE_ROLES = {"comparator", "verifier", "synthesizer", "normalizer", "red_team"}

_RETRY_STATUS = {408, 429, 500, 502, 503, 504}

# OpenRouter answers 404 for two very different situations: the model does not exist, and no
# endpoint can satisfy every parameter we pinned. The second is recoverable by unpinning.
_NO_ENDPOINT = "no endpoints found"


class OpenRouterProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.settings = settings
        self.max_attempts = max_attempts
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": settings.openrouter_app_url,
                "X-Title": settings.openrouter_app_title,
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _body(self, spec: CallSpec) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": spec.slug,
            "messages": spec.messages,
            "temperature": spec.temperature,
            "usage": {"include": True},  # ask for real cost back, for the trace footer
        }
        model = SCHEMAS.get(spec.schema_name or "")
        if model is not None:
            body["response_format"] = response_format(spec.schema_name or "out", model)
        if spec.role in REFEREE_ROLES:
            body["provider"] = {"require_parameters": True, "allow_fallbacks": True}
        if spec.web:
            body["plugins"] = [
                {"id": "web", "engine": spec.web_engine, "max_results": spec.max_results}
            ]
        return body

    async def complete(self, spec: CallSpec, *, timeout_s: float) -> Completion:
        body = self._body(spec)
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self._client.post(
                    "/chat/completions", json=body, timeout=timeout_s
                )
            except httpx.TimeoutException as exc:
                last_error = ProviderTimeout(f"{spec.slug} timed out after {timeout_s}s")
                if attempt == self.max_attempts:
                    raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = ProviderError(f"{spec.slug}: {exc}")
                if attempt == self.max_attempts:
                    raise last_error from exc
            else:
                if response.status_code == 404:
                    if _NO_ENDPOINT in response.text.lower() and "provider" in body:
                        # The catalogue advertises the union of parameters across endpoints,
                        # while require_parameters demands one endpoint honouring all of them.
                        # Drop the pin, keep the schema, and record the weaker guarantee.
                        body.pop("provider")
                        unpinned = await self._client.post(
                            "/chat/completions", json=body, timeout=timeout_s
                        )
                        if unpinned.status_code < 400:
                            completion = self._to_completion(spec, unpinned)
                            return completion.model_copy(update={"routing_unpinned": True})
                    raise ModelUnavailable(
                        f"{spec.slug} is not routable on OpenRouter: {response.text[:200]}"
                    )
                if response.status_code in _RETRY_STATUS and attempt < self.max_attempts:
                    await asyncio.sleep(0.5 * 2 ** (attempt - 1))
                    continue
                if response.status_code >= 400:
                    raise ProviderError(
                        f"{spec.slug}: {response.status_code} {response.text[:300]}"
                    )
                return self._to_completion(spec, response)

            await asyncio.sleep(0.5 * 2 ** (attempt - 1))

        raise last_error or ProviderError(f"{spec.slug}: exhausted attempts")

    @staticmethod
    def _to_completion(spec: CallSpec, response: httpx.Response) -> Completion:
        data = response.json()
        choices = data.get("choices") or [{}]
        message = choices[0].get("message") or {}
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        return Completion(
            role=spec.role,
            slug=spec.slug,
            call_key=spec.key(),
            text=message.get("content") or "",
            parsed=None,  # content is text; the caller extracts and validates
            annotations=message.get("annotations") or [],
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                cost_micros=int(round(float(cost) * 1_000_000)) if cost else 0,
            ),
            upstream_provider=data.get("provider"),
            generation_id=data.get("id"),
            finish_reason=choices[0].get("finish_reason"),
            latency_ms=int(response.elapsed.total_seconds() * 1000) if response.elapsed else 0,
        )
