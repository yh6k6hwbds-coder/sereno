"""
tests/test_baseline.py — Fatia de linha de base (PSQI + GAD-7), ponta a ponta.

Cobre: escore correto (contra o módulo validado), persistência do BRUTO + escore
versionado, validação (422), regra de domínio (dormir > tempo na cama), duplicidade
(409) e ausência de token (401). Autenticação real (token de participante).
"""
from __future__ import annotations
from sqlalchemy import select
from app.core.models import Participant, BaselineAssessment
from app.core import auth

URL = "/v1/participants/me/baseline"

PSQI_OK = {
    "subjective_quality": 1, "latency_min": 20, "cannot_sleep_30min_freq": 1,
    "hours_slept": 6.0, "hours_in_bed": 8.0,
    "disturbance_items": [1, 1, 1, 1, 1, 1, 1, 0, 1],
    "medication_freq": 0, "stay_awake_freq": 1, "enthusiasm_problem": 1,
}
GAD7_OK = [2, 3, 1, 2, 0, 1, 3]   # total 12 → moderada


def _seed(TestSession):
    with TestSession() as s:
        p = Participant(study_code="P-BASE")
        s.add(p); s.commit()
        pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def test_baseline_ok_scores_and_persists(api):
    client, TestSession = api
    pid, hdr = _seed(TestSession)
    r = client.post(URL, headers=hdr, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["gad7_total"] == 12 and body["gad7_severity"] == "moderada"
    assert body["psqi_global"] == 6 and body["psqi_interpretation"] == "sono ruim"
    assert body["score_version"] == "gad7:1.0.0|psqi:1.0.0"
    # persistiu bruto + escore?
    with TestSession() as s:
        rec = s.scalars(select(BaselineAssessment).where(BaselineAssessment.participant_id == pid)).one()
        assert rec.gad7_total == 12 and rec.psqi_global == 6
        assert rec.gad7_items == GAD7_OK                     # bruto
        assert rec.psqi_input["hours_slept"] == 6.0          # bruto (JSON)


def test_gad7_wrong_length_422(api):
    client, TestSession = api
    _pid, hdr = _seed(TestSession)
    r = client.post(URL, headers=hdr, json={"gad7_items": [1, 2, 3], "psqi": PSQI_OK})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")


def test_gad7_out_of_range_422(api):
    client, TestSession = api
    _pid, hdr = _seed(TestSession)
    bad = [4, 0, 0, 0, 0, 0, 0]                              # 4 está fora de 0–3
    r = client.post(URL, headers=hdr, json={"gad7_items": bad, "psqi": PSQI_OK})
    assert r.status_code == 422


def test_psqi_domain_inconsistency_422(api):
    client, TestSession = api
    _pid, hdr = _seed(TestSession)
    bad_psqi = {**PSQI_OK, "hours_slept": 9.0, "hours_in_bed": 8.0}   # dormiu > na cama
    r = client.post(URL, headers=hdr, json={"gad7_items": GAD7_OK, "psqi": bad_psqi})
    assert r.status_code == 422 and "hours_slept" in r.json()["detail"]


def test_duplicate_baseline_409(api):
    client, TestSession = api
    _pid, hdr = _seed(TestSession)
    payload = {"gad7_items": GAD7_OK, "psqi": PSQI_OK}
    assert client.post(URL, headers=hdr, json=payload).status_code == 201
    r2 = client.post(URL, headers=hdr, json=payload)
    assert r2.status_code == 409


def test_no_token_401(api):
    client, _ = api
    r = client.post(URL, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK})
    assert r.status_code == 401
