"""
tests/test_safety_referral.py — PHQ-9 de segurança e fluxo de encaminhamento (G5/ADR-102).

O protocolo manda: GAD-7 >= 15, item 9 do PHQ-9 positivo ou relato de sofrimento psíquico →
o candidato **não é incluído** ou, se já incluído, é **retirado do protocolo**, acolhido e
encaminhado de forma documentada, com o encaminhamento comunicado ao CEP no relatório parcial.

Provamos o caminho inteiro: o gatilho, a retirada (a exposição para de fato), a ficha, a
confirmação de acolhimento e a contagem que vai ao relatório — e as duas coisas que NÃO podem
acontecer: escore de gravidade na resposta ao participante e vazamento de braço.
"""
from __future__ import annotations

import uuid

from app.core import auth
from app.core.models import (Participant, Allocation, AudioProtocol, Referral,
                             SafetyAssessment, ConsentRecord, StaffUser)
from app.modules.safety.service import GAD7_RISK_CUTOFF, evaluate_risk
from tests.helpers import start_body

CHECK = "/v1/participants/me/safety-check"
SEM_RISCO = [0] * 9                       # PHQ-9 todo zero
ITEM9 = [0] * 8 + [2]                     # só o item 9 positivo — total baixo, risco alto
GAD7_GRAVE = [3] * 7                      # 21 pontos


def _participante(TestSession, code="SF01", *, com_sessao=False):
    with TestSession() as s:
        p = Participant(study_code=code)
        s.add(p)
        s.flush()
        if com_sessao:
            if s.query(AudioProtocol).count() == 0:
                s.add(AudioProtocol(protocol_id="sf-01", version="1.0.0", band="delta",
                                    carrier_hz=250.0, beat_hz=3.0, duration_s=2.0,
                                    target_peak_dbfs=-12.0, content_hash="e" * 64))
                s.add(AudioProtocol(protocol_id="sf-02", version="1.0.0", band="delta",
                                    carrier_hz=250.0, beat_hz=0.0, duration_s=2.0,
                                    target_peak_dbfs=-12.0, content_hash="f" * 64))
            s.add(Allocation(participant_id=p.id, arm_coded="A", block=1, sequence_seed_ref="ref"))
        s.commit()
        return p.id


def _hdr(pid):
    return {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _staff(TestSession, role="researcher"):
    """Staff de verdade: o RBAC confere `is_active` no banco a cada requisicao (ADR-081)."""
    with TestSession() as s:
        u = StaffUser(email=f"{uuid.uuid4().hex[:8]}@uninta.edu.br",
                      password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u)
        s.commit()
        uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


# ------------------------------------------------------------------------ a regra
def test_regra_de_risco_e_versionada_e_explicita():
    assert GAD7_RISK_CUTOFF == 15                      # critério de exclusão (d) do protocolo
    assert evaluate_risk(gad7_total=14, phq9_item9=0) == []
    assert evaluate_risk(gad7_total=15, phq9_item9=0) == ["gad7_grave"]
    assert evaluate_risk(gad7_total=0, phq9_item9=1) == ["phq9_item9"]
    assert evaluate_risk(gad7_total=21, phq9_item9=3) == ["gad7_grave", "phq9_item9"]
    assert evaluate_risk(self_reported=True) == ["relato"]


def test_item9_positivo_dispara_mesmo_com_total_baixo(api):
    """Um total baixo com item 9 positivo não pode passar batido — é o ponto do rastreio."""
    client, TestSession = api
    pid = _participante(TestSession)
    r = client.post(CHECK, headers=_hdr(pid), json={"phq9_items": ITEM9})
    assert r.status_code == 201, r.text
    assert r.json()["referral_opened"] is True
    with TestSession() as s:
        av = s.query(SafetyAssessment).one()
        assert av.phq9_total == 2 and av.phq9_item9 == 2
        assert av.risk_detected is True and av.reasons == ["phq9_item9"]


# ----------------------------------------------------------- resposta ao participante
def test_resposta_nao_devolve_escore_e_sempre_orienta(api):
    """Número de gravidade na tela, sem profissional junto, é lido como diagnóstico."""
    client, TestSession = api
    pid = _participante(TestSession)
    corpo = client.post(CHECK, headers=_hdr(pid), json={"phq9_items": SEM_RISCO}).json()
    assert set(corpo) == {"status", "referral_opened", "guidance"}
    assert corpo["referral_opened"] is False
    assert "188" in corpo["guidance"]                  # CVV, como no TCLE
    texto = str(corpo).lower()
    for proibido in ("total", "severity", "grave", "phq", "score"):
        assert proibido not in texto


def test_sem_gatilho_nao_abre_ficha_nem_retira(api):
    client, TestSession = api
    pid = _participante(TestSession)
    client.post(CHECK, headers=_hdr(pid), json={"phq9_items": SEM_RISCO, "gad7_items": [1] * 7})
    with TestSession() as s:
        assert s.query(Referral).count() == 0
        assert s.get(Participant, pid).status == "active"


# --------------------------------------------------------------- retirada do protocolo
def test_gatilho_retira_do_protocolo_e_a_sessao_para(api):
    """Retirar não é só avisar: a exposição precisa parar de verdade."""
    client, TestSession = api
    pid = _participante(TestSession, code="SF02", com_sessao=True)
    hdr = _hdr(pid)

    assert client.post("/v1/sessions", headers=hdr, json=start_body("delta")).status_code == 201

    r = client.post(CHECK, headers=hdr, json={"phq9_items": SEM_RISCO, "gad7_items": GAD7_GRAVE})
    assert r.json()["referral_opened"] is True

    with TestSession() as s:
        assert s.get(Participant, pid).status == "removed"
    bloqueada = client.post("/v1/sessions", headers=hdr, json=start_body("delta"))
    assert bloqueada.status_code == 403, bloqueada.text
    assert "interromp" in bloqueada.text.lower()


def test_ficha_e_uma_so_mesmo_com_varios_gatilhos(api):
    """Reabrir ficha a cada questionário viraria fila de duplicatas."""
    client, TestSession = api
    pid = _participante(TestSession)
    hdr = _hdr(pid)
    client.post(CHECK, headers=hdr, json={"phq9_items": ITEM9})
    client.post(CHECK, headers=hdr, json={"phq9_items": SEM_RISCO, "gad7_items": GAD7_GRAVE})
    with TestSession() as s:
        fichas = s.query(Referral).all()
        assert len(fichas) == 1
        assert sorted(fichas[0].reasons) == ["gad7_grave", "phq9_item9"]   # motivos acumulam


# ---------------------------------------------------------------------------- triagem
def test_triagem_com_item9_positivo_torna_inelegivel(api):
    client, TestSession = api
    pid = _participante(TestSession, code="SF03")
    r = client.post("/v1/screening", headers=_staff(TestSession), json={
        "participant_id": str(pid),
        "inclusion": {"idade_18": True, "fones": True},
        "exclusion": {"epilepsia": False},
        "phq9_items": ITEM9})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["eligible"] is False and corpo["risk_detected"] is True
    assert corpo["referral_id"] is not None
    with TestSession() as s:
        assert s.query(Referral).count() == 1
        sc = s.query(SafetyAssessment).one()
        assert sc.moment == "triagem"


def test_triagem_com_gad7_grave_tambem_exclui(api):
    client, TestSession = api
    pid = _participante(TestSession, code="SF04")
    r = client.post("/v1/screening", headers=_staff(TestSession), json={
        "participant_id": str(pid),
        "inclusion": {"idade_18": True},
        "exclusion": {},
        "gad7_total": 15})
    assert r.json()["eligible"] is False and r.json()["risk_detected"] is True


def test_triagem_sem_phq9_segue_funcionando(api):
    """O campo é opcional: a triagem antiga não quebra (e não abre ficha à toa)."""
    client, TestSession = api
    pid = _participante(TestSession, code="SF05")
    r = client.post("/v1/screening", headers=_staff(TestSession), json={
        "participant_id": str(pid), "inclusion": {"idade_18": True}, "exclusion": {}})
    assert r.json() == {"status": "screened", "eligible": True,
                        "risk_detected": False, "referral_id": None}
    with TestSession() as s:
        assert s.query(Referral).count() == 0


# ------------------------------------------------------------------- ficha (equipe)
def test_ficha_listada_pseudonimizada_e_sem_braco(api):
    client, TestSession = api
    pid = _participante(TestSession, code="SF06", com_sessao=True)
    client.post(CHECK, headers=_hdr(pid), json={"phq9_items": ITEM9})

    r = client.get("/v1/referrals", headers=_staff(TestSession))
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["study_code"] == "SF06" and item["status"] == "aberto"
    assert item["reasons"] == ["phq9_item9"]
    texto = r.text.lower()
    for proibido in ("active", "sham", "grupo a", "grupo b", "arm", "phq9_total"):
        assert proibido not in texto


def test_registrar_encaminhamento_e_acolhimento(api):
    client, TestSession = api
    pid = _participante(TestSession, code="SF07")
    fid = client.post(CHECK, headers=_hdr(pid), json={"phq9_items": ITEM9}) and None
    with TestSession() as s:
        fid = str(s.query(Referral).one().id)

    hdr = _staff(TestSession)
    r1 = client.post(f"/v1/referrals/{fid}/record", headers=hdr, json={"service": "caps"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "encaminhado" and r1.json()["referred_at"] is not None
    assert r1.json()["acknowledged_at"] is None

    r2 = client.post(f"/v1/referrals/{fid}/record", headers=hdr,
                     json={"service": "caps", "acknowledged": True})
    assert r2.json()["status"] == "acolhido" and r2.json()["acknowledged_at"] is not None


def test_ficha_inexistente_da_404(api):
    client, TestSession = api
    r = client.post(f"/v1/referrals/{uuid.uuid4()}/record", headers=_staff(TestSession),
                    json={"service": "caps"})
    assert r.status_code == 404


def test_participante_nao_le_nem_altera_fichas(api):
    """A ficha é da equipe: participante não lista nem registra acolhimento."""
    client, TestSession = api
    pid = _participante(TestSession, code="SF08")
    hdr = _hdr(pid)
    assert client.get("/v1/referrals", headers=hdr).status_code == 403
    assert client.post(f"/v1/referrals/{uuid.uuid4()}/record", headers=hdr,
                       json={"service": "caps"}).status_code == 403


# ------------------------------------------------------------- relatório parcial (CEP)
def test_relatorio_conta_encaminhamentos_para_o_cep(api):
    client, TestSession = api
    pid = _participante(TestSession, code="SF09", com_sessao=True)
    with TestSession() as s:
        s.add(ConsentRecord(participant_id=pid, tcle_version="0.1.0-rascunho", accepted=True,
                            content_hash="0" * 64))
        s.commit()
    client.post(CHECK, headers=_hdr(pid), json={"phq9_items": ITEM9})

    r = client.get("/v1/research/analysis", headers=_staff(TestSession))
    assert r.status_code == 200, r.text
    seg = r.json()["seguranca"]
    assert seg["encaminhamentos"] == {"total": 1, "em_aberto": 1, "com_acolhimento_confirmado": 0}
    assert seg["retirados_por_seguranca"] == 1
    assert seg["eventos_adversos_graves"] == 0


# ------------------------------------------------------------------------ LGPD
def test_eliminacao_nao_apaga_a_retirada_por_seguranca(api):
    """Apagar PII é direito do titular; apagar POR QUE o estudo o retirou, não.

    Se a eliminação rebaixasse 'removed' para 'withdrawn', a contagem que vai ao CEP
    encolheria sozinha — sem que nenhum encaminhamento tivesse deixado de existir."""
    client, TestSession = api
    pid = _participante(TestSession, code="SF10")
    client.post(CHECK, headers=_hdr(pid), json={"phq9_items": ITEM9})

    admin = _staff(TestSession, role="admin")
    r = client.post(f"/v1/participants/{pid}/erase", headers=admin)
    assert r.status_code == 200, r.text
    with TestSession() as s:
        assert s.get(Participant, pid).status == "removed"

    dados = client.get(f"/v1/participants/{pid}/data", headers=admin).json()
    assert dados["safety_checks"][0]["risk_detected"] is True
    assert dados["referrals"][0]["status"] == "aberto"
    assert "arm" not in str(dados).lower()          # acesso do titular segue cego
