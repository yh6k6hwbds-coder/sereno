"""
modules/data_rights/service.py — Direitos do titular (LGPD): acesso/portabilidade e eliminação.

- **Eliminação:** remove a PII DIRETA (contato cifrado, artefatos de OTP) e marca o participante
  como ``withdrawn``. Os dados de pesquisa PSEUDONIMIZADOS são **retidos** (exceção de pesquisa da
  LGPD; ver ADR-066); a auditoria é append-only e **nunca** é apagada.
- **Acesso:** reúne os dados do titular (com a PII **decifrada**, pois é o próprio dado dele),
  **SEM** revelar o braço/condição (cegamento preservado até o desbloqueio controlado).
"""
from __future__ import annotations
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.models import (Participant, ContactInfo, OtpChallenge, ConsentRecord, Screening,
                             BaselineAssessment, FollowupAssessment, Session as SessionModel,
                             SleepDiary, AdverseEvent)
from app.core import pii_crypto


def erase_personal_data(db: Session, participant_id: uuid.UUID) -> dict:
    """Remove PII direta e marca ``withdrawn``. Retém pesquisa pseudonimizada; não toca auditoria."""
    contact_n = db.execute(
        delete(ContactInfo).where(ContactInfo.participant_id == participant_id)).rowcount
    otp_n = db.execute(
        delete(OtpChallenge).where(OtpChallenge.participant_id == participant_id)).rowcount
    p = db.get(Participant, participant_id)
    p.status = "withdrawn"
    db.flush()
    return {"contact_info": int(contact_n or 0), "otp_challenges": int(otp_n or 0)}


def _decrypt_contact(db: Session, participant_id: uuid.UUID) -> dict | None:
    c = db.scalar(select(ContactInfo).where(ContactInfo.participant_id == participant_id))
    if c is None:
        return None
    try:
        return {
            "name": pii_crypto.decrypt(c.enc_name, aad=pii_crypto.aad_for(participant_id, "name")),
            "email": pii_crypto.decrypt(c.enc_email, aad=pii_crypto.aad_for(participant_id, "email")),
        }
    except Exception:  # noqa: BLE001 — sem a chave, não decifra (retorna indicador, sem PII)
        return {"name": None, "email": None}


def export_subject_data(db: Session, participant_id: uuid.UUID) -> dict:
    """Reúne os dados do titular. NUNCA inclui o braço/condição (cegamento preservado)."""
    p = db.get(Participant, participant_id)

    def rows(model, cols: list[str]) -> list[dict]:
        return [{c: getattr(r, c) for c in cols}
                for r in db.scalars(select(model).where(model.participant_id == participant_id))]

    return {
        "profile": {"study_code": p.study_code, "status": p.status, "enrolled_at": p.enrolled_at},
        "contact": _decrypt_contact(db, participant_id),
        "consent": rows(ConsentRecord, ["tcle_version", "accepted", "accepted_at"]),
        "screening": rows(Screening, ["eligible", "screened_at"]),
        "baseline": rows(BaselineAssessment, ["gad7_total", "psqi_global", "assessed_at"]),
        "followup": rows(FollowupAssessment,
                         ["gad7_total", "psqi_global", "sus_score", "blinding_guess", "assessed_at"]),
        "sleep_diary": rows(SleepDiary,
                            ["diary_date", "latency_min", "awakenings", "duration_h", "quality"]),
        "adverse_events": rows(AdverseEvent, ["type", "severity", "occurred_at"]),
        "sessions_completed": int(db.scalar(select(func.count()).select_from(SessionModel).where(
            SessionModel.participant_id == participant_id, SessionModel.completed.is_(True))) or 0),
        # Nota: alocação/braço/condição são DELIBERADAMENTE omitidos (cegamento).
    }
