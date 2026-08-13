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

    def supports_native_web(self, slug: str) -> bool | None:
        """Whether the model has its *own* search that OpenRouter's `engine: "native"` can drive.

        Measured by `web_search_options` in the advertised parameters. As of writing this is a
        short list — notably it does not include any Gemini model, so provider-native grounding
        is not a route to a current-knowledge verifier. Gateway retrieval (`engine: "exa"`) has
        no model requirement, which is why it is the default.
        """
        if slug not in self._entries:
            return None
        return "web_search_options" in self._params(slug)

    # Kept as the name the role registry asks for; gateway retrieval works with any model, so
    # the only real capability question is whether native search is available.
    supports_web = supports_native_web

    def price_per_token(self, slug: str) -> tuple[float, float] | None:
        """(prompt, completion) USD per token, or None if unknown."""
        pricing = (self._entries.get(slug) or {}).get("pricing") or {}
        try:
            return float(pricing["prompt"]), float(pricing["completion"])
        except (KeyError, TypeError, ValueError):
            return None

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
