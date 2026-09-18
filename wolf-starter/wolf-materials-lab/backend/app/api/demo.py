"""Synthetic demo fixtures exposed only for the hackathon workflow UI."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/demo", tags=["demo"])
FIXTURE = Path(__file__).resolve().parents[2] / "demo" / "france-v2.csv"


@router.get("/france-v2", response_class=FileResponse)
async def get_france_v2_fixture() -> FileResponse:
    """Return the official synthetic France V2 replacement fixture."""
    if not FIXTURE.is_file():
        raise HTTPException(status_code=404, detail="France demo fixture is not installed.")
    return FileResponse(FIXTURE, media_type="text/csv", filename="FR-v2--Sheet1.csv")
