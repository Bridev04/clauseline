"""
Deviation detection API.

  POST /api/deviation/run             — run the 5-node LangGraph pipeline
  GET  /api/deviation/runs/{run_id}   — fetch a persisted run
  POST /api/deviation/{run_id}/review — HITL review (Week 6 stub)

Runs are synchronous from the caller's perspective. The pipeline result is
persisted in deviation_runs before the response is returned.
"""
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Contract, ContractStatus, DeviationRun, DeviationRunStatus
from app.db.session import get_session
from app.deviation import DeviationReport, DeviationRunError, run_deviation_pipeline
from app.playbooks import load_all_playbooks

log = structlog.get_logger(__name__)
router = APIRouter()


class DeviationRunRequest(BaseModel):
    contract_id: str
    playbook_id: str


class DeviationRunResponse(BaseModel):
    run_id: str
    contract_id: str
    playbook_id: str
    status: str
    overall_severity: str | None = None
    deviations_found: int = 0
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str


def _run_to_response(run: DeviationRun) -> DeviationRunResponse:
    result = run.result
    overall_severity: str | None = None
    deviations_found = 0
    if result and isinstance(result, dict):
        score = result.get("score")
        if isinstance(score, dict):
            overall_severity = (
                str(score["overall_severity"]) if "overall_severity" in score else None
            )
        comparisons = result.get("comparisons")
        if isinstance(comparisons, list):
            deviations_found = len(comparisons)

    return DeviationRunResponse(
        run_id=run.id,
        contract_id=run.contract_id,
        playbook_id=run.playbook_id,
        status=str(run.status),
        overall_severity=overall_severity,
        deviations_found=deviations_found,
        result=result,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


@router.post("/run", response_model=DeviationRunResponse)
async def run_deviation(
    req: DeviationRunRequest,
    session: AsyncSession = Depends(get_session),
) -> DeviationRunResponse:
    """Run the LangGraph deviation pipeline against a playbook. Week 5."""
    contract = await session.get(Contract, req.contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract.status != ContractStatus.ready:
        raise HTTPException(
            status_code=409,
            detail=f"Contract is not ready (status={contract.status.value})",
        )

    settings = get_settings()
    playbooks = load_all_playbooks(Path(settings.playbooks_dir))
    if req.playbook_id not in playbooks:
        raise HTTPException(status_code=404, detail=f"Playbook not found: {req.playbook_id}")

    now = datetime.now(UTC)
    run = DeviationRun(
        id=str(uuid.uuid4()),
        contract_id=req.contract_id,
        playbook_id=req.playbook_id,
        status=DeviationRunStatus.running,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    log.info(
        "deviation.run.start",
        run_id=run.id,
        contract_id=req.contract_id,
        playbook_id=req.playbook_id,
    )

    try:
        report: DeviationReport = await run_deviation_pipeline(
            req.contract_id, req.playbook_id, session
        )
        run.status = DeviationRunStatus.completed
        run.result = report.to_dict()
        run.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(run)
        log.info(
            "deviation.run.completed",
            run_id=run.id,
            overall_severity=report.score.overall_severity,
            deviations=len(report.comparisons),
        )

    except DeviationRunError as exc:
        run.status = DeviationRunStatus.failed
        run.error = str(exc)
        run.updated_at = datetime.now(UTC)
        await session.commit()
        log.warning("deviation.run.failed", run_id=run.id, error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:
        run.status = DeviationRunStatus.failed
        run.error = type(exc).__name__
        run.updated_at = datetime.now(UTC)
        await session.commit()
        log.error("deviation.run.error", run_id=run.id, exc_type=type(exc).__name__)
        raise HTTPException(status_code=500, detail="Deviation pipeline failed") from exc

    return _run_to_response(run)


@router.get("/runs/{run_id}", response_model=DeviationRunResponse)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> DeviationRunResponse:
    """Fetch a persisted deviation run by ID."""
    run = await session.get(DeviationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Deviation run not found")
    return _run_to_response(run)


@router.post("/{run_id}/review")
async def submit_review(run_id: str, approved: bool, notes: str | None = None) -> dict[str, Any]:
    """Submit HITL review decision for a deviation run. Week 6."""
    raise NotImplementedError("Week 6")
