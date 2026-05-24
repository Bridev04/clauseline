from fastapi import APIRouter

router = APIRouter()


@router.post("/ask")
async def ask(contract_id: str, question: str) -> dict:
    """Answer a question over a contract with cited evidence. Week 3."""
    raise NotImplementedError("Week 3")
