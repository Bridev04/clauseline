"""Unit tests for the deviation Loader node — error paths, no LLM calls."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.deviation import DeviationRunError, _loader_node


def _make_state(contract_id: str = "cid", playbook_id: str = "acme-saas-v1") -> dict:  # type: ignore[type-arg]
    return {"contract_id": contract_id, "playbook_id": playbook_id}


@pytest.mark.asyncio
async def test_loader_raises_on_missing_contract() -> None:
    session = AsyncMock()
    session.get.return_value = None  # contract not found

    with pytest.raises(DeviationRunError, match="Contract not found"):
        await _loader_node(_make_state(), session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_loader_raises_on_unknown_playbook() -> None:
    session = AsyncMock()
    session.get.return_value = MagicMock()  # contract exists

    with (
        patch("app.deviation.load_all_playbooks", return_value={}),
        patch("app.deviation.get_settings", return_value=MagicMock(playbooks_dir="/tmp")),
        pytest.raises(DeviationRunError, match="Playbook not found"),
    ):
        await _loader_node(_make_state(playbook_id="nonexistent"), session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_loader_raises_on_rule_cap_exceeded() -> None:
    session = AsyncMock()
    session.get.return_value = MagicMock()

    from app.playbooks import Condition, CUADCategory, Playbook, PlaybookRule, Severity

    overloaded_playbook = Playbook(
        id="big-playbook",
        name="Big Playbook",
        rules=[
            PlaybookRule(
                category=CUADCategory.governing_law,
                condition=Condition.present,
                severity=Severity.low,
            )
        ]
        * 51,  # 51 rules — exceeds MAX_RULES=50
    )

    with (
        patch("app.deviation.load_all_playbooks", return_value={"big-playbook": overloaded_playbook}),
        patch("app.deviation.get_settings", return_value=MagicMock(playbooks_dir="/tmp")),
        pytest.raises(DeviationRunError, match="limit"),
    ):
        await _loader_node(_make_state(playbook_id="big-playbook"), session)  # type: ignore[arg-type]
