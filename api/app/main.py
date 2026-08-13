"""FastAPI application.

Built through a factory so tests can inject a scripted provider and an in-memory store, which
is what keeps the whole suite offline. Nothing about the pipeline changes between that and
production — only the two ports.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_models, routes_runs
from .orchestrator import Orchestrator
from .providers.base import LLMPort
from .roles import CapabilityIndex, ConfigError
from .settings import Config, Settings, load_config, load_settings
from .store.base import StorePort
from .store.broadcast import Broadcast
from .store.memory import MemoryStore


def build_provider(settings: Settings, store: StorePort) -> LLMPort:
    from .providers.openrouter import OpenRouterProvider
    from .providers.replay import CachingProvider

    live = OpenRouterProvider(settings) if settings.openrouter_api_key else None
    if settings.replay:
        # Replay serves recorded fixtures only. A missing recording is an error rather than a
        # silent live call, so a demo cannot quietly start spending money.
        return CachingProvider(store, inner=None)
    if live is None:
        raise ConfigError(
            "OPENROUTER_API_KEY is not set. Copy api/.env.example to api/.env and add a key, "
            "or run `make demo` to replay the recorded traces without one."
        )
    return CachingProvider(store, inner=live)


def build_store(settings: Settings) -> StorePort:
    if not settings.has_mongo:
        # Runs are still fully traced, just not durably. The API says so at startup.
        return MemoryStore()
    from .store.mongo import MongoStore

    return MongoStore(settings.mongodb_uri, settings.mongodb_db)


def create_app(
    *,
    provider: LLMPort | None = None,
    store: StorePort | None = None,
    cfg: Config | None = None,
    settings: Settings | None = None,
    capabilities: CapabilityIndex | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    resolved_cfg = cfg or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app.state.store.ensure_ready()
        # Only consult the catalogue for a transport we built. An injected provider means the
        # caller owns its environment — a test with scripted slugs must not reach the network,
        # and its fake models must not be measured against a real catalogue.
        needs_catalogue = (
            provider is None
            and app.state.capabilities is None
            and bool(resolved_settings.openrouter_api_key)
        )
        if needs_catalogue:
            # Without the catalogue two invariants quietly stop running: referee capability
            # checks pass by default, and the guard's minimum-context check is a no-op — which
            # would let a context that fits one panelist and truncates another manufacture a
            # disagreement. Failure to fetch is survivable, but it must not be silent.
            from .providers import catalog

            try:
                app.state.capabilities = await catalog.fetch(
                    resolved_settings.openrouter_api_key
                )
            except Exception as exc:  # noqa: BLE001
                app.state.catalogue_error = str(exc)
        try:
            yield
        finally:
            closer = getattr(app.state.store, "close", None)
            if closer is not None:
                await closer()

    app = FastAPI(title="Delibrator", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = resolved_settings
    app.state.config = resolved_cfg
    app.state.store = store or build_store(resolved_settings)
    app.state.broadcast = Broadcast()
    app.state.capabilities = capabilities
    app.state.tasks = set()

    def build_orchestrator() -> Orchestrator:
        return Orchestrator(
            provider or build_provider(resolved_settings, app.state.store),
            app.state.config,
            capabilities=app.state.capabilities,
        )

    app.state.build_orchestrator = build_orchestrator

    app.include_router(routes_runs.router)
    app.include_router(routes_models.router)

    @app.get("/health")
    async def health() -> dict:
        return {
            "ok": True,
            "durable_store": getattr(app.state.store, "durable", False),
            "config_fingerprint": resolved_cfg.fingerprint(),
            # False means the capability and context-window invariants are running on
            # assumption rather than data for this process.
            "catalogue_loaded": app.state.capabilities is not None,
            "catalogue_error": getattr(app.state, "catalogue_error", None),
        }

    return app


app = create_app()
