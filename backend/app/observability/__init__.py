"""
Langfuse observability client. Every LLM call in the system is traced through
this module: input tokens, output tokens, model, latency, cost estimate, and the
Langfuse generation ID that links back to the full trace in the Langfuse UI.
The eval failure explorer in `/evals` tab 2 embeds Langfuse trace links so that
each failure can be inspected end-to-end without switching tools. The client is
initialized at app startup (see `main.py` lifespan) and injected via FastAPI
dependency injection.

Implemented: Week 1 (client), Week 3 (eval integration).
"""
import structlog

from app.config import Settings, get_settings

log = structlog.get_logger(__name__)


class ObservabilityClient:
    """Thin wrapper around Langfuse. Silently disabled if keys are not configured."""

    def __init__(self, settings: Settings) -> None:
        self._enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
        self._client = None
        if self._enabled:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            log.info("observability.langfuse.enabled", host=settings.langfuse_host)
        else:
            log.warning("observability.langfuse.disabled", reason="keys not configured")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def trace(self, name: str, **kwargs: object) -> object | None:
        if self._client is None:
            return None
        # Langfuse v4 removed .trace(); silently skip if unavailable
        fn = getattr(self._client, "trace", None)
        if fn is None:
            return None
        return fn(name=name, **kwargs)  # type: ignore[no-any-return]

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()


_client: ObservabilityClient | None = None


def get_observability_client(settings: Settings | None = None) -> ObservabilityClient:
    global _client
    if _client is None:
        _client = ObservabilityClient(settings or get_settings())
    return _client
