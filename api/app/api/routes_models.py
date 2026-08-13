"""The panel picker's data source.

The list is curated rather than the whole catalogue, so the family-diversity and
minimum-context rules are enforceable and no model that ignores the response schema can break
a fan-out mid-demo. Capability flags come from OpenRouter's own catalogue when it has been
consulted; `null` means unverified rather than unsupported.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..roles import family

router = APIRouter(tags=["models"])


class ModelInfo(BaseModel):
    slug: str
    family: str
    in_default: bool
    structured_outputs: bool | None = None
    web_search: bool | None = None
    context_length: int | None = None


@router.get("/models", response_model=list[ModelInfo])
async def list_models(request: Request) -> list[ModelInfo]:
    state = request.app.state
    cfg = state.config
    caps = getattr(state, "capabilities", None)
    return [
        ModelInfo(
            slug=slug,
            family=family(slug),
            in_default=slug in cfg.panel_default,
            structured_outputs=caps.supports_structured(slug) if caps else None,
            web_search=caps.supports_web(slug) if caps else None,
            context_length=caps.context_length(slug) if caps else None,
        )
        for slug in cfg.panel_shortlist
    ]
