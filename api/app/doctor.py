"""`make doctor` — resolve every seat against reality before a run needs it.

Model slugs rot. A pinned slug that has been retired should fail here, at boot, with a
suggested replacement — not three stages into a deliberation someone is watching. This also
reports which invariants are currently satisfied by configuration versus assumed.
"""

import asyncio
import sys

from .calls import Caller
from .contracts import Role
from .prompts.loader import fragment
from .providers import catalog
from .providers.base import ProviderError
from .providers.openrouter import OpenRouterProvider
from .roles import ConfigError, ResolvedRole, RoleRegistry, family
from .schemas import SCHEMAS
from .settings import load_config, load_settings

OK = "ok"
WARN = "warn"
FAIL = "FAIL"

# Which output shape each seat is held to, for the probe below.
_SEAT_SCHEMA = {
    Role.COMPARATOR: "comparison",
    Role.VERIFIER: "verification",
    Role.SYNTHESIZER: "synthesis",
    Role.NORMALIZER: "normalizer",
    Role.RED_TEAM: "red_team",
}

_PROBE = fragment("capability_probe")


def _line(status: str, text: str) -> str:
    return f"  [{status:>4}] {text}"


async def _probe_seat(caller: Caller, role: ResolvedRole) -> tuple[str, str]:
    """Make one real, tiny call per referee seat.

    Reading `supported_parameters` is not enough: the catalogue reports the union across a
    model's endpoints, so a seat can pass every metadata check and still 404 on first use
    because no single endpoint honours the strict schema alongside everything else we send.
    A boot check that does not place a call is not a boot check.
    """
    schema_name = _SEAT_SCHEMA[role.role]
    out_model = SCHEMAS[schema_name]
    try:
        call = await caller.call(
            role=role.role.value,
            slug=role.slug,
            messages=[{"role": "user", "content": _PROBE}],
            prompt_version=role.prompt_version,
            out_model=out_model,
            schema_name=schema_name,
            fallback_slugs=role.fallbacks,
            timeout_s=60.0,
            allow_repair=False,
        )
    except ProviderError as exc:
        return FAIL, f"probe failed: {exc}"

    served = call.completion.slug
    detail = f"probe ok via {served}"
    if served != role.slug:
        detail += f" (chain fell back from {role.slug})"
    if call.completion.routing_unpinned:
        return WARN, detail + " — strict routing had no endpoint, ran unpinned"
    if call.parsed is None:
        return WARN, detail + " — routed, but the schema was not honoured"
    return OK, detail


async def main() -> int:
    settings = load_settings()
    cfg = load_config()
    problems = 0
    warnings = 0
    out: list[str] = []

    out.append("environment")
    out.append(
        _line(OK if settings.openrouter_api_key else FAIL, "OPENROUTER_API_KEY present")
    )
    problems += 0 if settings.openrouter_api_key else 1
    out.append(
        _line(
            OK if settings.has_mongo else WARN,
            "MONGODB_URI present"
            if settings.has_mongo
            else "MONGODB_URI unset — traces will not persist",
        )
    )
    warnings += 0 if settings.has_mongo else 1

    caps = catalog.Capabilities()
    if settings.openrouter_api_key:
        try:
            caps = await catalog.fetch(settings.openrouter_api_key)
            out.append(_line(OK, f"catalogue fetched: {len(caps)} models"))
        except Exception as exc:  # noqa: BLE001 — doctor reports, never raises
            out.append(_line(WARN, f"catalogue unavailable ({exc}); capabilities unverified"))
            warnings += 1

    out.append("")
    out.append("panel shortlist")
    for slug in cfg.panel_shortlist:
        if not caps.known:
            out.append(_line(WARN, f"{slug} — unverified"))
            continue
        if not caps.has(slug):
            suggestions = caps.closest(slug)
            hint = f" — try {', '.join(suggestions)}" if suggestions else ""
            out.append(_line(FAIL, f"{slug} is not in the catalogue{hint}"))
            problems += 1
            continue
        window = caps.context_length(slug)
        structured = caps.supports_structured(slug)
        note = f"context {window or '?'}"
        note += ", strict json" if structured else ", no strict json (normalizer fallback)"
        out.append(_line(OK, f"{slug} — {note}"))

    families = {family(s) for s in cfg.panel_default}
    if len(families) < len(cfg.panel_default):
        out.append(
            _line(WARN, "default panel repeats a family; its votes are correlated")
        )
        warnings += 1

    out.append("")
    out.append("referee seats")
    registry = RoleRegistry(cfg, caps if caps.known else None)
    provider = OpenRouterProvider(settings) if settings.openrouter_api_key else None
    caller = Caller(provider) if provider else None

    for role in (Role.COMPARATOR, Role.VERIFIER, Role.SYNTHESIZER, Role.NORMALIZER, Role.RED_TEAM):
        try:
            resolved = registry.resolve(role, panel=cfg.panel_default)
        except ConfigError as exc:
            out.append(_line(FAIL, f"{role.value}: {exc}"))
            problems += 1
            continue
        status = OK if resolved.enabled and not resolved.on_panel else WARN
        detail = f"{role.value} -> {resolved.slug} ({resolved.prompt_version})"
        if not resolved.enabled:
            detail += " — DISABLED"
        if resolved.on_panel:
            detail += " — also on the panel"
        out.append(_line(status, detail))
        warnings += 0 if status == OK else 1
        for note in resolved.notes:
            out.append(f"         · {note}")

        if caller and resolved.enabled:
            probe_status, probe_detail = await _probe_seat(caller, resolved)
            out.append(f"         · {probe_detail}")
            if probe_status == FAIL:
                problems += 1
            elif probe_status == WARN:
                warnings += 1

    if provider:
        await provider.aclose()

    comparator = cfg.roles.get("comparator")
    if comparator:
        verified = cfg.is_verified(comparator.chain[0], comparator.prompt_version)
        out.append(
            _line(
                OK if verified else WARN,
                "comparator config is in the verified registry"
                if verified
                else f"comparator ({comparator.chain[0]}, {comparator.prompt_version}) is not in "
                "the verified registry — runs will be stamped `gate: unvalidated`",
            )
        )
        warnings += 0 if verified else 1

    if settings.has_mongo:
        out.append("")
        out.append("storage")
        try:
            from .store.mongo import MongoStore

            store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
            await store.ensure_ready()
            await store.close()
            out.append(_line(OK, f"Atlas reachable, indexes ensured on {settings.mongodb_db}"))
        except Exception as exc:  # noqa: BLE001
            out.append(_line(FAIL, f"Mongo unreachable: {exc}"))
            problems += 1

    out.append("")
    out.append(f"config fingerprint {cfg.fingerprint()}")
    out.append(f"{problems} problem(s), {warnings} warning(s)")
    print("\n".join(out))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
