"""
tests/test_analysis.py — Relatório de análise + critérios de progressão (fatia C7).

Prova o "Pronto (DoD)":
  - relatório reprodutível e CEGO (por braço codificado A/B), sem PII nem condição;
  - índice de Bang calculado a partir do `blinding_guess` (detecta desblindagem);
  - semáforo de progressão determinístico a partir de limiares pré-especificados;
  - nada decide eficácia ao vivo (é relatório). RBAC `research:read` (403 participante, 401 sem token).
"""
from __future__ import annotations
import datetime as dt
import uuid

from app.core.models import (Participant, StaffUser, Allocation, BaselineAssessment,
                             FollowupAssessment, Session as SessionModel, AdverseEvent)
from app.core import auth
from app.modules.research.analysis_plan import progression_semaphore

URL = "/v1/research/analysis"


def _researcher(TestSession):
    with TestSession() as s:
        u = StaffUser(email="pesq@uninta.edu.br", password_hash=auth.hash_password("Senha-Forte-123"),
                      role="researcher", mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), 'researcher')}"}


def _seed_complete(TestSession, code, arm, *, gad_base=14, gad_fu=8, psqi_base=10, psqi_fu=5,
                   sus=80, guess="nao_sei", completed=14):
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
        s.commit()


# ---------- semáforo (unidade, sem DB) ----------
def test_progression_semaphore_lights():
    assert progression_semaphore(75, 85, 0, True)["overall"] == "verde"
    amber = progression_semaphore(55, 85, 0, True)               # adesão amarela
    assert amber["criteria"]["adesao"] == "amarelo" and amber["overall"] == "amarelo"
    red = progression_semaphore(75, 85, 1, True)                 # EA grave → vermelho
    assert red["criteria"]["seguranca"] == "vermelho" and red["overall"] == "vermelho"
    unblind = progression_semaphore(75, 85, 0, False)            # cegamento não mantido
    assert unblind["criteria"]["cegamento"] == "amarelo"
    assert progression_semaphore(None, None, 0, True)["criteria"]["adesao"] == "indeterminado"


# ---------- relatório (integração) ----------
def test_report_structure_and_no_condition_leak(api):
    client, TestSession = api
    hdr = _researcher(TestSession)
    for i in range(4):
        _seed_complete(TestSession, f"A{i}", "A", guess="nao_sei")
        _seed_complete(TestSession, f"B{i}", "B", guess="nao_sei")
    r = client.get(URL, headers=hdr)
    assert r.status_code == 200
    rep = r.json()
    assert {"framing", "enrollment", "feasibility", "blinding", "exploratory", "progression"} <= set(rep)
    assert rep["enrollment"]["complete_cases"] == 8
    # todos "não sei" → Bang ≈ 0, cegamento mantido
    assert rep["blinding"]["maintained"] is True
    assert abs(rep["blinding"]["bang_index"]["grupo_a"]["bang_bi"]) < 0.2
    # exploratórios presentes (n≥3 por braço)
    assert rep["exploratory"]["gad7_entre_bracos"] is not None
    # nunca a condição (ativo/sham) nem PII
    assert not any(tok in str(rep).lower() for tok in ("active", "sham", "ativo", "@"))


def test_report_bang_detects_unblinding(api):
    client, TestSession = api
    hdr = _researcher(TestSession)
    for i in range(4):
        _seed_complete(TestSession, f"A{i}", "A", guess="A")   # todos acertam o próprio braço
        _seed_complete(TestSession, f"B{i}", "B", guess="B")
    rep = client.get(URL, headers=hdr).json()
    assert rep["blinding"]["bang_index"]["grupo_a"]["bang_bi"] == 1.0
    assert rep["blinding"]["maintained"] is False
    assert rep["progression"]["criteria"]["cegamento"] == "amarelo"


def test_report_empty_is_safe(api):
    client, TestSession = api
    hdr = _researcher(TestSession)
    rep = client.get(URL, headers=hdr).json()
    assert rep["enrollment"]["allocated"] == 0 and rep["enrollment"]["complete_cases"] == 0
    assert rep["blinding"]["maintained"] is True          # sem respondentes → nada a refutar


def test_analysis_participant_forbidden_403(api):
    client, TestSession = api
    with TestSession() as s:
        p = Participant(study_code="P-X"); s.add(p); s.commit(); pid = p.id
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    assert client.get(URL, headers=hdr).status_code == 403


def test_analysis_no_token_401(api):
    client, _ = api
    assert client.get(URL).status_code == 401
