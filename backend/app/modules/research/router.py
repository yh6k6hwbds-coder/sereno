"""modules/research/router.py — área de pesquisa (RBAC). Braço sempre CODIFICADO."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require
from app.core.problem import ProblemException
from app.modules.audit.service import list_events, record_event
from app.modules.research.export_service import build_export_csv_from_db, get_job_store
from app.modules.research.features_service import build_features_csv_from_db
from app.modules.research.analysis_service import build_report
from app.modules.recommender.service import coherence as recommendation_coherence

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/_status")
async def status():
    return {"module": "research", "status": "stub"}


@router.get("/participants")
async def list_participants(user: dict = Depends(require("research:read"))):
    # TODO (fatia vertical): listar com braço CODIFICADO (A/B) e paginação por cursor.
    return {"items": [], "next_cursor": None}


@router.get("/analysis")
async def get_analysis(db: Session = Depends(get_db),
                       _user: dict = Depends(require("research:read"))):
    """Relatório reprodutível e CEGO (por braço A/B). Exploratório; não decide eficácia."""
    return build_report(db)


@router.get("/recommendation-coherence")
async def get_recommendation_coherence(db: Session = Depends(get_db),
                                       _user: dict = Depends(require("research:read"))):
    """Coerência do recomendador (exploratório, CEGO): alinhamento objetivo→banda e aceitação."""
    return recommendation_coherence(db)


@router.get("/ml-features")
async def get_ml_features(db: Session = Depends(get_db),
                         user: dict = Depends(require("export:request"))):
    """Dataset OFFLINE de features p/ ML (E4): CSV pseudonimizado e CEGO (braço codificado).

    Consolida o `recommendation_log` + telemetria já registrados — **nada decide aqui** (o
    recomendador segue por regras, inegociável #5). Sem PII, sem condição. Auditado."""
    csv_body = build_features_csv_from_db(db)
    actor_id = None
    try:
        actor_id = uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    # Auditoria SEM PII/braço: só o fato do export de features (nº de linhas, sem conteúdo).
    record_event(db, action="features.exported", resource_type="ml_feature_dataset",
                 actor_type="staff", actor_id=actor_id,
                 meta={"rows": max(csv_body.count("\n") - 1, 0)})
    return Response(content=csv_body, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="sereno_ml_features.csv"',
                             "Cache-Control": "private, no-store"})


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


@router.post("/export", status_code=202)
async def request_export(db: Session = Depends(get_db),
                         user: dict = Depends(require("export:request"))):
    """Solicita a exportação pseudonimizada (sem PII, sem condição). Registrada em auditoria."""
    job = get_job_store().run(lambda: build_export_csv_from_db(db))
    actor_id = None
    try:
        actor_id = uuid.UUID(str(user["id"]))
    except (KeyError, ValueError, TypeError):
        pass
    record_event(db, action="export.requested", resource_type="research_export",
                 actor_type="staff", actor_id=actor_id, resource_id=uuid.UUID(job.id),
                 meta={"status": job.status})
    return {"job_id": job.id, "status": job.status}


@router.get("/export/{job_id}")
async def get_export(job_id: uuid.UUID, _user: dict = Depends(require("export:request"))):
    """Status (JSON) ou o arquivo (CSV) quando concluído. Nunca contém PII nem a condição."""
    job = get_job_store().get(str(job_id))
    if job is None:
        raise ProblemException(404, "Exportação não encontrada", "Job de exportação inexistente.")
    if job.status != "done" or job.result is None:
        return {"job_id": job.id, "status": job.status}
    return Response(content=job.result, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="sereno_export.csv"',
                             "Cache-Control": "private, no-store"})
