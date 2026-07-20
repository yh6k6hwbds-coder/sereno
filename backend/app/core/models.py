"""
models.py — Modelo físico (SQLAlchemy 2.0) do backend do piloto de neuromodulação.

Tipos PORTÁVEIS: mantêm JSONB/UUID/INET nativos no PostgreSQL (via .with_variant)
e degradam para JSON/CHAR/VARCHAR no SQLite (dev/testes). Assim o CI roda testes de
banco sem subir um Postgres, e a produção continua Postgres-nativa.

Convenções: PK UUID, timestamps com fuso, integridade no banco (FK + CHECK + UNIQUE),
dado de pesquisa pseudonimizado e PII separada. O braço é armazenado CODIFICADO (A/B);
o vínculo A/B → ativo/sham é mantido à parte, com proteção reforçada.
"""
from __future__ import annotations
import datetime as dt
import uuid
from sqlalchemy import (String, Integer, SmallInteger, Boolean, Numeric, Date, DateTime,
                        LargeBinary, JSON, Uuid, ForeignKey, CheckConstraint, UniqueConstraint,
                        func, text)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB, INET as PG_INET
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Variantes: nativo no Postgres, portátil no SQLite.
JSONB = JSON().with_variant(PG_JSONB, "postgresql")
INET = String(45).with_variant(PG_INET, "postgresql")

def UUID_PK():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
def fk(target: str, nullable: bool = False, ondelete: str = "CASCADE"):
    return mapped_column(Uuid, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)
def TS(default: bool = True):
    return mapped_column(DateTime(timezone=True), server_default=func.now() if default else None,
                         nullable=not default)


class Base(DeclarativeBase):
    pass


class Participant(Base):
    __tablename__ = "participant"
    id: Mapped[uuid.UUID] = UUID_PK()
    study_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'active'"))
    enrolled_at: Mapped[dt.datetime] = TS()
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("status in ('active','withdrawn','completed')", name="ck_participant_status"),)


class ContactInfo(Base):                       # PII separada e cifrada na aplicação
    __tablename__ = "contact_info"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    enc_name: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enc_email: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[dt.datetime] = TS()
    __table_args__ = (UniqueConstraint("participant_id", name="uq_contact_participant"),)


class ConsentRecord(Base):
    __tablename__ = "consent_record"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    tcle_version: Mapped[str] = mapped_column(String(20), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accepted_at: Mapped[dt.datetime] = TS()
    ip_address: Mapped[str] = mapped_column(INET, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revoked_at: Mapped[dt.datetime] = TS(default=False)


class Screening(Base):
    __tablename__ = "screening"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)
    symptoms: Mapped[dict] = mapped_column(JSONB, nullable=True)
    screened_at: Mapped[dt.datetime] = TS()


class AudioProtocol(Base):                     # versionado; identificador NEUTRO (não revela braço)
    __tablename__ = "audio_protocol"
    id: Mapped[uuid.UUID] = UUID_PK()
    protocol_id: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    band: Mapped[str] = mapped_column(String(8), nullable=False)
    carrier_hz: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    beat_hz: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    duration_s: Mapped[float] = mapped_column(Numeric(7, 1), nullable=False)
    target_peak_dbfs: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = TS()
    __table_args__ = (
        UniqueConstraint("protocol_id", "version", name="uq_protocol_version"),
        CheckConstraint("band in ('alpha','theta','delta')", name="ck_protocol_band"),
        CheckConstraint("carrier_hz > 0 and duration_s > 0", name="ck_protocol_positive"),
    )


class Allocation(Base):                        # braço CODIFICADO; mapa A/B→ativo/sham fica à parte
    __tablename__ = "allocation"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    arm_coded: Mapped[str] = mapped_column(String(1), nullable=False)
    block: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_seed_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    allocated_at: Mapped[dt.datetime] = TS()
    # Desbloqueio em DUAS PESSOAS (ADR-075): passo 1 grava o pedido; passo 2 (2º admin distinto)
    # grava unblinded_at ao revelar. requested_by guarda o solicitante p/ impor a regra "2 pessoas".
    unblind_requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=True)
    unblind_requested_at: Mapped[dt.datetime] = TS(default=False)
    unblind_justification: Mapped[str] = mapped_column(String(500), nullable=True)
    unblinded_at: Mapped[dt.datetime] = TS(default=False)
    __table_args__ = (
        UniqueConstraint("participant_id", name="uq_allocation_participant"),
        CheckConstraint("arm_coded in ('A','B')", name="ck_allocation_arm"),
    )


class BaselineAssessment(Base):
    __tablename__ = "baseline_assessment"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    gad7_items: Mapped[dict] = mapped_column(JSONB, nullable=False)
    gad7_total: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    psqi_input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    psqi_global: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score_version: Mapped[str] = mapped_column(String(20), nullable=False)
    assessed_at: Mapped[dt.datetime] = TS()
    __table_args__ = (
        CheckConstraint("gad7_total between 0 and 21", name="ck_baseline_gad7"),
        CheckConstraint("psqi_global between 0 and 21", name="ck_baseline_psqi"),
    )


class FollowupAssessment(Base):
    __tablename__ = "followup_assessment"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    gad7_items: Mapped[dict] = mapped_column(JSONB, nullable=False)     # bruto
    gad7_total: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    psqi_input: Mapped[dict] = mapped_column(JSONB, nullable=False)     # bruto
    psqi_global: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sus_items: Mapped[dict] = mapped_column(JSONB, nullable=False)      # bruto
    sus_score: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)   # 0.0–100.0
    blinding_guess: Mapped[str] = mapped_column(String(8), nullable=True)     # palpite; NUNCA o braço real
    score_version: Mapped[str] = mapped_column(String(20), nullable=False)
    assessed_at: Mapped[dt.datetime] = TS()
    __table_args__ = (
        CheckConstraint("gad7_total between 0 and 21", name="ck_follow_gad7"),
        CheckConstraint("psqi_global between 0 and 21", name="ck_follow_psqi"),
        CheckConstraint("sus_score between 0 and 100", name="ck_follow_sus"),
        CheckConstraint("blinding_guess in ('A','B','nao_sei') or blinding_guess is null", name="ck_follow_guess"),
    )


class Session(Base):
    __tablename__ = "session"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    protocol_uuid: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("audio_protocol.id", ondelete="RESTRICT"), index=True)
    protocol_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[dt.datetime] = TS()
    ended_at: Mapped[dt.datetime] = TS(default=False)
    effective_seconds: Mapped[int] = mapped_column(Integer, nullable=True)
    interruptions: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    headphones_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    device_info: Mapped[dict] = mapped_column(JSONB, nullable=True)


class PostSessionSurvey(Base):
    __tablename__ = "post_session_survey"
    id: Mapped[uuid.UUID] = UUID_PK()
    session_id: Mapped[uuid.UUID] = fk("session.id")
    feeling: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    relaxation: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    slept_better: Mapped[int] = mapped_column(SmallInteger, nullable=True)
    liked: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    intensity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    would_repeat: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[dt.datetime] = TS()
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_survey_session"),
        CheckConstraint("feeling between 0 and 4 and relaxation between 0 and 4 and liked between 0 and 4 and intensity between 0 and 4", name="ck_survey_scales"),
    )


class SleepDiary(Base):
    __tablename__ = "sleep_diary"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    diary_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    latency_min: Mapped[int] = mapped_column(Integer, nullable=True)
    awakenings: Mapped[int] = mapped_column(Integer, nullable=True)
    duration_h: Mapped[float] = mapped_column(Numeric(4, 2), nullable=True)
    quality: Mapped[int] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[dt.datetime] = TS()
    __table_args__ = (UniqueConstraint("participant_id", "diary_date", name="uq_diary_day"),)


class AdverseEvent(Base):
    __tablename__ = "adverse_event"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("session.id", ondelete="SET NULL"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(200), nullable=True)
    outcome: Mapped[str] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[dt.datetime] = TS()
    __table_args__ = (CheckConstraint("severity in ('mild','moderate','severe')", name="ck_ae_severity"),)


class RecommendationLog(Base):
    __tablename__ = "recommendation_log"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("session.id", ondelete="SET NULL"), nullable=True)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    # nullable: o guardrail de contraindicação produz `no_recommendation` (sem protocolo);
    # esse evento de segurança é registrado fielmente com NULL (E1/ADR-068).
    suggested_protocol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[dt.datetime] = TS()


class StaffUser(Base):                          # pesquisador/admin — RBAC + MFA
    __tablename__ = "staff_user"
    id: Mapped[uuid.UUID] = UUID_PK()
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)   # argon2id
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    mfa_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Lifecycle: desativar suspende o acesso sem apagar a trilha de autoria (ADR-081).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[dt.datetime] = TS(default=False)
    created_at: Mapped[dt.datetime] = TS()
    __table_args__ = (CheckConstraint("role in ('researcher','admin')", name="ck_staff_role"),)


class AuditLog(Base):                           # append-only (guard ORM + trigger no banco; ADR-086)
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = UUID_PK()
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[dt.datetime] = TS()


class OtpChallenge(Base):                        # login de participante por código de uso único
    __tablename__ = "otp_challenge"
    id: Mapped[uuid.UUID] = UUID_PK()
    participant_id: Mapped[uuid.UUID] = fk("participant.id")
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)   # sha256(código+pepper)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[dt.datetime] = TS()
