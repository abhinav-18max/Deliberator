"""Role resolution and the invariants configuration is not allowed to break.

Each invariant has a *defined* failure mode rather than a generic error, because the right
response differs per seat:

| invariant                        | on violation                                     |
|----------------------------------|--------------------------------------------------|
| comparator emits strict schema   | reject the config — its output *is* control flow |
| verifier can ground              | disable rung 2 entirely, never guess             |
| synthesizer emits strict schema  | reject the config                                |
| optional seats capable           | disable that seat, run degraded                  |
| synthesizer/verifier off panel   | substitute down the chain, else stamp the run    |
| referee temperature              | clamped to 0 — control flow must not sample      |

Capability answers may be `None`, meaning "catalogue not consulted". That is allowed but
recorded: `make doctor` is where an operator gets certainty, and a run that assumed
capability says so in its trace.
"""

from dataclasses import dataclass, field
from typing import Protocol

from .contracts import Role
from .settings import Config, RoleConfig

_FATAL_IF_INCAPABLE = {Role.COMPARATOR, Role.SYNTHESIZER}


class ConfigError(ValueError):
    """The configuration cannot produce a legal pipeline. Surfaces as a 4xx, not a 500."""


class CapabilityIndex(Protocol):
    def supports_structured(self, slug: str) -> bool | None: ...
    def supports_web(self, slug: str) -> bool | None: ...
    def context_length(self, slug: str) -> int | None: ...


@dataclass(frozen=True)
class ResolvedRole:
    role: Role
    slug: str
    prompt_version: str
    temperature: float = 0.0
    require_structured: bool = False
    require_web: bool = False
    search_engine: str = "exa"
    # The rest of the capable chain, in order. Chains exist because a pinned slug will
    # rate-limit or go unroutable mid-run, so something has to actually walk them.
    fallbacks: tuple[str, ...] = ()
    enabled: bool = True
    on_panel: bool = False  # a referee that is also a panelist judges its own output
    notes: tuple[str, ...] = ()

    @property
    def stamped(self) -> bool:
        return self.on_panel or not self.enabled


@dataclass
class PanelCheck:
    models: list[str]
    warnings: list[str] = field(default_factory=list)


def family(slug: str) -> str:
    return slug.split("/", 1)[0] if "/" in slug else slug


def validate_panel(cfg: Config, models: list[str]) -> PanelCheck:
    """Membership and size are errors; correlation is a warning.

    A 2-1 majority drawn from one lineage is closer to one vote than two, and rung 3 of the
    ladder assumes independent voters. We cannot decorrelate the panel, so we surface it.
    """
    if not models:
        raise ConfigError("no models selected")
    if len(models) > cfg.caps.max_panel:
        raise ConfigError(f"panel of {len(models)} exceeds the cap of {cfg.caps.max_panel}")
    if cfg.panel_shortlist:
        unknown = [m for m in models if m not in cfg.panel_shortlist]
        if unknown:
            raise ConfigError(f"not in the curated panel list: {', '.join(unknown)}")

    warnings: list[str] = []
    families: dict[str, list[str]] = {}
    for slug in models:
        families.setdefault(family(slug), []).append(slug)
    for fam, slugs in families.items():
        if len(slugs) > 1:
            warnings.append(
                f"{len(slugs)} models share the {fam} family ({', '.join(slugs)}); "
                "their votes are correlated, so a majority among them is weaker than it looks"
            )
    if len(models) < cfg.caps.min_quorum:
        warnings.append(
            f"a panel of {len(models)} is below quorum; this will run in single-answer mode"
        )
    return PanelCheck(models=models, warnings=warnings)


class RoleRegistry:
    def __init__(self, cfg: Config, capabilities: CapabilityIndex | None = None) -> None:
        self.cfg = cfg
        self.capabilities = capabilities

    def _capable(self, slug: str, rc: RoleConfig) -> tuple[bool, str | None]:
        caps = self.capabilities
        if caps is None:
            return True, "capability not verified against the catalogue"
        if caps.supports_structured(slug) is None:
            # The catalogue was consulted and this slug is not in it. Slugs are retired
            # regularly, and a pin that no longer exists must fall through to the next
            # candidate rather than resolving "ok" and failing on first use.
            return False, f"{slug} is not in the catalogue"
        if rc.require_structured and caps.supports_structured(slug) is False:
            return False, f"{slug} cannot emit strict JSON schema"
        # Only native search constrains the model. Gateway retrieval works with anything.
        if rc.require_web and rc.search_engine == "native" and caps.supports_web(slug) is False:
            return False, f"{slug} has no native web search"
        return True, None

    def resolve(
        self,
        role: Role,
        *,
        panel: list[str],
        overrides: dict[Role, str] | None = None,
    ) -> ResolvedRole:
        rc = self.cfg.roles.get(role.value)
        if rc is None:
            raise ConfigError(f"no configuration for role {role.value}")

        notes: list[str] = []
        candidates = list(rc.chain)
        override = (overrides or {}).get(role)
        if override:
            if role.value not in self.cfg.allow_request_overrides:
                raise ConfigError(f"{role.value} is not caller-overridable")
            candidates = [override, *[c for c in rc.chain if c != override]]

        capable: list[str] = []
        for slug in candidates:
            ok, note = self._capable(slug, rc)
            if note and note not in notes:
                notes.append(note)
            if ok:
                capable.append(slug)

        if not capable:
            if role in _FATAL_IF_INCAPABLE:
                raise ConfigError(
                    f"{role.value}: no candidate in {candidates} meets its hard requirements; "
                    "this seat has no degraded path"
                )
            # The verifier is the important case: without grounding there is no external
            # arbiter, so rung 2 is removed rather than faked.
            return ResolvedRole(
                role=role,
                slug=candidates[0],
                prompt_version=rc.prompt_version,
                temperature=0.0,
                require_structured=rc.require_structured,
                require_web=rc.require_web,
                search_engine=rc.search_engine,
                enabled=False,
                notes=tuple(notes + [f"{role.value} disabled: no capable model configured"]),
            )

        off_panel = [s for s in capable if s not in panel]
        if off_panel:
            slug, on_panel = off_panel[0], False
            if off_panel[0] != capable[0]:
                notes.append(
                    f"{capable[0]} is on the panel; substituted {off_panel[0]} so the seat "
                    "does not judge its own output"
                )
        else:
            slug, on_panel = capable[0], rc.off_panel != "ignore"
            if on_panel:
                notes.append(
                    f"{slug} is refereeing as {role.value} while also on the panel — "
                    "self-preference is possible and confidence is reduced accordingly"
                )

        return ResolvedRole(
            role=role,
            slug=slug,
            fallbacks=tuple(c for c in capable if c != slug),
            prompt_version=rc.prompt_version,
            temperature=0.0,  # clamped: control flow must not sample
            require_structured=rc.require_structured,
            require_web=rc.require_web,
            search_engine=rc.search_engine,
            enabled=True,
            on_panel=on_panel,
            notes=tuple(notes),
        )

    def resolve_all(
        self, *, panel: list[str], overrides: dict[Role, str] | None = None
    ) -> dict[Role, ResolvedRole]:
        return {
            role: self.resolve(role, panel=panel, overrides=overrides)
            for role in (
                Role.COMPARATOR,
                Role.VERIFIER,
                Role.SYNTHESIZER,
                Role.NORMALIZER,
                Role.RED_TEAM,
            )
        }

    def gate_validated(self, comparator: ResolvedRole) -> bool:
        return self.cfg.is_verified(comparator.slug, comparator.prompt_version)
