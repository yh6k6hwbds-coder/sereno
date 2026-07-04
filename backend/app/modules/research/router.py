"""modules/research/router.py — área de pesquisa (RBAC). Braço sempre CODIFICADO."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require
from app.modules.audit.service import list_events

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/_status")
async def status():
    return {"module": "research", "status": "stub"}


@router.get("/participants")
async def list_participants(user: dict = Depends(require("research:read"))):
    # TODO (fatia vertical): listar com braço CODIFICADO (A/B) e paginação por cursor.
    return {"items": [], "next_cursor": None}


def _serialize_event(e) -> dict:
    """Serializa um evento de auditoria para o schema AuditEvent (sem PII, sem braço)."""
    return {
        "id": e.id, "action": e.action, "resource_type": e.resource_type,
        "resource_id": e.resource_id, "actor_type": e.actor_type, "actor_id": e.actor_id,
        "occurred_at": e.occurred_at, "meta": e.meta,
    }


@router.get("/audit")
async def read_audit(limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None),
                     db: Session = Depends(get_db),
                     _user: dict = Depends(require("audit:read"))):
    """Lê o log de auditoria (admin). Append-only, sem PII nem braço; keyset por cursor."""
    rows, next_cursor = list_events(db, limit=limit, cursor=cursor)
    return {"items": [_serialize_event(e) for e in rows], "next_cursor": next_cursor}
