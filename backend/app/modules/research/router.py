"""modules/research/router.py — área de pesquisa (RBAC). Braço sempre CODIFICADO."""
from fastapi import APIRouter, Depends
from app.core.security import require

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/_status")
async def status():
    return {"module": "research", "status": "stub"}


@router.get("/participants")
async def list_participants(user: dict = Depends(require("research:read"))):
    # TODO (fatia vertical): listar com braço CODIFICADO (A/B) e paginação por cursor.
    return {"items": [], "next_cursor": None}
