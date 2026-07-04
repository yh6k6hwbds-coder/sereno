"""
modules/screening/service.py — Elegibilidade (regra transparente/versionada) + gate do funil.

A triagem é o 1º passo da inscrição: decide elegibilidade por uma regra **determinística** —
todas as inclusões verdadeiras E nenhuma exclusão presente. As CHAVES concretas dos critérios
vêm do protocolo aprovado (CEP); aqui aplica-se apenas a meta-regra, versionada (``criteria``
guarda a versão). O funil exige **triagem elegível + consentimento aceito** antes de alocar.
"""
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Screening, ConsentRecord

CRITERIA_VERSION = "1.0.0"


def evaluate_eligibility(inclusion: dict[str, bool], exclusion: dict[str, bool]) -> bool:
    """Elegível ⇔ todas as inclusões verdadeiras e nenhuma exclusão presente."""
    return all(bool(v) for v in inclusion.values()) and not any(bool(v) for v in exclusion.values())


def latest_screening(db: Session, participant_id: uuid.UUID) -> Screening | None:
    return db.scalar(select(Screening).where(Screening.participant_id == participant_id)
                     .order_by(Screening.screened_at.desc()))


def has_accepted_consent(db: Session, participant_id: uuid.UUID) -> bool:
    return db.scalar(select(ConsentRecord.id).where(
        ConsentRecord.participant_id == participant_id,
        ConsentRecord.accepted.is_(True),
        ConsentRecord.revoked_at.is_(None))) is not None


def enrollment_blocker(db: Session, participant_id: uuid.UUID) -> str | None:
    """``None`` se apto a alocar; senão, o motivo do bloqueio (para 409). Ordena o funil."""
    sc = latest_screening(db, participant_id)
    if sc is None:
        return "Triagem pendente: registre a triagem antes de alocar."
    if not sc.eligible:
        return "Participante inelegível na triagem."
    if not has_accepted_consent(db, participant_id):
        return "Consentimento (TCLE) pendente: obtenha o aceite antes de alocar."
    return None
