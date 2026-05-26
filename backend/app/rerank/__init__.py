"""
Cohere rerank-3 wrapper. Takes the fused RRF candidate list (~40 chunks) and
returns the top-K (default 8) reranked by semantic relevance to the query.
Reranking is the last filtering stage before the LLM sees context — it directly
affects faithfulness. A local cross-encoder was considered but rejected in favor
of the Cohere API (see docs/decision-log.md: "Cohere rerank vs local cross-encoder").

Implemented: Week 2.
"""
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings
from app.db.models import Chunk
from app.retrieval import RetrievalResult

log = structlog.get_logger(__name__)


class RerankClient:
    def __init__(self, settings: Settings) -> None:
        import cohere  # imported here so the module loads without the key present

        self._client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)
        self._model = settings.cohere_rerank_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        *,
        top_k: int,
    ) -> list[Chunk]:
        """Rerank candidates by semantic relevance and return the top-k chunks.

        Documents are passed as plain strings (chunk content). The returned list
        is ordered by Cohere relevance score descending. Falls back to RRF order
        if the rerank model is unavailable on the current API key.
        """
        if not candidates:
            return []

        import cohere as _cohere

        documents = [r.chunk.content for r in candidates]

        try:
            response = await self._client.rerank(
                model=self._model,
                query=query,
                documents=documents,
                top_n=min(top_k, len(candidates)),
            )
        except _cohere.errors.not_found_error.NotFoundError:
            log.warning(
                "rerank.model_unavailable",
                model=self._model,
                fallback="rrf_order",
            )
            return [r.chunk for r in candidates[:top_k]]

        reranked: list[Chunk] = []
        for result in response.results:
            chunk = candidates[result.index].chunk
            reranked.append(chunk)
            log.debug(
                "rerank.result",
                chunk_id=chunk.id,
                relevance_score=result.relevance_score,
                original_rank=result.index,
            )

        log.info(
            "rerank.done",
            query_len=len(query),
            input_candidates=len(candidates),
            output_chunks=len(reranked),
        )
        return reranked


_client: RerankClient | None = None


def get_rerank_client(settings: Settings | None = None) -> RerankClient:
    global _client
    if _client is None:
        _client = RerankClient(settings or get_settings())
    return _client
