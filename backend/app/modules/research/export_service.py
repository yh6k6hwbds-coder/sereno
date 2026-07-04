"""
modules/research/export_service.py — Exportação pseudonimizada + job (porta).

Monta o CSV de análise **reusando** ``instruments_scoring.build_export_csv``. Regras
inegociáveis:
  - **SEM PII** (só o ``study_code`` pseudônimo);
  - **SEM a condição** (ativo/sham) nem a chave selada — apenas o braço **CODIFICADO A/B**,
    que a análise cega precisa (o mapa A/B→condição só abre no *data lock*).

Casos **completos**: participante alocado com baseline **e** seguimento (a análise de desfechos
usa o par basal→seguimento); adesão e eventos adversos entram como métricas. Incompletos ficam
de fora deste export (tratamento de perdas é do plano de análise, C7).

O "job" é uma **porta**: aqui roda inline (N pequeno) e guarda o resultado em memória; em
produção troca-se por RQ/Redis + armazenamento (URLs assinadas). Não persiste em banco (sem
migração).
"""
from __future__ import annotations
import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import (Allocation, Participant, BaselineAssessment,
                             FollowupAssessment, Session as SessionModel, AdverseEvent)
from app.modules.instruments.instruments_scoring import ParticipantExport, build_export_csv

PRESCRIBED_SESSIONS = 20


def _arm_label(arm_coded: str) -> str:
    """Rótulo CODIFICADO (nunca a condição): 'A'→'Grupo A', 'B'→'Grupo B'."""
    return "Grupo A" if arm_coded == "A" else "Grupo B"


def gather_export_rows(db: Session) -> list[ParticipantExport]:
    """Casos completos (alocado + baseline + seguimento), pseudonimizados e cegos."""
    rows: list[ParticipantExport] = []
    for alloc in db.scalars(select(Allocation)).all():
        pid = alloc.participant_id
        base = db.scalar(select(BaselineAssessment).where(BaselineAssessment.participant_id == pid)
                         .order_by(BaselineAssessment.assessed_at.desc()))
        fu = db.scalar(select(FollowupAssessment).where(FollowupAssessment.participant_id == pid)
                       .order_by(FollowupAssessment.assessed_at.desc()))
        if base is None or fu is None:
            continue   # incompleto: fora do export de casos completos
        p = db.get(Participant, pid)
        completed = db.scalar(select(func.count()).select_from(SessionModel).where(
            SessionModel.participant_id == pid, SessionModel.completed.is_(True))) or 0
        ae = db.scalar(select(func.count()).select_from(AdverseEvent).where(
            AdverseEvent.participant_id == pid)) or 0
        rows.append(ParticipantExport(
            code=p.study_code,
            arm_coded=_arm_label(alloc.arm_coded),
            gad7_base=base.gad7_total, gad7_fu=fu.gad7_total,
            psqi_base=base.psqi_global, psqi_fu=fu.psqi_global,
            sus_fu=int(round(float(fu.sus_score))),
            adherence_pct=round(100 * int(completed) / PRESCRIBED_SESSIONS, 1),
            adverse_events=int(ae),
            blinding_guess=fu.blinding_guess or "nao_sei",
        ))
    return rows


def build_export_csv_from_db(db: Session) -> str:
    return build_export_csv(gather_export_rows(db))


# ----------------------------------------------------------------------------
# Job (porta): in-memory no piloto; RQ/Redis + storage em produção.
# ----------------------------------------------------------------------------
@dataclass
class ExportJob:
    id: str
    status: str            # queued | running | done | failed
    result: str | None
    created_at: dt.datetime


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ExportJob] = {}

    def run(self, fn: Callable[[], str]) -> ExportJob:
        """No piloto executa inline; em produção enfileira (RQ). Guarda o resultado."""
        jid = str(uuid.uuid4())
        now = dt.datetime.now(dt.timezone.utc)
        try:
            job = ExportJob(jid, "done", fn(), now)
        except Exception:  # noqa: BLE001 — falha do export vira status 'failed' (não derruba a API)
            job = ExportJob(jid, "failed", None, now)
        self._jobs[jid] = job
        return job

    def get(self, job_id: str) -> ExportJob | None:
        return self._jobs.get(job_id)

    def reset(self) -> None:
        self._jobs.clear()


_store: InMemoryJobStore | None = None


def get_job_store() -> InMemoryJobStore:
    global _store
    if _store is None:
        _store = InMemoryJobStore()
    return _store
