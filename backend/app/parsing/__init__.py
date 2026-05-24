"""
PDF parsing layer. PyMuPDF4LLM is the primary parser: it returns markdown text
plus bounding-box metadata for every block, which is non-negotiable for the
citation IoU metric. LlamaParse is the fallback for scanned PDFs or complex
multi-column layouts where PyMuPDF struggles. Output contract: a list of
`ParsedBlock(text, page, bbox)` consumed by the chunking layer.

Implemented: Week 1.
"""
