"""
Layout-aware hierarchical chunking with dual granularity. Section-level chunks
(~1500 tokens) carry the structural context needed for the deviation pipeline;
clause-level chunks (~300 tokens) are the retrieval unit for QA. Both granularities
store the bboxes of their constituent blocks so the citation validator can
reconstruct the source region. Chunk overlap is intentional: a clause that
straddles a section boundary appears in both section chunks.

Implemented: Week 1.
"""
