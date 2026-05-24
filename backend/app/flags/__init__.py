"""
Automated risk flag detection. Four flag types with severity levels:
  1. Auto-renewal clause (Medium) — contract renews without affirmative consent
  2. Uncapped liability (High) — no ceiling on damages owed by one party
  3. Asymmetric termination rights (Medium) — one party can exit on shorter notice
  4. Assignment without consent (High) — contract can be assigned to a third party
     without the other party's approval

Flags are deterministic (regex + extraction output), not LLM-judged, so they are
cheap to run and appear in the Trust Panel. Severity thresholds are configurable
via playbook YAML overrides.

Implemented: Week 2.
"""
import enum
import re
from dataclasses import dataclass

from app.db.models import Chunk
from app.extraction import ExtractionResult


class Severity(enum.StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RiskFlag:
    flag_type: str
    severity: Severity
    triggered: bool
    evidence_text: str | None
    explanation: str


# ---------------------------------------------------------------------------
# Regex patterns — compiled once at import time
# ---------------------------------------------------------------------------

_AUTO_RENEWAL_RE = re.compile(
    r"(?:"
    r"automatically\s+renew"
    r"|auto.?renew"
    r"|(?:shall|will|must)\s+renew"
    r"|evergreen\s+(?:clause|provision|term)"
    r"|successive\s+(?:one.year|annual|monthly|term)\s+terms?"
    r"|unless\s+(?:either\s+party\s+)?(?:provides?|gives?|delivers?)\s+(?:written\s+)?notice\s+of\s+(?:non.?renewal|termination)"
    r")",
    re.IGNORECASE,
)

_UNCAPPED_LIABILITY_RE = re.compile(
    r"(?:"
    r"unlimited\s+liability"
    r"|no\s+(?:limitation|cap|ceiling)\s+on\s+(?:liability|damages?)"
    r"|without\s+any\s+(?:limitation|cap)\s+on\s+(?:liability|damages?)"
    r"|liability\s+(?:shall|is|will\s+be)\s+unlimited"
    r")",
    re.IGNORECASE,
)

# Asymmetric termination: one party has unilateral exit rights — look for
# "Company may terminate" / "Provider may terminate" without "either party".
_SYMMETRIC_TERMINATION_RE = re.compile(
    r"either\s+party\s+may\s+(?:terminate|cancel)",
    re.IGNORECASE,
)
_UNILATERAL_TERMINATION_RE = re.compile(
    r"(?:company|provider|vendor|licensor|supplier|client|customer|we|us)\s+"
    r"(?:may|can|shall\s+have\s+the\s+right\s+to)\s+terminate",
    re.IGNORECASE,
)

_ASSIGNMENT_WITHOUT_CONSENT_RE = re.compile(
    r"(?:"
    r"may\s+assign\s+this\s+(?:agreement|contract)"
    r"|assignment\s+(?:is\s+)?permitted\s+without\s+(?:the\s+)?(?:other\s+party.s\s+)?consent"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_match(pattern: re.Pattern[str], chunks: list[Chunk]) -> str | None:
    """Return the first matching text excerpt across all chunks, or None."""
    for chunk in chunks:
        m = pattern.search(chunk.content)
        if m:
            start = max(0, m.start() - 80)
            end = min(len(chunk.content), m.end() + 80)
            return f"…{chunk.content[start:end]}…"
    return None


def _extraction_by_category(extractions: list[ExtractionResult]) -> dict[str, ExtractionResult]:
    return {r.category: r for r in extractions}


# ---------------------------------------------------------------------------
# Individual flag detectors
# ---------------------------------------------------------------------------


def _flag_auto_renewal(chunks: list[Chunk], by_cat: dict[str, ExtractionResult]) -> RiskFlag:
    renewal = by_cat.get("Renewal Term")
    if renewal and renewal.present:
        evidence = renewal.clause_text or _first_match(_AUTO_RENEWAL_RE, chunks)
        return RiskFlag(
            flag_type="auto_renewal",
            severity=Severity.MEDIUM,
            triggered=True,
            evidence_text=evidence,
            explanation="Contract contains a renewal term that may renew automatically without affirmative consent.",
        )

    evidence = _first_match(_AUTO_RENEWAL_RE, chunks)
    if evidence:
        return RiskFlag(
            flag_type="auto_renewal",
            severity=Severity.MEDIUM,
            triggered=True,
            evidence_text=evidence,
            explanation="Auto-renewal language detected in contract text.",
        )

    return RiskFlag(
        flag_type="auto_renewal",
        severity=Severity.MEDIUM,
        triggered=False,
        evidence_text=None,
        explanation="No auto-renewal clause detected.",
    )


def _flag_uncapped_liability(chunks: list[Chunk], by_cat: dict[str, ExtractionResult]) -> RiskFlag:
    uncapped = by_cat.get("Uncapped Liability")
    if uncapped and uncapped.present:
        return RiskFlag(
            flag_type="uncapped_liability",
            severity=Severity.HIGH,
            triggered=True,
            evidence_text=uncapped.clause_text or _first_match(_UNCAPPED_LIABILITY_RE, chunks),
            explanation="Contract contains an explicitly uncapped liability provision.",
        )

    cap = by_cat.get("Cap on Liability")
    if cap and not cap.present:
        evidence = _first_match(_UNCAPPED_LIABILITY_RE, chunks)
        return RiskFlag(
            flag_type="uncapped_liability",
            severity=Severity.HIGH,
            triggered=True,
            evidence_text=evidence,
            explanation="No liability cap found. Without an explicit cap, damages may be unlimited.",
        )

    evidence = _first_match(_UNCAPPED_LIABILITY_RE, chunks)
    if evidence:
        return RiskFlag(
            flag_type="uncapped_liability",
            severity=Severity.HIGH,
            triggered=True,
            evidence_text=evidence,
            explanation="Language suggesting unlimited liability detected in contract text.",
        )

    return RiskFlag(
        flag_type="uncapped_liability",
        severity=Severity.HIGH,
        triggered=False,
        evidence_text=None,
        explanation="No uncapped liability provision detected.",
    )


def _flag_asymmetric_termination(
    chunks: list[Chunk], by_cat: dict[str, ExtractionResult]
) -> RiskFlag:
    termination = by_cat.get("Termination for Convenience")

    # If extraction found a termination clause, check its text for symmetry.
    if termination and termination.present and termination.clause_text:
        clause = termination.clause_text
        if _SYMMETRIC_TERMINATION_RE.search(clause):
            return RiskFlag(
                flag_type="asymmetric_termination",
                severity=Severity.MEDIUM,
                triggered=False,
                evidence_text=None,
                explanation="Termination for convenience is mutual (either party).",
            )
        # Clause exists but doesn't say "either party" — likely one-sided.
        return RiskFlag(
            flag_type="asymmetric_termination",
            severity=Severity.MEDIUM,
            triggered=True,
            evidence_text=clause[:300] if len(clause) > 300 else clause,
            explanation="Termination for convenience clause may grant rights to only one party.",
        )

    # Fall back to regex over all chunks.
    has_symmetric = any(
        _SYMMETRIC_TERMINATION_RE.search(c.content) for c in chunks
    )
    if has_symmetric:
        return RiskFlag(
            flag_type="asymmetric_termination",
            severity=Severity.MEDIUM,
            triggered=False,
            evidence_text=None,
            explanation="Mutual termination rights detected.",
        )

    unilateral_evidence = _first_match(_UNILATERAL_TERMINATION_RE, chunks)
    if unilateral_evidence:
        return RiskFlag(
            flag_type="asymmetric_termination",
            severity=Severity.MEDIUM,
            triggered=True,
            evidence_text=unilateral_evidence,
            explanation="Unilateral termination right detected without a corresponding mutual right.",
        )

    return RiskFlag(
        flag_type="asymmetric_termination",
        severity=Severity.MEDIUM,
        triggered=False,
        evidence_text=None,
        explanation="No asymmetric termination rights detected.",
    )


def _flag_assignment_without_consent(
    chunks: list[Chunk], by_cat: dict[str, ExtractionResult]
) -> RiskFlag:
    anti_assign = by_cat.get("Anti-Assignment")

    if anti_assign and anti_assign.present:
        return RiskFlag(
            flag_type="assignment_without_consent",
            severity=Severity.HIGH,
            triggered=False,
            evidence_text=anti_assign.clause_text,
            explanation="Anti-assignment clause present; assignment requires consent.",
        )

    # Check for explicit permissive assignment language.
    permissive_evidence = _first_match(_ASSIGNMENT_WITHOUT_CONSENT_RE, chunks)
    if permissive_evidence:
        return RiskFlag(
            flag_type="assignment_without_consent",
            severity=Severity.HIGH,
            triggered=True,
            evidence_text=permissive_evidence,
            explanation="Contract explicitly permits assignment without the other party's consent.",
        )

    # No anti-assignment clause and no permissive language — assignment likely unrestricted.
    return RiskFlag(
        flag_type="assignment_without_consent",
        severity=Severity.HIGH,
        triggered=True,
        evidence_text=None,
        explanation=(
            "No anti-assignment clause found. Without an explicit restriction, "
            "either party may assign the contract to a third party."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_flags(
    chunks: list[Chunk],
    extractions: list[ExtractionResult],
) -> list[RiskFlag]:
    """Run all four risk flag detectors and return a result for each.

    Detectors are deterministic: they combine regex matching on chunk content
    with the structured extraction results. No LLM calls are made here.

    Args:
        chunks: All chunks for the contract (any type; both section and clause are scanned).
        extractions: Output of extraction.extract() for the same contract.
    """
    by_cat = _extraction_by_category(extractions)
    return [
        _flag_auto_renewal(chunks, by_cat),
        _flag_uncapped_liability(chunks, by_cat),
        _flag_asymmetric_termination(chunks, by_cat),
        _flag_assignment_without_consent(chunks, by_cat),
    ]
