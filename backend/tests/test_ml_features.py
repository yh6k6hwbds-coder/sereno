"""
tests/test_ml_features.py — Dataset OFFLINE de features p/ ML (E4/ADR-083).

Prova o "Pronto (DoD)":
  (1) staff com export:request baixa um CSV; participante/anônimo não (403/401);
  (2) uma linha por recomendação — inclusive no_recommendation (guardrail) e recomendações
      sem sessão vinculada (telemetria em branco);
  (3) quando há sessão + pós-sessão vinculadas, a telemetria entra na linha;
  (4) pseudonimizado (study_code, sem PII) e CEGO: só braço CODIFICADO (Grupo A/B), NUNCA
      ativo/sham/condição; protocolo_sugerido é handle neutro de banda;
  (5) o export é auditado sem PII/braço (só nº de linhas);
  (6) OFFLINE: o endpoint apenas consolida — não cria recomendação nem decide.
"""
from __future__ import annotations
import csv
import io
import hashlib

from sqlalchemy import select

from app.core.models import (Participant, Allocation, AudioProtocol, StaffUser, AuditLog,
                             RecommendationLog)
from app.core import auth

FEATURES = "/v1/research/ml-features"
REC = "/v1/recommendations"
SESS = "/v1/sessions"
FORBIDDEN = ("active", "sham", "condition", "ativo", "beat_hz")


def _staff(TestSession, role="researcher", email=None):
    email = email or f"{role}@uninta.edu.br"
    with TestSession() as s:
        u = StaffUser(email=email, password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _participant(TestSession, code, arm=None):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        if arm is not None:
            s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="t"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _seed_library(TestSession):
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="ax-1", version="1.0.0", band="alpha", carrier_hz=200,
                            beat_hz=10, duration_s=2, target_peak_dbfs=-12.0,
                            content_hash=hashlib.sha256(b"a-active").hexdigest()))
        s.add(AudioProtocol(protocol_id="ax-2", version="1.0.0", band="alpha", carrier_hz=200,
                            beat_hz=0, duration_s=2, target_peak_dbfs=-12.0,
                            content_hash=hashlib.sha256(b"a-sham").hexdigest()))
        s.commit()


def _rows(csv_text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_participant_and_anon_denied(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-DENY", arm="A")
    assert client.get(FEATURES, headers=hdr).status_code == 403     # participante
    assert client.get(FEATURES).status_code == 401                  # sem token


def test_one_row_per_recommendation_incl_no_recommendation(api):
    client, TestSession = api
    # Participante contraindicado (triagem inelegível) → recomendação vira no_recommendation.
    from app.core.models import Screening
    _pid, hdr = _participant(TestSession, "P-CI", arm="A")
    with TestSession() as s:
        pid = s.scalars(select(Participant).where(Participant.study_code == "P-CI")).one().id
        s.add(Screening(participant_id=pid, eligible=False, criteria={"version": "1.0.0"}))
        s.commit()
    r_ci = client.post(REC, headers=hdr, json={"goal": "anxiety"})
    assert r_ci.status_code == 201

    # Um participante elegível com 2 recomendações (sem sessão vinculada).
    _p2, hdr2 = _participant(TestSession, "P-OK", arm="B")
    client.post(REC, headers=hdr2, json={"goal": "anxiety"})
    client.post(REC, headers=hdr2, json={"goal": "sleep", "sleep_issue": "onset"})

    staff = _staff(TestSession)
    resp = client.get(FEATURES, headers=staff)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = _rows(resp.text)
    assert len(rows) == 3                                    # 1 (CI) + 2 (OK)
    ci = next(r for r in rows if r["codigo"] == "P-CI")
    assert ci["acao"] == "no_recommendation" and ci["protocolo_sugerido"] == ""
    ok = [r for r in rows if r["codigo"] == "P-OK"]
    assert {r["rec_index"] for r in ok} == {"1", "2"}       # ordinal por participante
    assert all(r["sessao_completa"] == "" for r in ok)      # sem sessão vinculada → em branco


def test_linked_session_telemetry_present(api):
    client, TestSession = api
    _seed_library(TestSession)
    _pid, hdr = _participant(TestSession, "P-LINK", arm="A")
    rid = client.post(REC, headers=hdr, json={"goal": "anxiety"}).json()["id"]
    client.post(f"{REC}/{rid}/accept", headers=hdr, json={"accepted": True})
    sid = client.post(SESS, headers=hdr, json={
        "protocol_handle": "alpha", "headphones_ok": True, "recommendation_id": rid}).json()["session_id"]
    client.post(f"{SESS}/{sid}/complete", headers=hdr, json={"effective_seconds": 1000, "interruptions": 1})
    client.post(f"{SESS}/{sid}/survey", headers=hdr, json={
        "feeling": 3, "relaxation": 4, "liked": 3, "intensity": 2, "would_repeat": True})

    staff = _staff(TestSession)
    row = next(r for r in _rows(client.get(FEATURES, headers=staff).text) if r["codigo"] == "P-LINK")
    assert row["aceita"] == "sim"
    assert row["sessao_completa"] == "sim" and row["segundos_efetivos"] == "1000"
    assert row["interrupcoes"] == "1"
    assert row["relaxamento"] == "4" and row["repetiria"] == "sim"


def test_blind_and_no_pii(api):
    client, TestSession = api
    _pa, ha = _participant(TestSession, "P-ARM-A", arm="A")   # A
    _pb, hb = _participant(TestSession, "P-ARM-B", arm="B")   # B
    client.post(REC, headers=ha, json={"goal": "anxiety"})
    client.post(REC, headers=hb, json={"goal": "sleep", "sleep_issue": "onset"})

    staff = _staff(TestSession)
    text = client.get(FEATURES, headers=staff).text
    low = text.lower()
    # Cego: só braço codificado, nunca a condição.
    assert "grupo a" in low and "grupo b" in low
    assert not any(tok in low for tok in FORBIDDEN)
    # protocolo_sugerido é handle NEUTRO de banda (alpha/theta), não revela braço.
    rows = _rows(text)
    assert any(r["protocolo_sugerido"].startswith(("alpha", "theta", "delta")) for r in rows)


def test_export_is_audited_without_pii(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AUD", arm="A")
    client.post(REC, headers=hdr, json={"goal": "anxiety"})
    staff = _staff(TestSession)
    client.get(FEATURES, headers=staff)
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "features.exported")).one()
        assert ev.resource_type == "ml_feature_dataset" and ev.meta == {"rows": 1}
        assert "P-AUD" not in f"{ev.meta}"                   # sem código no log
        assert not any(tok in f"{ev.meta}".lower() for tok in FORBIDDEN)


def test_offline_does_not_create_recommendations(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-OFF", arm="A")
    client.post(REC, headers=hdr, json={"goal": "anxiety"})
    staff = _staff(TestSession)
    with TestSession() as s:
        before = s.scalar(select(__import__("sqlalchemy").func.count()).select_from(RecommendationLog))
    client.get(FEATURES, headers=staff)
    client.get(FEATURES, headers=staff)                      # duas leituras
    with TestSession() as s:
        after = s.scalar(select(__import__("sqlalchemy").func.count()).select_from(RecommendationLog))
    assert before == after == 1                              # consolidar não cria nada


def test_unallocated_participant_marked(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-NOALLOC", arm=None)   # sem alocação
    client.post(REC, headers=hdr, json={"goal": "anxiety"})
    staff = _staff(TestSession)
    row = next(r for r in _rows(client.get(FEATURES, headers=staff).text) if r["codigo"] == "P-NOALLOC")
    assert row["grupo_codificado"] == "nao_alocado"
