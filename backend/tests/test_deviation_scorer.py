"""Unit tests for the deviation Scorer node — purely deterministic, no LLM or DB."""
import pytest

from app.deviation import OverallScore, RuleComparison, _scorer_node


def _make_comparison(severity: str, category: str = "governing_law") -> RuleComparison:
    return RuleComparison(
        rule_category=category,
        rule_condition="eq",
        rule_required_value="California",
        rule_severity=severity,
        label="Deviating",
        evidence_text="This agreement is governed by the laws of New York.",
        deviation_type="Wrong Value",
    )


@pytest.mark.asyncio
async def test_scorer_all_conforming_returns_none() -> None:
    state = {"contract_id": "c1", "playbook_id": "p1", "comparisons": []}
    result = await _scorer_node(state)  # type: ignore[arg-type]
    score: OverallScore = result["score"]
    assert score.overall_severity == "none"
    assert score.per_rule == []


@pytest.mark.asyncio
async def test_scorer_single_critical_deviation() -> None:
    state = {
        "contract_id": "c1",
        "playbook_id": "p1",
        "comparisons": [_make_comparison("critical")],
    }
    result = await _scorer_node(state)  # type: ignore[arg-type]
    score: OverallScore = result["score"]
    assert score.overall_severity == "critical"
    assert len(score.per_rule) == 1
    assert score.per_rule[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_scorer_precedence_critical_wins_over_low() -> None:
    state = {
        "contract_id": "c1",
        "playbook_id": "p1",
        "comparisons": [
            _make_comparison("low", "confidentiality"),
            _make_comparison("critical", "governing_law"),
            _make_comparison("medium", "cap_on_liability"),
        ],
    }
    result = await _scorer_node(state)  # type: ignore[arg-type]
    score: OverallScore = result["score"]
    assert score.overall_severity == "critical"
    assert len(score.per_rule) == 3


@pytest.mark.asyncio
async def test_scorer_high_without_critical() -> None:
    state = {
        "contract_id": "c1",
        "playbook_id": "p1",
        "comparisons": [
            _make_comparison("high"),
            _make_comparison("low"),
        ],
    }
    result = await _scorer_node(state)  # type: ignore[arg-type]
    assert result["score"].overall_severity == "high"


@pytest.mark.asyncio
async def test_scorer_medium_only() -> None:
    state = {
        "contract_id": "c1",
        "playbook_id": "p1",
        "comparisons": [_make_comparison("medium")],
    }
    result = await _scorer_node(state)  # type: ignore[arg-type]
    assert result["score"].overall_severity == "medium"


@pytest.mark.asyncio
async def test_scorer_per_rule_entries_match_comparisons() -> None:
    comparisons = [
        _make_comparison("high", "governing_law"),
        _make_comparison("low", "confidentiality"),
    ]
    state = {"contract_id": "c1", "playbook_id": "p1", "comparisons": comparisons}
    result = await _scorer_node(state)  # type: ignore[arg-type]
    score: OverallScore = result["score"]
    categories = {r["category"] for r in score.per_rule}
    assert "governing_law" in categories
    assert "confidentiality" in categories


@pytest.mark.asyncio
async def test_scorer_unclear_label_treated_same_as_deviating() -> None:
    comp = RuleComparison(
        rule_category="non_compete",
        rule_condition="absent",
        rule_required_value=None,
        rule_severity="high",
        label="Unclear",
        evidence_text="",
        deviation_type="Ambiguous Language",
    )
    state = {"contract_id": "c1", "playbook_id": "p1", "comparisons": [comp]}
    result = await _scorer_node(state)  # type: ignore[arg-type]
    assert result["score"].overall_severity == "high"
