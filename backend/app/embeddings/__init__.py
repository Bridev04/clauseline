"""
Voyage AI embedding client wrapper. Default model is `voyage-3-large`; the
legal-domain fine-tuned `voyage-law-2` is available as an alt via the VOYAGE_MODEL
env var. Exposes a single async `embed(texts)` function that handles batching
and rate-limit retries (via tenacity). Embeddings are 1024-dimensional floats
stored in pgvector's `vector` column type.

Implemented: Week 1.
"""
import structlog
import voyageai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings

log = structlog.get_logger(__name__)

_BATCH_SIZE = 128


class EmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self._client = voyageai.AsyncClient(api_key=settings.voyage_api_key)  # type: ignore[attr-defined]
        self._model = settings.voyage_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        result = await self._client.embed(texts, model=self._model, input_type="document")
        return result.embeddings  # type: ignore[return-value]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            log.debug("embeddings.batch", start=i, size=len(batch), model=self._model)
            all_embeddings.extend(await self._embed_batch(batch))
        return all_embeddings


_client: EmbeddingClient | None = None


def get_embedding_client(settings: Settings | None = None) -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient(settings or get_settings())
    return _client
