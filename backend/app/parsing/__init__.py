"""
PDF parsing layer. PyMuPDF (fitz) extracts text blocks with bounding-box metadata
per page — required for citation containment checks. LlamaParse is the planned
fallback for scanned/multi-column PDFs. Output: list[ParsedBlock] consumed by chunking.

Implemented: Week 1.
"""
import hashlib
from dataclasses import dataclass

import pymupdf


@dataclass
class ParsedBlock:
    text: str
    page: int  # 0-indexed
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points


@dataclass
class ParseResult:
    blocks: list[ParsedBlock]
    page_count: int
    file_hash: str  # SHA-256 hex — used for dedup at upload time


def parse_pdf(file_bytes: bytes) -> ParseResult:
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    doc = pymupdf.Document(stream=file_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    blocks: list[ParsedBlock] = []

    for page_num, page in enumerate(doc):  # type: ignore[arg-type, var-annotated]
        for block in page.get_text("blocks"):
            x0, y0, x1, y1, text, _block_no, block_type = block
            # block_type 0 = text, 1 = image; skip non-text blocks
            if block_type == 0 and text.strip():
                blocks.append(
                    ParsedBlock(text=text.strip(), page=page_num, bbox=(x0, y0, x1, y1))
                )

    return ParseResult(blocks=blocks, page_count=len(doc), file_hash=file_hash)
