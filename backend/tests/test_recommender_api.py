"""
tests/test_recommender_api.py — Recomendador POR REGRAS ao vivo (E1/ADR-068).

Cobre: recomendação por objetivo (ansiedade→alfa; sono/adormecer→teta), guardrails
resolvidos NO SERVIDOR (evento adverso recente → de-escalona + revisão; triagem inelegível →
no_recommendation), registro em recommendation_log (regra/versão/feature_vector), não
vazamento do braço (mesma forma e mesmo handle em braços opostos) e negações (401/403/422).
"""
from __future__ import annotations
import datetime as dt
import uuid

from sqlalchemy import select
from app.core.models import Participant, Allocation, AdverseEvent, Screening, RecommendationLog
from app.core import auth

URL = "/v1/recommendations"
FORBIDDEN = ("active", "sham", "beat", "arm", "condition", "ativo")   # termos que revelariam o braço


def _participant(TestSession, code, arm=None):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        if arm:
            s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="t"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def test_anxiety_recommends_alpha_and_logs(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-ANX")
    r = client.post(URL, headers=hdr, json={"goal": "anxiety"})
    assert r.status_code == 201
    b = r.json()
    assert b["action"] == "recommend" and b["suggested_protocol"] == "alpha-10"
    assert b["band"] == "alpha" and b["rule_id"] == "R1-anxiety"
    assert b["disclaimer"] and b["evidence_note"]        # postura científica sempre presente
    # Registrado com versão do conjunto de regras e feature_vector p/ ML futuro.
    with TestSession() as s:
        row = s.scalars(select(RecommendationLog).where(RecommendationLog.participant_id == pid)).one()
        assert row.suggested_protocol == "alpha-10" and row.rule_version
        assert "feature_vector" in row.inputs and "snapshot" in row.inputs


def test_sleep_onset_recommends_theta(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-SLEEP")
    r = client.post(URL, headers=hdr, json={"goal": "sleep", "sleep_issue": "onset"})
    assert r.status_code == 201 and r.json()["suggested_protocol"] == "theta-6"


def test_recent_adverse_event_deescalates_server_side(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-AE")
    with TestSession() as s:
        s.add(AdverseEvent(participant_id=pid, type="headache", severity="moderate",
                           occurred_at=dt.datetime.now(dt.timezone.utc)))
        s.commit()
    # Sono/adormecer normalmente iria para teta; o guardrail de segurança de-escalona p/ o mais brando.
    r = client.post(URL, headers=hdr, json={"goal": "sleep", "sleep_issue": "onset"})
    assert r.status_code == 201
    b = r.json()
    assert b["rule_id"] == "G2-safety-deescalate"
    assert b["suggested_protocol"] == "alpha-10" and b["flag_review"] is True


def test_contraindicated_screening_yields_no_recommendation(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-CI")
    with TestSession() as s:
        s.add(Screening(participant_id=pid, eligible=False, criteria={"version": "x"}))
        s.commit()
    r = client.post(URL, headers=hdr, json={"goal": "anxiety"})
    assert r.status_code == 201
    b = r.json()
    assert b["action"] == "no_recommendation" and b["suggested_protocol"] is None
    # O evento de segurança é registrado fielmente com protocolo NULL.
    with TestSession() as s:
        row = s.scalars(select(RecommendationLog).where(RecommendationLog.participant_id == pid)).one()
        assert row.suggested_protocol is None and row.rule_id == "G1-contraindication"


def test_arm_never_leaks_same_shape_both_arms(api):
    client, TestSession = api
    _pa, ha = _participant(TestSession, "P-ARM-A", arm="A")   # braços opostos
    _pb, hb = _participant(TestSession, "P-ARM-B", arm="B")
    ra = client.post(URL, headers=ha, json={"goal": "anxiety"})
    rb = client.post(URL, headers=hb, json={"goal": "anxiety"})
    assert ra.status_code == 201 and rb.status_code == 201
    a, b = ra.json(), rb.json()
    assert set(a.keys()) == set(b.keys())                     # mesma forma
    assert a["suggested_protocol"] == b["suggested_protocol"] # handle neutro, independe do braço
    for body in (a, b):
        assert not any(tok in str(body).lower() for tok in FORBIDDEN)


def test_no_token_401(api):
    client, TestSession = api
    r = client.post(URL, json={"goal": "anxiety"})
    assert r.status_code == 401


def test_staff_forbidden_403(api):
    client, _TestSession = api
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(uuid.uuid4()), 'admin')}"}
    r = client.post(URL, headers=hdr, json={"goal": "anxiety"})
    assert r.status_code == 403                               # staff não tem recommend:read


def test_invalid_goal_422(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-422")
    r = client.post(URL, headers=hdr, json={"goal": "focus"})
    assert r.status_code == 422
