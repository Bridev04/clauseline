"""
Deviation detection API.

  POST /api/deviation/run              — run the 6-node LangGraph pipeline;
                                         pauses at HITL, returns awaiting_review
  GET  /api/deviation/runs             — list recent deviation runs
  GET  /api/deviation/runs/{run_id}    — fetch a persisted run
  POST /api/deviation/{run_id}/review  — submit HITL review decision (Week 6)
"""
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Contract, ContractStatus, DeviationRun, DeviationRunStatus
from app.db.session import get_session
from app.deviation import (
    DeviationReport,
    DeviationRunError,
    resume_deviation_pipeline,
    run_deviation_pipeline,
)
from app.playbooks import load_all_playbooks

log = structlog.get_logger(__name__)
router = APIRouter()


class DeviationRunRequest(BaseModel):
    contract_id: str
    playbook_id: str


class ReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    edited_summary: str | None = None
    notes: str | None = None


class DeviationRunResponse(BaseModel):
    run_id: str
    contract_id: str
    playbook_id: str
    status: str
    overall_severity: str | None = None
    deviations_found: int = 0
    result: dict[str, Any] | None = None
    review_decision: str | None = None
    review_notes: str | None = None
    reviewed_at: str | None = None
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
        review_decision=run.review_decision,
        review_notes=run.review_notes,
        reviewed_at=run.reviewed_at.isoformat() if run.reviewed_at else None,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


@router.post("/run", response_model=DeviationRunResponse)
async def run_deviation(
    req: DeviationRunRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DeviationRunResponse:
    """Run the LangGraph deviation pipeline. Pauses at HITL; returns awaiting_review."""
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

    checkpointer = request.app.state.deviation_checkpointer
    try:
        report: DeviationReport = await run_deviation_pipeline(
            req.contract_id, req.playbook_id, session, run.id, checkpointer
        )
        # Pipeline paused at HITL interrupt; partial result is available.
        run.status = DeviationRunStatus.awaiting_review
        run.result = report.to_dict()
        run.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(run)
        log.info(
            "deviation.run.awaiting_review",
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


@router.get("/runs", response_model=list[DeviationRunResponse])
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, description="Filter by status"),
    session: AsyncSession = Depends(get_session),
) -> list[DeviationRunResponse]:
    """List deviation runs, newest first."""
    stmt = select(DeviationRun).order_by(DeviationRun.created_at.desc()).offset(offset).limit(limit)
    if status:
        try:
            status_enum = DeviationRunStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}") from None
        stmt = stmt.where(DeviationRun.status == status_enum)
    result = await session.execute(stmt)
    runs = list(result.scalars().all())
    return [_run_to_response(r) for r in runs]


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


@router.post("/{run_id}/review", response_model=DeviationRunResponse)
async def submit_review(
    run_id: str,
    req: ReviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DeviationRunResponse:
    """Submit a HITL review decision for a deviation run.

    The run must be in awaiting_review status. On approval the pipeline
    resumes (applying any edited summary) and the run is marked completed.
    On rejection the run is also marked completed with review_decision=rejected.
    """
    run = await session.get(DeviationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Deviation run not found")
    if run.status != DeviationRunStatus.awaiting_review:
        raise HTTPException(
            status_code=409,
            detail=f"Run is not awaiting review (status={run.status.value})",
        )

    log.info(
        "deviation.review.submitted",
        run_id=run_id,
        decision=req.decision,
        has_edit=bool(req.edited_summary),
    )

    checkpointer = request.app.state.deviation_checkpointer
    try:
        report: DeviationReport = await resume_deviation_pipeline(
            run_id=run_id,
            decision=req.decision,
            edited_summary=req.edited_summary,
            session=session,
            checkpointer=checkpointer,
        )
    except DeviationRunError as exc:
        log.warning("deviation.review.resume_failed", run_id=run_id, error=str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Update result with final (possibly edited) summary and review metadata.
    run.result = report.to_dict()
    run.status = DeviationRunStatus.completed
    run.review_decision = req.decision
    run.review_notes = req.notes
    run.reviewed_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(run)

    log.info(
        "deviation.review.completed",
        run_id=run_id,
        decision=req.decision,
        overall_severity=report.score.overall_severity,
    )
    return _run_to_response(run)
