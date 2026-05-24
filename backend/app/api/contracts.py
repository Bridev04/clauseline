from fastapi import APIRouter, UploadFile

router = APIRouter()


@router.post("/upload")
async def upload_contract(file: UploadFile) -> dict[str, str]:
    """Ingest a PDF, parse, chunk, embed, and store. Week 1."""
    raise NotImplementedError("Week 1")


@router.get("/")
async def list_contracts() -> list[dict]:
    """List all ingested contracts. Week 1."""
    raise NotImplementedError("Week 1")


@router.get("/{contract_id}")
async def get_contract(contract_id: str) -> dict:
    """Retrieve metadata for a single contract. Week 1."""
    raise NotImplementedError("Week 1")
