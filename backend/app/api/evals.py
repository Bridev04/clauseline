from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
async def get_summary() -> dict:
    """Headline metrics + per-bucket breakdown for the /evals dashboard. Week 3."""
    raise NotImplementedError("Week 3")


@router.get("/failures")
async def get_failures(limit: int = 50, offset: int = 0) -> list[dict]:
    """Paginated failure explorer: retrieved chunks + Langfuse trace ID. Week 3."""
    raise NotImplementedError("Week 3")


@router.get("/experiments")
async def get_experiments() -> list[dict]:
    """Experiment timeline including rolled-back runs. Week 4."""
    raise NotImplementedError("Week 4")
