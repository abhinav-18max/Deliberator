"""Deterministic scripted provider.

This is what makes the whole pipeline testable without a network: every rung of the
ladder, every dropout path, and every degraded parse can be forced exactly. Phase 0 of the
build runs the complete deliberation on this provider alone.

Scripts are keyed `"<role>:<slug>"` first, then `"<role>"`, so panel models can be scripted
individually while referees are scripted once. Queue a bare Exception instance to make a
call fail; queue a string to return unparseable prose.
"""

import asyncio
from typing import Any

from .base import CallSpec, Completion, ProviderError, Usage


class FakeProvider:
    def __init__(
        self,
        responses: dict[str, list[Any]] | None = None,
        *,
        latency_ms: int = 0,
        cost_micros: int = 100,
    ) -> None:
        self.responses: dict[str, list[Any]] = {k: list(v) for k, v in (responses or {}).items()}
        self.latency_ms = latency_ms
        self.cost_micros = cost_micros
        self.calls: list[CallSpec] = []

    def _next(self, spec: CallSpec) -> Any:
        for key in (f"{spec.role}:{spec.slug}", spec.role):
            queue = self.responses.get(key)
            if queue:
                return queue.pop(0)
            if queue is not None:
                # Explicitly scripted but drained. Fail loudly instead of falling back to
                # a broader key — a test that makes more calls than it scripted has a bug
                # worth seeing.
                raise ProviderError(f"fake script exhausted for {key}")
        raise ProviderError(f"no fake response scripted for {spec.role}:{spec.slug}")

    async def complete(self, spec: CallSpec, *, timeout_s: float) -> Completion:
        self.calls.append(spec)
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)

        item = self._next(spec)
        if isinstance(item, BaseException):
            raise item

        annotations: list[dict[str, Any]] = []
        parsed: dict[str, Any] | None = None
        text = ""
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            parsed = item.get("__parsed__", item)
            annotations = item.get("__annotations__", [])
            text = item.get("__text__", "")
            if parsed is item:
                parsed = {k: v for k, v in item.items() if not k.startswith("__")}
        else:
            raise TypeError(f"unscriptable fake response: {type(item)!r}")

        return Completion(
            role=spec.role,
            slug=spec.slug,
            call_key=spec.key(),
            text=text,
            parsed=parsed,
            annotations=annotations,
            usage=Usage(prompt_tokens=100, completion_tokens=50, cost_micros=self.cost_micros),
            upstream_provider="fake",
            generation_id=f"fake-{len(self.calls)}",
            finish_reason="stop",
            latency_ms=self.latency_ms,
        )
