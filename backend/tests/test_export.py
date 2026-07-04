"""
tests/test_export.py — Exportação pseudonimizada assíncrona (fatia C6).

Prova o "Pronto (DoD)":
  - o CSV exportado NÃO contém PII nem a condição (ativo/sham) — só o braço CODIFICADO A/B;
  - casos incompletos (sem baseline+seguimento) ficam de fora;
  - o pedido de exportação é registrado em auditoria (sem PII/condição);
  - fluxo de job: POST → 202 {job_id}; GET → CSV quando concluído; GET inexistente → 404.
Negações: 401 (sem token), 403 (papel sem `export:request`).
"""
from __future__ import annotations
import datetime as dt
import uuid

from sqlalchemy import select

from app.core.models import (Participant, StaffUser, Allocation, BaselineAssessment,
                             FollowupAssessment, Session as SessionModel, AdverseEvent, AuditLog)
from app.core import auth

EXPORT = "/v1/research/export"
FORBIDDEN = ("active", "sham", "ativo", "secret", "@")


def _researcher(TestSession):
    with TestSession() as s:
        u = StaffUser(email="pesq@uninta.edu.br", password_hash=auth.hash_password("Senha-Forte-123"),
                      role="researcher", mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), 'researcher')}"}


def _seed_complete(TestSession, code, arm, *, gad_base=14, gad_fu=8, psqi_base=10, psqi_fu=5,
                   sus=80, guess="A", completed=14, aes=1):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush(); pid = p.id
        s.add(Allocation(participant_id=pid, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.add(BaselineAssessment(participant_id=pid, gad7_items={}, gad7_total=gad_base,
                                 psqi_input={}, psqi_global=psqi_base, score_version="1.0.0"))
        s.add(FollowupAssessment(participant_id=pid, gad7_items={}, gad7_total=gad_fu,
                                 psqi_input={}, psqi_global=psqi_fu, sus_items={}, sus_score=sus,
                                 blinding_guess=guess, score_version="1.0.0"))
        for _ in range(completed):
            s.add(SessionModel(participant_id=pid, protocol_uuid=uuid.uuid4(), protocol_hash="0" * 64,
                               headphones_ok=True, completed=True))
        for _ in range(aes):
            s.add(AdverseEvent(participant_id=pid, type="headache", severity="mild",
                               occurred_at=dt.datetime.now(dt.timezone.utc)))
        s.commit()
    return pid


def _seed_incomplete(TestSession, code, arm):
    """Alocado mas SEM seguimento — deve ficar de fora do export de casos completos."""
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush(); pid = p.id
        s.add(Allocation(participant_id=pid, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.add(BaselineAssessment(participant_id=pid, gad7_items={}, gad7_total=12,
                                 psqi_input={}, psqi_global=9, score_version="1.0.0"))
        s.commit()
    return pid


def _download(client, hdr):
    r = client.post(EXPORT, headers=hdr)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    g = client.get(f"{EXPORT}/{job_id}", headers=hdr)
    return job_id, g


def test_export_has_coded_arm_no_pii_no_condition(api):
    client, TestSession = api
    hdr = _researcher(TestSession)
    _seed_complete(TestSession, "P001", "A", guess="A")
    _seed_complete(TestSession, "P002", "B", guess="nao_sei")
    _seed_incomplete(TestSession, "P003", "A")     # excluído

    _job_id, g = _download(client, hdr)
    assert g.status_code == 200
    assert g.headers["content-type"].startswith("text/csv")
    csv = g.text
    # braço CODIFICADO presente (necessário à análise cega)
    assert "Grupo A" in csv and "Grupo B" in csv
    # pseudônimos dos casos completos presentes; incompleto ausente
    assert "P001" in csv and "P002" in csv and "P003" not in csv
    # NUNCA a condição (ativo/sham) nem PII (e-mail)
    assert not any(tok in csv.lower() for tok in FORBIDDEN)


def test_export_is_audited(api):
    client, TestSession = api
    hdr = _researcher(TestSession)
    _seed_complete(TestSession, "P010", "A")
    job_id, _g = _download(client, hdr)
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "export.requested")).one()
        assert ev.resource_type == "research_export" and str(ev.resource_id) == job_id
        assert not any(tok in f"{ev.meta}".lower() for tok in ("active", "sham", "ativo"))


def test_get_unknown_job_404(api):
    client, TestSession = api
    hdr = _researcher(TestSession)
    r = client.get(f"{EXPORT}/{uuid.uuid4()}", headers=hdr)
    assert r.status_code == 404


def test_export_requires_permission_403_for_participant(api):
    client, TestSession = api
    with TestSession() as s:
        p = Participant(study_code="P-X"); s.add(p); s.commit(); pid = p.id
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    assert client.post(EXPORT, headers=hdr).status_code == 403


def test_export_no_token_401(api):
    client, _ = api
    assert client.post(EXPORT).status_code == 401
