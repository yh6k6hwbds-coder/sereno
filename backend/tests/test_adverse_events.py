"""
tests/test_adverse_events.py — Relato de evento adverso, ponta a ponta.

Cobre: leve → registrado sem atenção; grave → atenção + gancho de notificação
acionado; evento ligado à própria sessão (201) vs sessão alheia (404); gravidade
inválida (422); papel errado (403); sem token (401). A resposta sempre orienta ajuda.

E, desde o ADR-110, o outro lado: a EQUIPE lendo e fechando o evento. Segurança é desfecho
primário e, até então, era o único dado do estudo sem leitura nenhuma — só havia o POST.
"""
from __future__ import annotations
import hashlib
import pytest
from sqlalchemy import select
from app.core.models import (Participant, Allocation, AudioProtocol,
                             Session as SessionModel, AdverseEvent, StaffUser,
                             AuditLog)
from app.core import auth
from app.modules.adverse_events import router as ae_router
from tests.helpers import start_body

URL = "/v1/adverse-events"
SESSIONS = "/v1/sessions"


@pytest.fixture
def capture_notify(monkeypatch):
    calls = []
    monkeypatch.setattr(ae_router, "notify_team", lambda eid, sev: calls.append((eid, sev)))
    return calls


def _participant(TestSession, code, arm="A"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.flush()
        s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1, sequence_seed_ref="ref"))
        s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _seed_alpha(TestSession):
    with TestSession() as s:
        s.add(AudioProtocol(protocol_id="px-1", version="1.0.0", band="alpha", carrier_hz=200,
                            beat_hz=10, duration_s=1200, target_peak_dbfs=-3.0,
                            content_hash=hashlib.sha256(b"a").hexdigest()))
        s.commit()


def test_mild_event_recorded_no_attention(api, capture_notify):
    client, TestSession = api
    pid, hdr = _participant(TestSession, "P-AE1")
    r = client.post(URL, headers=hdr, json={"type": "cefaleia", "severity": "mild"})
    assert r.status_code == 201
    body = r.json()
    assert body["requires_attention"] is False and "profissional" in body["guidance"]
    assert capture_notify == []                       # não notificou
    with TestSession() as s:
        assert s.scalar(select(AdverseEvent.id).where(AdverseEvent.participant_id == pid)) is not None


def test_severe_event_flags_attention_and_notifies(api, capture_notify):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE2")
    r = client.post(URL, headers=hdr, json={"type": "tontura intensa", "severity": "severe"})
    assert r.status_code == 201
    body = r.json()
    assert body["requires_attention"] is True
    assert "192" in body["guidance"]                  # orientação urgente
    assert len(capture_notify) == 1 and capture_notify[0][1] == "severe"


def test_moderate_also_requires_attention(api, capture_notify):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE3")
    r = client.post(URL, headers=hdr, json={"type": "nausea", "severity": "moderate"})
    assert r.status_code == 201 and r.json()["requires_attention"] is True
    assert len(capture_notify) == 1


def test_event_linked_to_own_session_ok(api, capture_notify):
    client, TestSession = api
    _seed_alpha(TestSession)
    _pid, hdr = _participant(TestSession, "P-AE4")
    sid = client.post(SESSIONS, headers=hdr, json=start_body("alpha")).json()["session_id"]
    r = client.post(URL, headers=hdr, json={"type": "desconforto", "severity": "mild", "session_id": sid})
    assert r.status_code == 201


def test_event_linked_to_other_session_404(api, capture_notify):
    client, TestSession = api
    _seed_alpha(TestSession)
    _pa, hdr_a = _participant(TestSession, "P-AE-OWN", "A")
    _pb, hdr_b = _participant(TestSession, "P-AE-INT", "B")
    sid = client.post(SESSIONS, headers=hdr_a, json=start_body("alpha")).json()["session_id"]
    r = client.post(URL, headers=hdr_b, json={"type": "cefaleia", "severity": "mild", "session_id": sid})
    assert r.status_code == 404


def test_invalid_severity_422(api, capture_notify):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE5")
    r = client.post(URL, headers=hdr, json={"type": "x", "severity": "gravissimo"})
    assert r.status_code == 422


def test_staff_role_forbidden_403(api, capture_notify):
    client, TestSession = api
    hdr = {"Authorization": f"Bearer {auth.issue_access('22222222-2222-2222-2222-222222222222', 'researcher')}"}
    r = client.post(URL, headers=hdr, json={"type": "x", "severity": "mild"})
    assert r.status_code == 403


def test_no_token_401(api, capture_notify):
    client, _ = api
    assert client.post(URL, json={"type": "x", "severity": "mild"}).status_code == 401


# --------------------------------------------------------- ADR-110: a equipe lê e acompanha
def _staff(TestSession, role="researcher"):
    with TestSession() as s:
        u = StaffUser(email=f"{role}-ae@uninta.edu.br",
                      password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return uid, {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


def _relata(client, hdr, tipo, gravidade):
    r = client.post(URL, headers=hdr, json={"type": tipo, "severity": gravidade})
    assert r.status_code == 201, r.text
    return r


def test_equipe_le_os_eventos_pseudonimizados(api, capture_notify):
    """O relato existia e não havia como lê-lo: a lista é o que fecha o ADR-051."""
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE10")
    _relata(client, hdr, "cefaleia", "mild")
    _relata(client, hdr, "tontura", "severe")

    _uid, staff = _staff(TestSession)
    r = client.get(URL, headers=staff)
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert [i["type"] for i in itens] == ["tontura", "cefaleia"]      # mais recente primeiro
    assert {i["study_code"] for i in itens} == {"P-AE10"}
    assert itens[0]["requires_attention"] is True and itens[1]["requires_attention"] is False
    assert itens[0]["outcome"] is None


def test_a_lista_nao_revela_braco_nem_pii(api, capture_notify):
    """Cegamento: a equipe que lê EA não pode inferir alocação a partir da lista."""
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE11", arm="B")
    _relata(client, hdr, "zumbido", "moderate")
    _uid, staff = _staff(TestSession)
    bruto = client.get(URL, headers=staff).text.lower()
    for proibido in ("arm", "braco", "condition", "active", "sham", "protocol"):
        assert proibido not in bruto, f"a listagem vazou {proibido!r}"


def test_filtro_pending_mostra_so_o_que_falta_fechar(api, capture_notify):
    """A pergunta que a equipe faz ao abrir a lista é o que ainda está em aberto."""
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE12")
    _relata(client, hdr, "cefaleia", "mild")            # leve: não pede atenção
    grave = _relata(client, hdr, "tontura", "severe")   # grave e sem desfecho: pendente
    _uid, staff = _staff(TestSession)

    pend = client.get(f"{URL}?pending=true", headers=staff).json()["items"]
    assert [i["type"] for i in pend] == ["tontura"]

    # Ao fechar o grave, ele sai dos pendentes — o filtro olha o desfecho, não a gravidade.
    eid = [i["id"] for i in client.get(URL, headers=staff).json()["items"]
           if i["type"] == "tontura"][0]
    r = client.post(f"{URL}/{eid}/outcome", headers=staff,
                    json={"outcome": "resolvido em 24h, sem conduta adicional"})
    assert r.status_code == 200, r.text
    assert r.json()["outcome"].startswith("resolvido")
    assert client.get(f"{URL}?pending=true", headers=staff).json()["items"] == []
    assert grave.json()["requires_attention"] is True


def test_filtro_por_gravidade(api, capture_notify):
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE13")
    _relata(client, hdr, "cefaleia", "mild")
    _relata(client, hdr, "tontura", "severe")
    _uid, staff = _staff(TestSession)
    so_graves = client.get(f"{URL}?severity=severe", headers=staff).json()["items"]
    assert [i["type"] for i in so_graves] == ["tontura"]
    assert client.get(f"{URL}?severity=inventada", headers=staff).status_code == 422


def test_desfecho_deixa_trilha_de_auditoria_sem_o_texto(api, capture_notify):
    """O texto do desfecho é dado de saúde: a trilha registra que houve, não o que dizia."""
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE14")
    _relata(client, hdr, "tontura", "moderate")
    _uid, staff = _staff(TestSession)
    eid = client.get(URL, headers=staff).json()["items"][0]["id"]
    segredo = "encaminhada ao CAPS por ideacao"
    assert client.post(f"{URL}/{eid}/outcome", headers=staff,
                       json={"outcome": segredo}).status_code == 200

    with TestSession() as s:
        linha = s.scalar(select(AuditLog).where(
            AuditLog.action == "adverse_event.outcome_recorded"))
        assert linha is not None and str(linha.resource_id) == eid
        assert segredo not in str(linha.meta)


def test_desfecho_pode_evoluir_e_evento_inexistente_e_404(api, capture_notify):
    """Sobrescrever é de propósito: um desfecho evolui, e abrir evento novo duplicaria a
    contagem justamente na tabela em que contar eventos importa."""
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE15")
    _relata(client, hdr, "tontura", "moderate")
    _uid, staff = _staff(TestSession)
    eid = client.get(URL, headers=staff).json()["items"][0]["id"]
    client.post(f"{URL}/{eid}/outcome", headers=staff, json={"outcome": "em acompanhamento"})
    r = client.post(f"{URL}/{eid}/outcome", headers=staff, json={"outcome": "resolvido"})
    assert r.json()["outcome"] == "resolvido"
    assert client.post(f"{URL}/11111111-1111-1111-1111-111111111111/outcome",
                       headers=staff, json={"outcome": "nao existe"}).status_code == 404


def test_participante_nao_le_nem_fecha_evento(api, capture_notify):
    """ae:write é para relatar. Ler a lista do estudo, ou fechar um evento, é da equipe."""
    client, TestSession = api
    _pid, hdr = _participant(TestSession, "P-AE16")
    _relata(client, hdr, "cefaleia", "mild")
    assert client.get(URL, headers=hdr).status_code == 403
    eid = client.get(URL, headers=_staff(TestSession)[1]).json()["items"][0]["id"]
    assert client.post(f"{URL}/{eid}/outcome", headers=hdr,
                       json={"outcome": "eu mesmo fecho"}).status_code == 403
    assert client.get(URL).status_code == 401
