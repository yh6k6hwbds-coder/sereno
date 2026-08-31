"""
tests/test_screening.py — Triagem/elegibilidade + gate do funil de alocação (C2 e G8).

Prova o "Pronto (DoD)":
  - elegível ⇔ todas as inclusões verdadeiras E nenhuma exclusão presente (regra versionada);
  - as CHAVES são as do protocolo aprovado (G8): conjunto fechado, faltando/desconhecida = 422;
  - os critérios DERIVADOS (faixa sintomática e gatilho de risco) o servidor calcula dos
    escores — declará-los é 422, e uma triagem vazia é INELEGÍVEL, não elegível por vacuidade;
  - triagem registrada + auditada (sem PII); uma por participante (409 duplicado);
  - **bloqueio de alocação** antes de triagem, se inelegível, ou sem consentimento (409);
  - alocação liberada após o funil completo (triagem elegível + consentimento).
Cobre as negações: 401/403/404/409/422.
"""
from __future__ import annotations
import datetime as dt
from sqlalchemy import select

from app.core.models import Participant, StaffUser, Screening, ConsentRecord, Allocation, AuditLog
from app.core import auth
from app.modules.consent.router import TCLE_CURRENT   # versao vigente do termo (nao literal)
from app.modules.screening.service import CRITERIA_VERSION
from tests.helpers import (GAD7_ELEGIVEL, screening_body,
                           screening_criteria as _criterios)

SCREEN = "/v1/screening"
ALLOC = "/v1/allocation"


def _staff(TestSession, role="researcher"):
    with TestSession() as s:
        u = StaffUser(email=f"{role}@uninta.edu.br", password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _participant(TestSession, code="P-SC"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); return p.id


def _consent(TestSession, pid, accepted=True):
    with TestSession() as s:
        s.add(ConsentRecord(participant_id=pid, tcle_version=TCLE_CURRENT, accepted=accepted,
                            accepted_at=dt.datetime.now(dt.timezone.utc), content_hash="0" * 64))
        s.commit()


def _screen(client, hdr, pid, *, eligible=True):
    return client.post(SCREEN, headers=hdr, json=screening_body(pid, inclusao_ok=eligible))


# ---------- elegibilidade ----------
def test_eligible_all_inclusions_no_exclusion(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json=screening_body(pid))
    assert r.status_code == 201 and r.json() == {
        "status": "screened", "eligible": True, "risk_detected": False,
        "unmet_criteria": [], "referral_id": None}
    with TestSession() as s:
        sc = s.scalars(select(Screening).where(Screening.participant_id == pid)).one()
        assert sc.eligible is True and sc.criteria["version"] == CRITERIA_VERSION
        # O derivado entrou no registro sem ter sido declarado.
        assert sc.criteria["inclusion"]["sintomas_elegiveis"] is True
        assert sc.criteria["exclusion"]["d_gad7_grave_ou_risco"] is False


def test_ineligible_when_exclusion_present(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid), "gad7_total": GAD7_ELEGIVEL,
        **_criterios(exclusao={"b_neurologico": True})})
    assert r.status_code == 201 and r.json()["eligible"] is False
    assert r.json()["unmet_criteria"] == ["b_neurologico"]


def test_ineligible_when_inclusion_missing(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    payload = _criterios()
    payload["inclusion"]["vinculo_uninta"] = False
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid), "gad7_total": GAD7_ELEGIVEL, **payload})
    assert r.status_code == 201 and r.json()["eligible"] is False
    assert r.json()["unmet_criteria"] == ["vinculo_uninta"]


# ---------- G8: o conjunto de critérios é fechado ----------
def test_empty_screening_is_ineligible_not_vacuously_eligible(api):
    """O defeito que o G8 fecha: `all([])` respondia elegível para triagem vazia."""
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid), "inclusion": {}, "exclusion": {}})
    assert r.status_code == 422 and "não respondido" in r.json()["detail"]
    with TestSession() as s:
        assert s.scalar(select(Screening.id).where(Screening.participant_id == pid)) is None


def test_unknown_criterion_key_422(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    payload = _criterios()
    payload["inclusion"]["idade_18_60"] = True          # chave do formulário antigo
    r = client.post(SCREEN, headers=hdr, json={"participant_id": str(pid), **payload})
    assert r.status_code == 422 and "desconhecido" in r.json()["detail"]


def test_derived_criterion_cannot_be_declared_422(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    payload = _criterios()
    payload["inclusion"]["sintomas_elegiveis"] = True   # quem decide é a regra, não o formulário
    r = client.post(SCREEN, headers=hdr, json={"participant_id": str(pid), **payload})
    assert r.status_code == 422 and "calculado pelo servidor" in r.json()["detail"]


def test_symptom_range_is_computed_from_scores(api):
    """GAD-7 fora da faixa e sem PSQI ruim: inelegível mesmo com todas as caixas marcadas."""
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid), "gad7_total": 2, "psqi_global": 3, **_criterios()})
    assert r.status_code == 201 and r.json()["eligible"] is False
    assert r.json()["unmet_criteria"] == ["sintomas_elegiveis"]


def test_bad_sleep_alone_satisfies_the_symptom_range(api):
    """"e/ou": PSQI > 5 basta, mesmo com GAD-7 abaixo de 5."""
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": str(pid), "gad7_total": 2, "psqi_global": 9, **_criterios()})
    assert r.status_code == 201 and r.json()["eligible"] is True


def test_criteria_catalog_lists_protocol_keys(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    r = client.get(f"{SCREEN}/criteria", headers=hdr)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == CRITERIA_VERSION
    chaves_ex = [c["key"] for c in body["exclusion"]]
    assert chaves_ex[0].startswith("a_") and len(chaves_ex) == 9   # alíneas (a) a (i)
    derivados = [c["key"] for c in body["inclusion"] + body["exclusion"] if c["derived"]]
    assert set(derivados) == {"sintomas_elegiveis", "d_gad7_grave_ou_risco"}


def test_screening_is_audited_without_pii(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=True)
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "screening.recorded")).one()
        assert (ev.resource_type == "screening" and ev.resource_id == pid
                and ev.meta == {"eligible": True, "risk_detected": False,
                                "criteria_version": CRITERIA_VERSION, "unmet": []})


def test_duplicate_screening_409(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    assert _screen(client, hdr, pid).status_code == 201
    assert _screen(client, hdr, pid).status_code == 409


def test_unknown_participant_404(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    r = client.post(SCREEN, headers=hdr, json={
        "participant_id": "00000000-0000-0000-0000-000000000000", **_criterios()})
    assert r.status_code == 404


def test_participant_token_forbidden_403(api):
    client, TestSession = api
    pid = _participant(TestSession)
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}
    r = client.post(SCREEN, headers=hdr, json={"participant_id": str(pid), **_criterios()})
    assert r.status_code == 403
    assert client.get(f"{SCREEN}/criteria", headers=hdr).status_code == 403


def test_no_token_401(api):
    client, TestSession = api
    pid = _participant(TestSession)
    r = client.post(SCREEN, json={"participant_id": str(pid), **_criterios()})
    assert r.status_code == 401


def test_invalid_uuid_422(api):
    client, TestSession = api
    hdr = _staff(TestSession)
    r = client.post(SCREEN, headers=hdr, json={"participant_id": "nao-e-uuid", **_criterios()})
    assert r.status_code == 422


# ---------- gate do funil na alocação ----------
def test_allocation_blocked_before_screening(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _consent(TestSession, pid)                       # consentiu, mas não foi triado
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 409 and "triagem" in r.json()["detail"].lower()


def test_allocation_blocked_when_ineligible(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=False); _consent(TestSession, pid)
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 409 and "inelegível" in r.json()["detail"].lower()


def test_allocation_blocked_without_consent(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=True)         # elegível, mas sem consentimento
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 409 and "consentimento" in r.json()["detail"].lower()


def test_allocation_allowed_after_full_funnel(api):
    client, TestSession = api
    hdr = _staff(TestSession); pid = _participant(TestSession)
    _screen(client, hdr, pid, eligible=True); _consent(TestSession, pid)
    r = client.post(ALLOC, headers=hdr, json={"participant_id": str(pid)})
    assert r.status_code == 201 and r.json()["status"] == "allocated"
    with TestSession() as s:
        assert s.scalar(select(Allocation.id).where(Allocation.participant_id == pid)) is not None
