"""
LangGraph deviation detection pipeline. Five nodes executed as a directed graph:

  Loader       — fetches contract chunks and playbook rules from Postgres
  Classifier   — parallel fan-out per CUAD category (Haiku); labels each clause
                 as Conforming / Deviating / Unclear
  Comparator   — parallel fan-out per deviating/unclear rule (Sonnet); produces
                 a structured comparison with evidence text and deviation type
  Scorer       — deterministic aggregation of per-rule scores into an overall
                 deviation severity (High / Medium / Low / None)
  Summarizer   — Sonnet drafts a plain-language deviation report for the reviewer

A HITL interrupt fires after Summarizer; the reviewer approves, rejects, or edits
before the result is committed. State uses `Annotated[list, add]` reducers on the
fan-in edges so parallel node outputs merge cleanly.

Implemented: Week 5 (pipeline), Week 6 (HITL + UI).
"""
from __future__ import annotations

import asyncio
import json
import operator
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import structlog
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from app.config import get_settings
from app.db.models import Chunk, Contract
from app.extraction import ExtractionResult, extract
from app.llm import Tier, get_llm_client
from app.playbooks import (
    Condition,
    CUADCategory,
    Playbook,
    PlaybookRule,
    load_all_playbooks,
)

log = structlog.get_logger(__name__)

MAX_RULES = 50

# Normalization: CUADCategory enum value → extraction display name
_CATEGORY_TO_DISPLAY: dict[str, str] = {
    CUADCategory.governing_law: "Governing Law",
    CUADCategory.renewal_term: "Renewal Term",
    CUADCategory.notice_period_to_terminate_renewal: "Notice Period to Terminate Renewal",
    CUADCategory.termination_for_convenience: "Termination for Convenience",
    CUADCategory.indemnification: "Indemnification",
    CUADCategory.confidentiality: "Confidentiality",
    CUADCategory.anti_assignment: "Anti-Assignment",
    CUADCategory.non_compete: "Non-Compete",
    CUADCategory.cap_on_liability: "Cap on Liability",
    CUADCategory.change_of_control: "Change of Control",
    CUADCategory.ip_ownership_assignment: "IP Ownership Assignment",
    CUADCategory.uncapped_liability: "Uncapped Liability",
}

# Severity precedence — lower index wins in aggregation
_SEVERITY_ORDER: list[str] = ["critical", "high", "medium", "low", "info", "none"]


class DeviationRunError(RuntimeError):
    """Pipeline cannot proceed (missing contract/playbook, rule cap exceeded)."""
    pass


# ---------------------------------------------------------------------------
# State dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RuleClassification:
    rule_category: str          # CUADCategory enum value
    rule_condition: str
    rule_required_value: str | None
    rule_severity: str
    label: Literal["Conforming", "Deviating", "Unclear"]
    reasoning: str


@dataclass
class RuleComparison:
    rule_category: str
    rule_condition: str
    rule_required_value: str | None
    rule_severity: str
    label: Literal["Deviating", "Unclear"]
    evidence_text: str
    deviation_type: str


@dataclass
class OverallScore:
    overall_severity: str       # critical | high | medium | low | none
    per_rule: list[dict[str, str]] = field(default_factory=list)


@dataclass
class DeviationReport:
    contract_id: str
    playbook_id: str
    classifications: list[RuleClassification]
    comparisons: list[RuleComparison]
    score: OverallScore
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# LangGraph state schema
# ---------------------------------------------------------------------------

class _BaseState(TypedDict):
    contract_id: str
    playbook_id: str


class DeviationState(_BaseState, total=False):
    playbook: Playbook
    extraction_by_category: dict[str, ExtractionResult]
    classifications: Annotated[list[RuleClassification], operator.add]
    comparisons: Annotated[list[RuleComparison], operator.add]
    score: OverallScore
    summary: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _condition_description(rule: PlaybookRule) -> str:
    val = rule.required_value
    match rule.condition:
        case Condition.eq:
            return f"must equal '{val}'"
        case Condition.contains:
            return f"must contain '{val}'"
        case Condition.gte:
            return f"must be >= {val}"
        case Condition.lte:
            return f"must be <= {val}"
        case Condition.absent:
            return "must NOT be present"
        case Condition.present:
            return "must be present"
        case _:
            return f"{rule.condition.value}"


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract a JSON object from an LLM response, handling markdown fences."""
    text = text.strip()
    result: dict[str, Any]
    try:
        result = json.loads(text)
        return result
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        result = json.loads(m.group(1))
        return result
    m = re.search(r"\{[\s\S]+\}", text)
    if not m:
        raise ValueError(f"No JSON object in LLM response: {text[:300]}")
    result = json.loads(m.group())
    return result


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def _loader_node(state: DeviationState, session: AsyncSession) -> dict[str, Any]:
    contract_id = state["contract_id"]
    playbook_id = state["playbook_id"]
    log.info("deviation.loader.start", contract_id=contract_id, playbook_id=playbook_id)

    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise DeviationRunError(f"Contract not found: {contract_id}")

    settings = get_settings()
    playbooks = load_all_playbooks(Path(settings.playbooks_dir))
    playbook = playbooks.get(playbook_id)
    if playbook is None:
        raise DeviationRunError(f"Playbook not found: {playbook_id}")

    if len(playbook.rules) > MAX_RULES:
        raise DeviationRunError(
            f"Playbook '{playbook_id}' has {len(playbook.rules)} rules "
            f"(limit: {MAX_RULES})"
        )

    result = await session.execute(select(Chunk).where(Chunk.contract_id == contract_id))
    chunks = list(result.scalars().all())
    log.info("deviation.loader.chunks_loaded", count=len(chunks))

    extraction_results = await extract(chunks)
    extraction_by_category = {r.category: r for r in extraction_results}

    log.info(
        "deviation.loader.done",
        playbook_rules=len(playbook.rules),
        extracted_categories=len(extraction_by_category),
    )
    return {"playbook": playbook, "extraction_by_category": extraction_by_category}


async def _classify_single_rule(
    rule: PlaybookRule,
    extraction_by_category: dict[str, ExtractionResult],
) -> RuleClassification:
    display_name = _CATEGORY_TO_DISPLAY.get(rule.category, rule.category)
    ext = extraction_by_category.get(display_name)
    clause_text = ext.clause_text if ext and ext.present and ext.clause_text else None

    system = (
        "You are a contract compliance analyst. "
        "Classify whether the contract clause conforms to the playbook requirement. "
        "Return JSON only — no markdown fences, no explanation outside the JSON."
    )
    prompt = (
        f"Playbook requirement:\n"
        f"  Category: {display_name}\n"
        f"  Condition: {_condition_description(rule)}\n"
        f"  Description: {rule.description or '(none)'}\n\n"
        f"Contract clause text:\n"
        f"{clause_text if clause_text else '(not found in contract)'}\n\n"
        'Return JSON: {"label": "Conforming" | "Deviating" | "Unclear", '
        '"reasoning": "<1-2 sentences>"}'
    )

    client = get_llm_client()
    raw = await client.complete(prompt, Tier.HAIKU, system=system, max_tokens=256)
    log.debug("deviation.classifier.response", category=rule.category, label_raw=raw[:80])

    data = _parse_json_response(raw)
    label = str(data.get("label", "Unclear"))
    if label not in ("Conforming", "Deviating", "Unclear"):
        label = "Unclear"

    return RuleClassification(
        rule_category=str(rule.category),
        rule_condition=str(rule.condition),
        rule_required_value=rule.required_value,
        rule_severity=str(rule.severity),
        label=cast(Literal["Conforming", "Deviating", "Unclear"], label),
        reasoning=str(data.get("reasoning", "")),
    )


async def _classifier_node(state: DeviationState) -> dict[str, Any]:
    playbook: Playbook = state["playbook"]
    extraction: dict[str, ExtractionResult] = state["extraction_by_category"]
    log.info("deviation.classifier.start", rules=len(playbook.rules))

    classifications: list[RuleClassification] = list(
        await asyncio.gather(
            *[_classify_single_rule(rule, extraction) for rule in playbook.rules]
        )
    )

    log.info(
        "deviation.classifier.done",
        conforming=sum(1 for c in classifications if c.label == "Conforming"),
        deviating=sum(1 for c in classifications if c.label == "Deviating"),
        unclear=sum(1 for c in classifications if c.label == "Unclear"),
    )
    return {"classifications": classifications}


async def _compare_single_rule(
    clf: RuleClassification,
    extraction_by_category: dict[str, ExtractionResult],
) -> RuleComparison:
    display_name = _CATEGORY_TO_DISPLAY.get(clf.rule_category, clf.rule_category)
    ext = extraction_by_category.get(display_name)
    clause_text = ext.clause_text if ext and ext.present and ext.clause_text else None

    system = (
        "You are a senior contract lawyer performing a playbook compliance review. "
        "Analyze the deviation and provide structured findings. "
        "Return JSON only — no markdown fences."
    )
    prompt = (
        f"Playbook requirement:\n"
        f"  Category: {display_name}\n"
        f"  Condition: {clf.rule_condition} {clf.rule_required_value or ''}\n"
        f"  Severity: {clf.rule_severity}\n\n"
        f"Contract clause text:\n"
        f"{clause_text if clause_text else '(not found in contract)'}\n\n"
        f"Classification: {clf.label}\n"
        f"Classifier reasoning: {clf.reasoning}\n\n"
        "Return JSON:\n"
        "{\n"
        '  "evidence_text": "<verbatim excerpt from clause or null if absent>",\n'
        '  "deviation_type": '
        '"Wrong Value | Missing Clause | Forbidden Clause | Ambiguous Language | Partial Compliance"\n'
        "}"
    )

    client = get_llm_client()
    raw = await client.complete(prompt, Tier.SONNET, system=system, max_tokens=512)
    log.debug("deviation.comparator.response", category=clf.rule_category, raw_len=len(raw))

    data = _parse_json_response(raw)
    return RuleComparison(
        rule_category=clf.rule_category,
        rule_condition=clf.rule_condition,
        rule_required_value=clf.rule_required_value,
        rule_severity=clf.rule_severity,
        label=cast(Literal["Deviating", "Unclear"], clf.label),
        evidence_text=str(data.get("evidence_text") or ""),
        deviation_type=str(data.get("deviation_type") or "Unknown"),
    )


async def _comparator_node(state: DeviationState) -> dict[str, Any]:
    classifications: list[RuleClassification] = state.get("classifications") or []
    extraction: dict[str, ExtractionResult] = state["extraction_by_category"]
    non_conforming = [c for c in classifications if c.label in ("Deviating", "Unclear")]

    log.info("deviation.comparator.start", to_compare=len(non_conforming))

    if not non_conforming:
        return {"comparisons": []}

    comparisons: list[RuleComparison] = list(
        await asyncio.gather(
            *[_compare_single_rule(clf, extraction) for clf in non_conforming]
        )
    )

    log.info("deviation.comparator.done", comparisons=len(comparisons))
    return {"comparisons": comparisons}


async def _scorer_node(state: DeviationState) -> dict[str, Any]:
    comparisons: list[RuleComparison] = state.get("comparisons") or []

    per_rule: list[dict[str, str]] = [
        {
            "category": c.rule_category,
            "severity": c.rule_severity,
            "deviation_type": c.deviation_type,
            "label": c.label,
        }
        for c in comparisons
    ]

    if not comparisons:
        overall = "none"
    else:
        severities = {c.rule_severity for c in comparisons}
        overall = "none"
        for sev in _SEVERITY_ORDER:
            if sev in severities:
                overall = sev
                break

    log.info("deviation.scorer.done", overall_severity=overall, rules_scored=len(per_rule))
    return {"score": OverallScore(overall_severity=overall, per_rule=per_rule)}


async def _summarizer_node(state: DeviationState) -> dict[str, Any]:
    playbook: Playbook = state["playbook"]
    score: OverallScore = state["score"]
    comparisons: list[RuleComparison] = state.get("comparisons") or []

    if not comparisons:
        summary = (
            f"The contract fully conforms to the **{playbook.name}** playbook. "
            "No deviations were detected across all reviewed categories."
        )
        log.info("deviation.summarizer.no_deviations")
        return {"summary": summary}

    comparison_lines = "\n".join(
        f"- {c.rule_category} ({c.rule_severity}): {c.deviation_type} — "
        f"{(c.evidence_text or '(no excerpt)')[:200]}"
        for c in comparisons
    )

    system = (
        "You are a contract review specialist. "
        "Write a concise, plain-language deviation report for a business reviewer. "
        "Use markdown. Focus on business risk and what needs to be negotiated."
    )
    prompt = (
        f"Playbook: {playbook.name}\n"
        f"Overall severity: {score.overall_severity.upper()}\n\n"
        f"Deviations found ({len(comparisons)}):\n{comparison_lines}\n\n"
        "Write a 2-4 paragraph deviation report covering:\n"
        "1. Overall risk assessment\n"
        "2. Key deviations and their business impact\n"
        "3. Recommended next steps for negotiation\n"
    )

    client = get_llm_client()
    summary = await client.complete(prompt, Tier.SONNET, system=system, max_tokens=1024)
    log.info("deviation.summarizer.done", summary_len=len(summary))
    return {"summary": summary}


# ---------------------------------------------------------------------------
# Graph construction and entry point
# ---------------------------------------------------------------------------

def _build_graph(session: AsyncSession) -> Any:
    """Compile the LangGraph deviation pipeline for a single run."""

    async def loader(state: DeviationState) -> dict[str, Any]:
        return await _loader_node(state, session)

    builder: StateGraph = StateGraph(DeviationState)  # type: ignore[type-arg]
    builder.add_node("loader", loader)
    builder.add_node("classifier", _classifier_node)
    builder.add_node("comparator", _comparator_node)
    builder.add_node("scorer", _scorer_node)
    builder.add_node("summarizer", _summarizer_node)

    builder.add_edge(START, "loader")
    builder.add_edge("loader", "classifier")
    builder.add_edge("classifier", "comparator")
    builder.add_edge("comparator", "scorer")
    builder.add_edge("scorer", "summarizer")
    builder.add_edge("summarizer", END)

    return builder.compile()


async def run_deviation_pipeline(
    contract_id: str,
    playbook_id: str,
    session: AsyncSession,
) -> DeviationReport:
    """Run the 5-node deviation pipeline and return a structured report.

    Raises:
        DeviationRunError: Contract/playbook not found, or rule count exceeds MAX_RULES.
    """
    log.info("deviation.pipeline.start", contract_id=contract_id, playbook_id=playbook_id)

    graph = _build_graph(session)
    final_state: DeviationState = await graph.ainvoke(
        {
            "contract_id": contract_id,
            "playbook_id": playbook_id,
            "classifications": [],
            "comparisons": [],
        }
    )

    report = DeviationReport(
        contract_id=contract_id,
        playbook_id=playbook_id,
        classifications=final_state.get("classifications") or [],
        comparisons=final_state.get("comparisons") or [],
        score=final_state["score"],
        summary=final_state.get("summary") or "",
    )

    log.info(
        "deviation.pipeline.done",
        contract_id=contract_id,
        overall_severity=report.score.overall_severity,
        deviations=len(report.comparisons),
    )
    return report
