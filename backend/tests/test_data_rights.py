"""
tests/test_data_rights.py — Direitos do titular LGPD (fatia D4): acesso e eliminação.

Prova o "Pronto (DoD)":
  - eliminação remove a PII direta (contato, OTP) e marca 'withdrawn', RETENDO a pesquisa
    pseudonimizada e SEM apagar a auditoria (append-only preservado); é auditada;
  - exportação reúne os dados do titular (com a PII do próprio) e NUNCA inclui o braço/condição;
    é auditada.
Negações: 401 (sem token), 403 (não-admin), 404 (inexistente).
"""
from __future__ import annotations
import base64
import datetime as dt

import pytest
from sqlalchemy import func, select

from app.core.models import (Participant, StaffUser, ContactInfo, OtpChallenge,
                             BaselineAssessment, AuditLog)
from app.core import auth, pii_crypto
from app.modules.audit.service import record_event

DATA = "/v1/participants/{}/data"
ERASE = "/v1/participants/{}/erase"
_KEY = base64.b64encode(b"k" * 32).decode()


@pytest.fixture(autouse=True)
def _pii_key(monkeypatch):
    monkeypatch.setenv("PII_ENC_KEY", _KEY)


def _staff(TestSession, role, email=None):
    email = email or f"{role}@uninta.edu.br"
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _seed_full(TestSession, code="P-DR"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush(); pid = p.id
        s.add(ContactInfo(
            participant_id=pid,
            enc_name=pii_crypto.encrypt("Fulano", aad=pii_crypto.aad_for(pid, "name")),
            enc_email=pii_crypto.encrypt("f@example.com", aad=pii_crypto.aad_for(pid, "email"))))
        s.add(OtpChallenge(participant_id=pid, code_hash="0" * 64,
                           expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)))
        s.add(BaselineAssessment(participant_id=pid, gad7_items={}, gad7_total=10,
                                 psqi_input={}, psqi_global=6, score_version="1.0.0"))
        s.commit()
    return pid


def test_erase_removes_pii_keeps_research_and_audit(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _seed_full(TestSession)
    with TestSession() as s:                       # evento de auditoria pré-existente
        record_event(s, action="consent.recorded", resource_type="consent_record",
                     actor_type="participant", actor_id=pid, resource_id=pid)
        s.commit()

    r = client.post(ERASE.format(pid), headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "erased"
    assert body["removed"] == {"contact_info": 1, "otp_challenges": 1}

    with TestSession() as s:
        assert s.scalar(select(func.count()).select_from(ContactInfo)
                        .where(ContactInfo.participant_id == pid)) == 0
        assert s.scalar(select(func.count()).select_from(OtpChallenge)
                        .where(OtpChallenge.participant_id == pid)) == 0
        # pesquisa pseudonimizada RETIDA
        assert s.scalar(select(func.count()).select_from(BaselineAssessment)
                        .where(BaselineAssessment.participant_id == pid)) == 1
        assert s.get(Participant, pid).status == "withdrawn"
        # auditoria: evento pré-existente PRESERVADO + novo evento de eliminação
        actions = [e.action for e in s.scalars(select(AuditLog).where(AuditLog.resource_id == pid))]
        assert "consent.recorded" in actions and "participant.erased" in actions


def test_export_returns_subject_data_without_arm(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    pid = _seed_full(TestSession)
    r = client.get(DATA.format(pid), headers=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["profile"]["study_code"] == "P-DR" and d["profile"]["status"] == "active"
    assert d["contact"]["name"] == "Fulano" and d["contact"]["email"] == "f@example.com"
    assert len(d["baseline"]) == 1 and d["baseline"][0]["gad7_total"] == 10
    # NUNCA a condição nem o braço
    blob = str(d).lower()
    assert "active" not in str(d.get("baseline")).lower()  # (garantia extra local)
    assert "sham" not in blob and "arm" not in blob and "condition" not in blob
    with TestSession() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == "participant.data_exported")) is not None


def test_erase_requires_admin_403_for_researcher(api):
    client, TestSession = api
    hdr = _staff(TestSession, "researcher")
    pid = _seed_full(TestSession, "P-RES")
    assert client.post(ERASE.format(pid), headers=hdr).status_code == 403


def test_export_no_token_401(api):
    client, TestSession = api
    pid = _seed_full(TestSession, "P-NT")
    assert client.get(DATA.format(pid)).status_code == 401


def test_unknown_participant_404(api):
    client, TestSession = api
    admin = _staff(TestSession, "admin")
    assert client.post(ERASE.format("00000000-0000-0000-0000-000000000000"),
                       headers=admin).status_code == 404
