"""Configuration: `config.yaml` for the operator surface, environment for secrets.

The split matters. Callers pick the panel; the operator owns every referee seat, because
control flow must never depend on the reliability of a model someone else chose.
"""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

API_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = API_DIR / "config.yaml"


class Caps(BaseModel):
    max_panel: int = 5
    min_quorum: int = 2
    max_rounds: int = 2
    max_verified_disputes: int = 3
    search_max_results: int = 5
    per_call_timeout_s: float = 90.0
    panel_call_timeout_s: float = 60.0


class RoleConfig(BaseModel):
    chain: list[str] = Field(min_length=1)
    prompt_version: str
    require_structured: bool = False
    require_web: bool = False
    off_panel: Literal["require", "prefer", "ignore"] = "prefer"
    temperature: float = 0.0

    # Where retrieval happens. "exa" has OpenRouter run the search and inject results, which
    # works with any model; "native" drives the model's own search and therefore restricts the
    # chain to models advertising it. Citations arrive in the same normalised shape either way.
    search_engine: Literal["exa", "native"] = "exa"


class PanelPrompts(BaseModel):
    """Prompt versions for the re-entrant panel seats.

    These were literals in Python, which meant three of the system's nine prompts could be
    swapped without touching configuration and without `doctor` ever checking they existed.
    """

    answer: str = "panel_v1"
    debate_round_1: str = "debate_r1_v1"
    debate_round_2: str = "debate_r2_v1"

    def all(self) -> list[str]:
        return [self.answer, self.debate_round_1, self.debate_round_2]


class VerifiedConfig(BaseModel):
    slug: str
    prompt_version: str
    material_recall: float = 0.0


class Config(BaseModel):
    caps: Caps = Field(default_factory=Caps)
    panel_shortlist: list[str] = Field(default_factory=list)
    panel_default: list[str] = Field(default_factory=list)
    roles: dict[str, RoleConfig]
    panel_prompts: PanelPrompts = Field(default_factory=PanelPrompts)
    allow_request_overrides: list[str] = Field(default_factory=list)
    verified_configs: list[VerifiedConfig] = Field(default_factory=list)

    def fingerprint(self) -> str:
        """Identifies the referee cast + caps a run executed under, so a trace can never be
        misread as having been produced by a different configuration."""
        material = {
            "roles": {k: v.model_dump() for k, v in sorted(self.roles.items())},
            "panel_prompts": self.panel_prompts.model_dump(),
            "caps": self.caps.model_dump(),
        }
        blob = json.dumps(material, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def is_verified(self, slug: str, prompt_version: str) -> bool:
        return any(
            v.slug == slug and v.prompt_version == prompt_version for v in self.verified_configs
        )


class Settings(BaseModel):
    openrouter_api_key: str = ""
    openrouter_app_url: str = "http://localhost:3000"
    openrouter_app_title: str = "Delibrator"
    mongodb_uri: str = ""
    mongodb_db: str = "delibrator"
    replay: bool = False

    @property
    def has_mongo(self) -> bool:
        return bool(self.mongodb_uri)


def load_config(path: Path | None = None) -> Config:
    raw = yaml.safe_load((path or CONFIG_PATH).read_text())
    return Config.model_validate(raw)


def _load_dotenv() -> None:
    env_file = API_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Quoting a value in .env is normal and must not become part of it: a quoted
        # connection string otherwise fails with "invalid URI scheme" and looks like a
        # credentials problem rather than a parsing one.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def load_settings() -> Settings:
    _load_dotenv()
    return Settings(
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        openrouter_app_url=os.environ.get("OPENROUTER_APP_URL", "http://localhost:3000"),
        openrouter_app_title=os.environ.get("OPENROUTER_APP_TITLE", "Delibrator"),
        mongodb_uri=os.environ.get("MONGODB_URI", ""),
        mongodb_db=os.environ.get("MONGODB_DB", "delibrator"),
        replay=os.environ.get("DELIBRATOR_REPLAY", "0") not in ("0", "", "false", "False"),
    )


@lru_cache(maxsize=1)
def config() -> Config:
    return load_config()


@lru_cache(maxsize=1)
def settings() -> Settings:
    return load_settings()
