"""Record and replay model calls by call key.

This is what `call_key` was for. Three things fall out of it:

*   **The eval harness is free after its first run.** Comparator calibration is measured against
    recorded completions, so a regression check costs nothing and works offline.
*   **The demo needs no API key.** `DELIBRATOR_REPLAY=1` serves every call from the recorded
    fixtures, so a reviewer who never gets a key still sees the whole product work.
*   **A prompt edit correctly misses.** The prompt version is part of the key, so changing a
    prompt invalidates its recordings instead of silently replaying the old behaviour.

Recordings are fixtures, not a cache: nothing expires them.
"""

from ..store.base import StorePort
from .base import CallSpec, Completion, LLMPort, ProviderError


class CachingProvider:
    """Serves recorded completions; records new ones when an inner provider is available."""

    def __init__(
        self,
        store: StorePort,
        inner: LLMPort | None = None,
        *,
        record: bool = True,
    ) -> None:
        self.store = store
        self.inner = inner
        self.record = record
        self.hits = 0
        self.misses = 0

    async def complete(self, spec: CallSpec, *, timeout_s: float) -> Completion:
        key = spec.key()
        doc = await self.store.get_completion(key)
        if doc is not None:
            self.hits += 1
            return Completion.model_validate(doc)

        self.misses += 1
        if self.inner is None:
            raise ProviderError(
                f"no recorded completion for {spec.role}:{spec.slug} (key {key[:12]}). "
                "Replay mode can only serve calls that were recorded — run once with a key, "
                "or check whether a prompt version changed."
            )

        completion = await self.inner.complete(spec, timeout_s=timeout_s)
        if self.record:
            await self.store.put_completion(key, completion.model_dump(mode="json"))
        return completion
