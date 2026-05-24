from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.post("/run")
async def run_deviation(contract_id: str, playbook_id: str) -> dict[str, Any]:
    """Run the LangGraph deviation pipeline against a playbook. Week 5."""
    raise NotImplementedError("Week 5")


@router.post("/{run_id}/review")
async def submit_review(run_id: str, approved: bool, notes: str | None = None) -> dict[str, Any]:
    """Submit HITL review decision for a deviation run. Week 6."""
    raise NotImplementedError("Week 6")
