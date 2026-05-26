"""
Playbooks API.

  GET /api/playbooks/  — list available playbooks (metadata only)
"""
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.playbooks import load_all_playbooks

router = APIRouter()


class PlaybookSummary(BaseModel):
    id: str
    name: str
    version: str
    description: str | None
    rule_count: int


@router.get("/", response_model=list[PlaybookSummary])
async def list_playbooks() -> list[PlaybookSummary]:
    """List available playbooks (metadata only — no rule details)."""
    settings = get_settings()
    playbooks = load_all_playbooks(Path(settings.playbooks_dir))
    return [
        PlaybookSummary(
            id=pb.id,
            name=pb.name,
            version=pb.version,
            description=pb.description,
            rule_count=len(pb.rules),
        )
        for pb in playbooks.values()
    ]
