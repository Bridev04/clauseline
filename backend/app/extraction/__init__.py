"""
Structured extraction of the 12 CUAD categories chosen via Spike 3. Each category
(e.g., governing law, limitation of liability, auto-renewal, assignment) is extracted
as a typed `ExtractionResult` with the clause text, page reference, and a confidence
signal. Uses Haiku for the initial extraction pass and Sonnet for low-confidence
re-checks. The final 12-category list is the output of Spike 3 — do not expand
or contract the list without updating the golden eval set.

Implemented: Week 2.
"""
import json
import re
from dataclasses import dataclass

import structlog

from app.db.models import Chunk, ChunkType
from app.llm import LLMClient, Tier, get_llm_client

log = structlog.get_logger(__name__)

# Do not modify this list without updating the golden eval set (Spike 3).
CUAD_CATEGORIES: list[tuple[str, str]] = [
    ("Governing Law", "Which jurisdiction's laws govern this contract"),
    ("Renewal Term", "Whether the contract automatically renews and the renewal period length"),
    ("Notice Period to Terminate Renewal", "Required advance notice to prevent automatic renewal"),
    ("Termination for Convenience", "Either party's right to terminate without cause"),
    ("Indemnification", "Obligations to compensate the other party for losses or damages"),
    ("Confidentiality", "Obligations to keep information secret and not disclose it"),
    ("Anti-Assignment", "Restrictions on transferring contract rights or obligations to third parties"),
    ("Non-Compete", "Restrictions on engaging in competitive activities"),
    ("Cap on Liability", "Maximum damages or compensation one party owes the other"),
    ("Change of Control", "Provisions triggered if ownership of a party changes"),
    ("IP Ownership Assignment", "Which party owns intellectual property created under the contract"),
    ("Uncapped Liability", "Any liability explicitly stated to be unlimited or not subject to a cap"),
]

_CONFIDENCE_THRESHOLD = 0.7
_MAX_CONTRACT_CHARS = 120_000  # ~30k tokens — fits Haiku comfortably

_SYSTEM_PROMPT = """\
You are a contract analysis assistant specializing in legal clause extraction.
Extract the specified clause categories from the provided contract text.
Return a JSON object only — no markdown fences, no explanation text.

Confidence scoring guide:
- 0.9-1.0: clause is explicitly present with clear language
- 0.7-0.9: clause is present but may be implied or spread across sections
- 0.5-0.7: uncertain; clause may be partially present or ambiguous
- 0.0-0.5: clause is absent or you cannot find relevant language
"""

_EXTRACTION_SCHEMA = """\
{
  "extractions": [
    {
      "category": "<exact category name from the list>",
      "present": <true or false>,
      "clause_text": "<verbatim excerpt from the contract, or null if absent>",
      "page": <integer page number if identifiable, or null>,
      "confidence": <float 0.0 to 1.0>
    }
  ]
}"""


@dataclass
class ExtractionResult:
    category: str
    present: bool
    clause_text: str | None
    page: int | None
    confidence: float

    def dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "present": self.present,
            "clause_text": self.clause_text,
            "page": self.page,
            "confidence": self.confidence,
        }


def _build_contract_text(chunks: list[Chunk]) -> str:
    """Concatenate section chunks with page markers, truncated to fit context."""
    parts: list[str] = []
    total = 0
    for chunk in sorted(chunks, key=lambda c: c.page):
        header = f"\n\n--- Page {chunk.page} ---\n"
        body = chunk.content
        if total + len(header) + len(body) > _MAX_CONTRACT_CHARS:
            remaining = _MAX_CONTRACT_CHARS - total - len(header) - 50
            if remaining > 0:
                parts.append(header + body[:remaining] + "\n[truncated]")
            break
        parts.append(header + body)
        total += len(header) + len(body)
    return "".join(parts)


def _build_category_list(categories: list[tuple[str, str]]) -> str:
    return "\n".join(f"{i + 1}. {name} — {desc}" for i, (name, desc) in enumerate(categories))


def _build_prompt(contract_text: str, categories: list[tuple[str, str]]) -> str:
    return (
        f"Analyze the following contract and extract each listed category.\n\n"
        f"CONTRACT TEXT:\n{contract_text}\n\n"
        f"CATEGORIES TO EXTRACT:\n{_build_category_list(categories)}\n\n"
        f"Return a JSON object matching this schema exactly, "
        f"with one entry per category in the same order:\n{_EXTRACTION_SCHEMA}"
    )


def _parse_extraction_response(text: str) -> list[dict[str, object]]:
    """Parse the JSON extraction response, with fallbacks for markdown fences."""
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            data = json.loads(match.group(1))
        else:
            match = re.search(r"\{[\s\S]+\}", text)
            if not match:
                raise ValueError(f"No JSON found in LLM response: {text[:300]}") from None
            data = json.loads(match.group())

    extractions = data.get("extractions")
    if not isinstance(extractions, list):
        raise ValueError(f"Expected 'extractions' list, got: {type(extractions)}")
    return extractions  # list[Any] narrowed by caller


def _map_extractions(
    raw: list[dict[str, object]],
    categories: list[tuple[str, str]],
) -> list[ExtractionResult]:
    category_names = {name for name, _ in categories}
    results: list[ExtractionResult] = []
    for item in raw:
        cat = str(item.get("category", ""))
        if cat not in category_names:
            continue
        raw_page = item.get("page")
        raw_clause = item.get("clause_text")
        results.append(
            ExtractionResult(
                category=cat,
                present=bool(item.get("present", False)),
                clause_text=str(raw_clause) if raw_clause is not None else None,
                page=int(str(raw_page)) if raw_page is not None else None,
                confidence=float(str(item.get("confidence", 0.0))),
            )
        )
    return results


async def extract(
    chunks: list[Chunk],
    *,
    llm_client: LLMClient | None = None,
    confidence_threshold: float = _CONFIDENCE_THRESHOLD,
) -> list[ExtractionResult]:
    """Extract the 12 CUAD categories from section chunks.

    Haiku handles the initial pass. Any category with confidence below
    `confidence_threshold` is re-checked with Sonnet on the same text.

    Args:
        chunks: Section-type chunks for the contract (ChunkType.section).
                Clause chunks are silently filtered out.
        llm_client: Injected for testing; defaults to the global singleton.
        confidence_threshold: Categories below this confidence trigger a Sonnet re-check.
    """
    client = llm_client or get_llm_client()

    section_chunks = [c for c in chunks if c.chunk_type == ChunkType.section]
    if not section_chunks:
        log.warning("extraction.no_section_chunks", total_chunks=len(chunks))
        return [
            ExtractionResult(category=name, present=False, clause_text=None, page=None, confidence=0.0)
            for name, _ in CUAD_CATEGORIES
        ]

    contract_text = _build_contract_text(section_chunks)
    prompt = _build_prompt(contract_text, CUAD_CATEGORIES)

    log.info("extraction.haiku_pass", section_chunks=len(section_chunks), text_len=len(contract_text))
    haiku_response = await client.complete(prompt, Tier.HAIKU, system=_SYSTEM_PROMPT, max_tokens=4096)
    results = _map_extractions(_parse_extraction_response(haiku_response), CUAD_CATEGORIES)

    # Sonnet re-check for low-confidence categories
    low_confidence = [(name, desc) for name, desc in CUAD_CATEGORIES
                      if any(r.category == name and r.confidence < confidence_threshold for r in results)]

    if low_confidence:
        log.info("extraction.sonnet_recheck", categories=[n for n, _ in low_confidence])
        recheck_prompt = _build_prompt(contract_text, low_confidence)
        sonnet_response = await client.complete(
            recheck_prompt, Tier.SONNET, system=_SYSTEM_PROMPT, max_tokens=2048
        )
        recheck_results = _map_extractions(_parse_extraction_response(sonnet_response), low_confidence)
        recheck_by_category = {r.category: r for r in recheck_results}

        # Replace low-confidence results with Sonnet's answers
        results = [
            recheck_by_category.get(r.category, r)
            for r in results
        ]

    log.info(
        "extraction.done",
        total=len(results),
        present=sum(1 for r in results if r.present),
        rechecked=len(low_confidence),
    )
    return results
