"""
tests/test_followup.py — Seguimento (PSQI+GAD-7+SUS+cegamento), ponta a ponta.

Cobre: escores corretos (contra o módulo validado), persistência do BRUTO, o
palpite de cegamento gravado COMO PALPITE (nunca o braço real), duplicidade (409),
validação de SUS/faixas (422) e ausência de token (401).
"""
from __future__ import annotations
from sqlalchemy import select
from app.core.models import Participant, Allocation, FollowupAssessment
from app.core import auth

URL = "/v1/participants/me/followup"

PSQI_OK = {"subjective_quality": 1, "latency_min": 20, "cannot_sleep_30min_freq": 1,
           "hours_slept": 6.0, "hours_in_bed": 8.0,
           "disturbance_items": [1, 1, 1, 1, 1, 1, 1, 0, 1],
           "medication_freq": 0, "stay_awake_freq": 1, "enthusiasm_problem": 1}
GAD7_OK = [2, 3, 1, 2, 0, 1, 3]                 # 12 / moderada
SUS_OK = [4, 1, 4, 2, 5, 1, 4, 2, 5, 1]         # 87.5 / excelente


def _participant(TestSession, code, arm="A"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def test_followup_scores_and_persists_raw(api):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-F1")
    r = client.post(URL, headers=hdr, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK,
                                            "sus_items": SUS_OK, "blinding_guess": "nao_sei"})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["gad7_total"] == 12 and b["gad7_severity"] == "moderada"
    assert b["psqi_global"] == 6 and b["psqi_interpretation"] == "sono ruim"
    assert b["sus_score"] == 87.5 and b["sus_band"] == "excelente"
    assert b["score_version"] == "gad7:1.0.0|psqi:1.0.0|sus:1.0.0"
    with TestSession() as s:
        rec = s.scalars(select(FollowupAssessment).where(FollowupAssessment.participant_id == pid)).one()
        assert rec.gad7_items == GAD7_OK and rec.sus_items == SUS_OK        # bruto
        assert float(rec.sus_score) == 87.5                                # Numeric, não truncado


def test_blinding_guess_is_stored_as_guess_not_real_arm(api):
    client, TestSession = api
    # participante ALOCADO em A, mas PALPITA "B"
    pid, hdr = _participant(TestSession, "P-BLIND", arm="A")
    r = client.post(URL, headers=hdr, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK,
                                            "sus_items": SUS_OK, "blinding_guess": "B"})
    assert r.status_code == 201
    assert r.json()["blinding_guess"] == "B"        # o que ele ACHA
    with TestSession() as s:
        rec = s.scalars(select(FollowupAssessment).where(FollowupAssessment.participant_id == pid)).one()
        alloc = s.scalars(select(Allocation).where(Allocation.participant_id == pid)).one()
        assert rec.blinding_guess == "B"            # palpite gravado
        assert alloc.arm_coded == "A"               # braço real intacto e separado
        assert rec.blinding_guess != alloc.arm_coded  # palpite ≠ verdade — cegamento preservado


def test_duplicate_followup_409(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-F2")
    payload = {"gad7_items": GAD7_OK, "psqi": PSQI_OK, "sus_items": SUS_OK, "blinding_guess": "A"}
    assert client.post(URL, headers=hdr, json=payload).status_code == 201
    assert client.post(URL, headers=hdr, json=payload).status_code == 409


def test_sus_wrong_length_422(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-F3")
    r = client.post(URL, headers=hdr, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK,
                                            "sus_items": [4, 1, 4], "blinding_guess": "A"})
    assert r.status_code == 422


def test_sus_out_of_range_422(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-F4")
    bad = [6, 1, 4, 2, 5, 1, 4, 2, 5, 1]            # 6 fora de 1–5
    r = client.post(URL, headers=hdr, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK,
                                            "sus_items": bad, "blinding_guess": "A"})
    assert r.status_code == 422


def test_invalid_blinding_guess_422(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-F5")
    r = client.post(URL, headers=hdr, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK,
                                            "sus_items": SUS_OK, "blinding_guess": "talvez"})
    assert r.status_code == 422


def test_no_token_401(api):
    client, _ = api
    r = client.post(URL, json={"gad7_items": GAD7_OK, "psqi": PSQI_OK, "sus_items": SUS_OK, "blinding_guess": "A"})
    assert r.status_code == 401
