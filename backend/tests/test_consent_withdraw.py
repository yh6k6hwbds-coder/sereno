"""
tests/test_consent_withdraw.py — Retirada de consentimento self-service (B3/ADR-089).

Prova o "Pronto (DoD)":
  (1) o próprio titular retira o consentimento → 200, marca `revoked_at` no consentimento
      ativo e muda o status para `withdrawn`;
  (2) enforcement: após retirar, iniciar sessão é recusado (403) — a retirada tem efeito;
  (3) idempotência por estado: retirar de novo → 409;
  (4) auditado sem PII (só o fato + nº de consentimentos revogados);
  (5) não elimina o dado de pesquisa já coletado (retenção pseudonimizada; eliminação é
      direito separado) — o participante segue existindo, só `withdrawn`;
  (6) negações: staff não usa a rota do titular (403); sem token (401).
"""
from __future__ import annotations
import datetime as dt
import hashlib

from sqlalchemy import select

from app.core.models import Participant, Allocation, ConsentRecord, AuditLog, StaffUser
from app.core import auth

WITHDRAW = "/v1/participants/me/consent/withdraw"
CONSENT = "/v1/participants/me/consent"
SESS = "/v1/sessions"


def _participant(TestSession, code="P-W", allocated=False):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        if allocated:
            s.add(Allocation(participant_id=p.id, arm_coded="A", block=1, sequence_seed_ref="t"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _consent(client, hdr):
    r = client.post(CONSENT, headers=hdr, json={"tcle_version": "1.0.0", "accepted": True})
    assert r.status_code == 201


def test_withdraw_marks_revoked_and_withdrawn(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession)
    _consent(client, hdr)
    r = client.post(WITHDRAW, headers=hdr)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "withdrawn" and body["revoked_consents"] == 1
    with TestSession() as s:
        assert s.get(Participant, pid).status == "withdrawn"
        rec = s.scalars(select(ConsentRecord).where(ConsentRecord.participant_id == pid)).one()
        assert rec.revoked_at is not None                    # consentimento carimbado


def test_withdraw_blocks_new_sessions(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, code="P-W-SESS", allocated=True)
    _consent(client, hdr)
    # Antes: alocado + consentido → o start passaria da checagem de consentimento.
    client.post(WITHDRAW, headers=hdr)
    r = client.post(SESS, headers=hdr, json={"protocol_handle": "alpha", "headphones_ok": True})
    assert r.status_code == 403
    assert "consentimento" in r.text.lower()


def test_withdraw_twice_conflicts_409(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, code="P-W2")
    _consent(client, hdr)
    assert client.post(WITHDRAW, headers=hdr).status_code == 200
    assert client.post(WITHDRAW, headers=hdr).status_code == 409


def test_withdraw_is_audited_without_pii(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, code="P-W-AUD")
    _consent(client, hdr)
    client.post(WITHDRAW, headers=hdr)
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "consent.withdrawn")).one()
        assert ev.resource_type == "participant" and ev.actor_id == pid
        assert ev.meta == {"revoked_consents": 1}
        assert "P-W-AUD" not in f"{ev.meta}"                 # sem código/PII no log


def test_withdraw_retains_participant_record(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, code="P-W-RET")
    _consent(client, hdr)
    client.post(WITHDRAW, headers=hdr)
    with TestSession() as s:
        # Retirada NÃO elimina o registro de pesquisa — só encerra a participação.
        assert s.get(Participant, pid) is not None
        assert s.scalars(select(ConsentRecord).where(ConsentRecord.participant_id == pid)).all()


def test_withdraw_without_prior_consent_still_withdraws(api):
    # Sem consentimento aceito antes: revoga 0 registros, mas encerra a participação.
    client, TestSession = api
    _pid, hdr = _participant(TestSession, code="P-W-NONE")
    r = client.post(WITHDRAW, headers=hdr)
    assert r.status_code == 200 and r.json()["revoked_consents"] == 0


def test_staff_cannot_use_titular_route_403(api):
    client, TestSession = api
    with TestSession() as s:
        u = StaffUser(email="r@uninta.edu.br", password_hash=auth.hash_password("Senha-Forte-123"),
                      role="researcher", mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(uid), 'researcher')}"}
    assert client.post(WITHDRAW, headers=hdr).status_code == 403


def test_no_token_401(api):
    client, _ = api
    assert client.post(WITHDRAW).status_code == 401
