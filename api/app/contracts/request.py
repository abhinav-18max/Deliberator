"""The request boundary."""

from pydantic import BaseModel, Field, field_validator

from .common import Mode, Role


class RoleOverride(BaseModel):
    role: Role
    slug: str

    @field_validator("role")
    @classmethod
    def _overridable(cls, v: Role) -> Role:
        # Enforced again against config at resolve time; this is the cheap first pass.
        if v in (Role.PANEL, Role.COMPARATOR):
            raise ValueError(f"{v} is not caller-overridable")
        return v


class DeliberateRequest(BaseModel):
    task: str = Field(min_length=1)
    context: str | None = None
    models: list[str] = Field(min_length=1)
    mode: Mode = Mode.FAST
    overrides: list[RoleOverride] = Field(default_factory=list)

    # Rung 5 needs a designated answer to fall back to. Defaults to the first
    # selected model so the ladder can never exit empty.
    default_model: str | None = None

    @field_validator("models")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate models selected")
        return v

    def floor_model(self) -> str:
        return self.default_model or self.models[0]
