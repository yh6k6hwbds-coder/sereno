"""
tests/test_contact.py — Captura de contato com PII CIFRADA (fatia C4), ponta a ponta.

Prova o "Pronto (DoD)":
  - o que é gravado no banco é CIPHERTEXT (não texto claro) e a resposta não ecoa PII;
  - round-trip: decifra corretamente com a mesma chave + AAD;
  - AAD liga o valor ao participante e ao campo (não dá para trocar campo nem mover de linha);
  - sem a chave certa não há leitura (InvalidTag);
  - upsert por participante; captura auditada SEM PII (reusa a trilha C1).
Cobre as negações: 401 (sem token), 403 (participante), 404 (inexistente), 422 (e-mail inválido).
"""
from __future__ import annotations
import base64
import uuid

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from app.core.models import Participant, StaffUser, ContactInfo, AuditLog
from app.core import auth, pii_crypto

URL = "/v1/participants/{}/contact"
_KEY = base64.b64encode(b"k" * 32).decode()


@pytest.fixture(autouse=True)
def _pii_key(monkeypatch):
    monkeypatch.setenv("PII_ENC_KEY", _KEY)


def _staff(TestSession, role="researcher"):
    with TestSession() as s:
        u = StaffUser(email=f"{role}@uninta.edu.br",
                      password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _participant(TestSession, code="P-CT"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); pid = p.id
    return pid


def test_stores_ciphertext_and_roundtrips(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    pid = _participant(TestSession)
    r = client.post(URL.format(pid), headers=hdr,
                    json={"name": "Fulano de Tal", "email": "fulano@example.com"})
    assert r.status_code == 201 and r.json() == {"status": "stored"}
    assert "fulano" not in r.text.lower()          # resposta neutra, sem PII
    with TestSession() as s:
        rec = s.scalars(select(ContactInfo).where(ContactInfo.participant_id == pid)).one()
        # no banco: ciphertext (nunca o texto claro)
        assert b"Fulano" not in rec.enc_name and b"fulano" not in rec.enc_email
        assert len(rec.enc_name) > 12 and len(rec.enc_email) > 12
        assert pii_crypto.decrypt(rec.enc_name, aad=pii_crypto.aad_for(pid, "name")) == "Fulano de Tal"
        assert pii_crypto.decrypt(rec.enc_email, aad=pii_crypto.aad_for(pid, "email")) == "fulano@example.com"


def test_aad_binding_prevents_field_or_row_swap(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    pid = _participant(TestSession)
    client.post(URL.format(pid), headers=hdr, json={"name": "Nome X", "email": "x@example.com"})
    with TestSession() as s:
        enc_name = s.scalars(select(ContactInfo).where(ContactInfo.participant_id == pid)).one().enc_name
    with pytest.raises(InvalidTag):                 # trocar de campo (name→email) falha
        pii_crypto.decrypt(enc_name, aad=pii_crypto.aad_for(pid, "email"))
    with pytest.raises(InvalidTag):                 # mover para outra linha falha
        pii_crypto.decrypt(enc_name, aad=pii_crypto.aad_for(uuid.uuid4(), "name"))


def test_wrong_key_cannot_read(monkeypatch):
    aad = pii_crypto.aad_for(uuid.uuid4(), "name")
    monkeypatch.setenv("PII_ENC_KEY", base64.b64encode(b"a" * 32).decode())
    token = pii_crypto.encrypt("segredo", aad=aad)
    monkeypatch.setenv("PII_ENC_KEY", base64.b64encode(b"b" * 32).decode())
    with pytest.raises(InvalidTag):
        pii_crypto.decrypt(token, aad=aad)


def test_upsert_overwrites(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    pid = _participant(TestSession)
    client.post(URL.format(pid), headers=hdr, json={"name": "A", "email": "a@example.com"})
    r2 = client.post(URL.format(pid), headers=hdr, json={"name": "B", "email": "b@example.com"})
    assert r2.status_code == 201
    with TestSession() as s:
        rows = s.scalars(select(ContactInfo).where(ContactInfo.participant_id == pid)).all()
        assert len(rows) == 1                       # único por participante
        assert pii_crypto.decrypt(rows[0].enc_email, aad=pii_crypto.aad_for(pid, "email")) == "b@example.com"


def test_audit_event_without_pii(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    pid = _participant(TestSession)
    client.post(URL.format(pid), headers=hdr, json={"name": "Sigiloso", "email": "sig@example.com"})
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "contact.stored")).one()
        assert ev.resource_type == "contact_info" and ev.actor_type == "staff" and ev.resource_id == pid
        blob = f"{ev.action}{ev.meta}".lower()
        assert "sigiloso" not in blob and "sig@example" not in blob


def test_unknown_participant_404(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    r = client.post(URL.format("00000000-0000-0000-0000-000000000000"), headers=hdr,
                    json={"name": "X", "email": "x@example.com"})
    assert r.status_code == 404


def test_participant_token_forbidden_403(api):
    client, TestSession = api
    pid = _participant(TestSession)
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    r = client.post(URL.format(pid), headers=hdr, json={"name": "X", "email": "x@example.com"})
    assert r.status_code == 403


def test_no_token_401(api):
    client, TestSession = api
    pid = _participant(TestSession)
    r = client.post(URL.format(pid), json={"name": "X", "email": "x@example.com"})
    assert r.status_code == 401


def test_invalid_email_422(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    pid = _participant(TestSession)
    r = client.post(URL.format(pid), headers=hdr, json={"name": "X", "email": "naoehemail"})
    assert r.status_code == 422
