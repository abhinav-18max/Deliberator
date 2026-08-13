"""OpenRouter's model catalogue as a capability index.

Two rules in the design depend on real capability data rather than assumptions: the comparator
must be routed to an endpoint that honours strict JSON schema, and the envelope must fit every
selected model's context window (truncation that hits one panelist and not another manufactures
a disagreement judgement never produced).

`None` from any lookup means "not in the catalogue" — unverified, not unsupported. Callers treat
that as permission with a note in the trace, and `make doctor` is where an operator gets
certainty instead.
"""

from typing import Any

import httpx

from .openrouter import BASE_URL


class Capabilities:
    def __init__(self, entries: dict[str, dict[str, Any]] | None = None) -> None:
        self._entries = entries or {}

    @property
    def known(self) -> bool:
        return bool(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def has(self, slug: str) -> bool:
        return slug in self._entries

    def _params(self, slug: str) -> set[str]:
        return set((self._entries.get(slug) or {}).get("supported_parameters") or [])

    def supports_structured(self, slug: str) -> bool | None:
        if slug not in self._entries:
            return None
        params = self._params(slug)
        return "structured_outputs" in params or "response_format" in params

    def supports_web(self, slug: str) -> bool | None:
        if slug not in self._entries:
            return None
        entry = self._entries[slug]
        # A model is groundable through OpenRouter either by supporting tools natively or by
        # being one of the providers whose built-in search the web plugin can drive.
        params = self._params(slug)
        return bool(entry.get("supports_web") or "tools" in params)

    def context_length(self, slug: str) -> int | None:
        entry = self._entries.get(slug)
        if not entry:
            return None
        value = entry.get("context_length")
        return int(value) if value else None

    def closest(self, slug: str, limit: int = 3) -> list[str]:
        """Suggestions for a slug that has rotted away, so doctor can say what to use instead."""
        family, _, rest = slug.partition("/")
        stem = rest.split("-")[0] if rest else ""
        same_family = [s for s in self._entries if s.startswith(f"{family}/")]
        preferred = [s for s in same_family if stem and stem in s]
        return (preferred + [s for s in same_family if s not in preferred])[:limit]


async def fetch(api_key: str | None = None, *, timeout_s: float = 30.0) -> Capabilities:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers) as client:
        response = await client.get("/models", timeout=timeout_s)
        response.raise_for_status()
        payload = response.json()
    entries = {
        entry["id"]: entry for entry in payload.get("data", []) if entry.get("id")
    }
    return Capabilities(entries)
