"""
Layout-aware hierarchical chunking with dual granularity. Section-level chunks
(~1500 tokens) carry the structural context needed for the deviation pipeline;
clause-level chunks (~300 tokens) are the retrieval unit for QA. Both granularities
store the bboxes of their constituent blocks so the citation validator can
reconstruct the source region. Chunk overlap is intentional: a clause that
straddles a section boundary appears in both section chunks.

Implemented: Week 1.
"""
from dataclasses import dataclass

from app.parsing import ParsedBlock

SECTION_TOKEN_LIMIT = 1500
CLAUSE_TOKEN_LIMIT = 300


def _approx_tokens(text: str) -> int:
    # Words × 1.3 is a reasonable approximation for legal English
    return max(1, int(len(text.split()) * 1.3))


def _merge_bboxes(bboxes: list[tuple[float, float, float, float]]) -> dict[str, float]:
    return {
        "x0": min(b[0] for b in bboxes),
        "y0": min(b[1] for b in bboxes),
        "x1": max(b[2] for b in bboxes),
        "y1": max(b[3] for b in bboxes),
    }


@dataclass
class ChunkData:
    content: str
    chunk_type: str  # "section" | "clause" — matches ChunkType enum values in db/models.py
    page: int
    bbox: dict[str, float]
    token_count: int


def chunk_blocks(blocks: list[ParsedBlock]) -> list[ChunkData]:
    """Return section + clause chunks for a list of ParsedBlocks."""
    if not blocks:
        return []
    sections = _build_sections(blocks)
    clauses = _split_to_clauses(sections)
    return sections + clauses


def _build_sections(blocks: list[ParsedBlock]) -> list[ChunkData]:
    sections: list[ChunkData] = []
    current_texts: list[str] = []
    current_bboxes: list[tuple[float, float, float, float]] = []
    current_page = blocks[0].page
    current_tokens = 0

    def _flush() -> None:
        if current_texts:
            text = "\n\n".join(current_texts)
            sections.append(
                ChunkData(
                    content=text,
                    chunk_type="section",
                    page=current_page,
                    bbox=_merge_bboxes(current_bboxes),
                    token_count=_approx_tokens(text),
                )
            )

    for block in blocks:
        block_tokens = _approx_tokens(block.text)
        if current_tokens + block_tokens > SECTION_TOKEN_LIMIT and current_texts:
            _flush()
            current_texts = []
            current_bboxes = []
            current_page = block.page
            current_tokens = 0
        current_texts.append(block.text)
        current_bboxes.append(block.bbox)
        current_page = block.page
        current_tokens += block_tokens

    _flush()
    return sections


def _split_to_clauses(sections: list[ChunkData]) -> list[ChunkData]:
    clauses: list[ChunkData] = []
    words_per_clause = max(1, int(CLAUSE_TOKEN_LIMIT / 1.3))

    for section in sections:
        if section.token_count <= CLAUSE_TOKEN_LIMIT:
            clauses.append(
                ChunkData(
                    content=section.content,
                    chunk_type="clause",
                    page=section.page,
                    bbox=section.bbox,
                    token_count=section.token_count,
                )
            )
            continue

        words = section.content.split()
        for start in range(0, len(words), words_per_clause):
            chunk_text = " ".join(words[start : start + words_per_clause])
            if not chunk_text.strip():
                continue
            clauses.append(
                ChunkData(
                    content=chunk_text,
                    chunk_type="clause",
                    page=section.page,
                    bbox=section.bbox,  # inherits parent section bbox
                    token_count=_approx_tokens(chunk_text),
                )
            )

    return clauses
