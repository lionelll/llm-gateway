from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@router.get("/portal")
async def get_portal() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
