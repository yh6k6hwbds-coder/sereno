"""
tests/test_retention_otp.py — Expurgo dos desafios de OTP (E2 / política de retenção).

Prova o "Pronto (DoD)":
  - expurga o que já expirou além da carência; respeita a carência;
  - **NUNCA apaga desafio ainda válido** — apagá-lo zeraria `attempts` e devolveria ao
    atacante um novo lote de tentativas (é a invariante de segurança da fatia);
  - idempotente (rodar de novo apaga 0) e não mexe em outras tabelas;
  - registra a contagem na auditoria (evidência de que o controle rodou — RIPD R-10), sem PII
    e sem participante; não audita quando não há nada a apagar (evita ruído diário);
  - o fluxo de login segue íntegro depois do expurgo.
"""
from __future__ import annotations
import datetime as dt

from sqlalchemy import select, func

from app.core.models import Participant, OtpChallenge, AuditLog
from app.core import otp
from app.modules.retention.service import purge_expired_otp

REQ_OTP = "/v1/auth/participant/request-otp"
VERIFY = "/v1/auth/participant/verify-otp"


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _participant(TestSession, code="P-RET"):
    with TestSession() as s:
        p = Participant(study_code=code)
        s.add(p)
        s.commit()
        return p.id


def _challenge(TestSession, pid, *, expires_in_min: float, code="123456",
               consumed=False, attempts=0):
    with TestSession() as s:
        ch = OtpChallenge(participant_id=pid, code_hash=otp.hash_code(code),
                          expires_at=_now() + dt.timedelta(minutes=expires_in_min),
                          consumed=consumed, attempts=attempts)
        s.add(ch)
        s.commit()
        return ch.id


def _count(TestSession, model=OtpChallenge):
    with TestSession() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_purge_apaga_expirado_alem_da_carencia(api):
    _client, TestSession = api
    pid = _participant(TestSession)
    _challenge(TestSession, pid, expires_in_min=-120)     # expirou há 2 h
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=60) == 1
        s.commit()
    assert _count(TestSession) == 0


def test_purge_respeita_a_carencia(api):
    _client, TestSession = api
    pid = _participant(TestSession)
    _challenge(TestSession, pid, expires_in_min=-10)      # expirou há 10 min (< carência)
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=60) == 0
        s.commit()
    assert _count(TestSession) == 1


def test_purge_nunca_apaga_desafio_valido(api):
    """INVARIANTE DE SEGURANÇA: apagar um desafio vivo zeraria `attempts` e daria ao
    atacante mais 5 tentativas contra um código de 6 dígitos. Nem com carência 0."""
    _client, TestSession = api
    pid = _participant(TestSession)
    _challenge(TestSession, pid, expires_in_min=5, attempts=4)   # vivo, quase sem tentativas
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=0) == 0
        s.commit()
    with TestSession() as s:
        ch = s.scalars(select(OtpChallenge)).one()
        assert ch.attempts == 4        # contador preservado


def test_purge_e_idempotente(api):
    _client, TestSession = api
    pid = _participant(TestSession)
    _challenge(TestSession, pid, expires_in_min=-120)
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=0) == 1
        s.commit()
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=0) == 0    # nada sobrou
        s.commit()


def test_purge_apaga_consumido_ja_expirado(api):
    _client, TestSession = api
    pid = _participant(TestSession)
    _challenge(TestSession, pid, expires_in_min=-120, consumed=True)
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=0) == 1
        s.commit()


def test_purge_audita_so_a_contagem_sem_pii(api):
    _client, TestSession = api
    pid = _participant(TestSession)
    _challenge(TestSession, pid, expires_in_min=-120)
    _challenge(TestSession, pid, expires_in_min=-200)
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=0) == 2
        s.commit()
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "otp.purged")).one()
        assert ev.actor_type == "system" and ev.actor_id is None
        assert ev.meta["deleted"] == 2
        # Nada que ligue o evento a uma pessoa: sem participante e sem hash de código.
        assert ev.resource_id is None
        assert "participant_id" not in ev.meta and "code_hash" not in ev.meta
        assert str(pid) not in str(ev.meta)


def test_purge_vazio_nao_audita(api):
    # Um job diário que não achou nada não deve poluir a trilha (append-only, 5 anos).
    _client, TestSession = api
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=0) == 0
        s.commit()
    assert _count(TestSession, AuditLog) == 0


def test_purge_nao_toca_no_participante(api):
    _client, TestSession = api
    pid = _participant(TestSession)
    _challenge(TestSession, pid, expires_in_min=-120)
    with TestSession() as s:
        purge_expired_otp(s, grace_min=0)
        s.commit()
    assert _count(TestSession, Participant) == 1     # só o transitório sai


def test_login_continua_funcionando_apos_expurgo(api):
    """O expurgo não pode alterar o fluxo do titular: o desafio vivo sobrevive e vale."""
    client, TestSession = api
    pid = _participant(TestSession, "P-LOGIN")
    _challenge(TestSession, pid, expires_in_min=-120)               # lixo, some
    _challenge(TestSession, pid, expires_in_min=5, code="654321")   # vivo, fica
    with TestSession() as s:
        assert purge_expired_otp(s, grace_min=0) == 1
        s.commit()
    r = client.post(VERIFY, json={"study_code": "P-LOGIN", "code": "654321"})
    assert r.status_code == 200 and "access_token" in r.json()


def test_codigo_expirado_segue_recusado_apos_expurgo(api):
    """Antes o expirado dava 401 por `expires_at`; agora a linha nem existe. A resposta ao
    titular tem de ser a MESMA — senão o expurgo vira oráculo de existência."""
    client, TestSession = api
    pid = _participant(TestSession, "P-EXP")
    _challenge(TestSession, pid, expires_in_min=-120, code="111111")
    antes = client.post(VERIFY, json={"study_code": "P-EXP", "code": "111111"})
    with TestSession() as s:
        purge_expired_otp(s, grace_min=0)
        s.commit()
    depois = client.post(VERIFY, json={"study_code": "P-EXP", "code": "111111"})
    assert antes.status_code == depois.status_code == 401
    assert antes.json()["title"] == depois.json()["title"]
    assert antes.json()["detail"] == depois.json()["detail"]
