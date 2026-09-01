"""
tests/test_leitura_de_sessoes.py — Ler o registro por sessão (H2, ADR-111).

O ADR-107 acrescentou à sessão as colunas que o protocolo manda registrar em "Registro e
monitoramento" — duração das interrupções, volume médio e máximo, relaxamento 0–10 — e
**nenhuma delas era legível**. Existiam no banco e saíam, no máximo, agregadas no relatório.
E o contrato prometia `GET /sessions` ("listar sessões do participante") desde antes: a rota
simplesmente não existia.

O que se prova aqui:

  1. O participante lê o **próprio** histórico, e só ele — o filtro vem do token.
  2. O histórico do participante **não repete identificador do áudio**: dois participantes
     comparando `content_hash` descobririam que estão em braços diferentes.
  3. A equipe lê o registro por sessão com as seis colunas do ADR-107, pseudonimizado.
  4. **O registro da equipe não carrega nada do protocolo de áudio** — é o item de cegamento:
     só há dois protocolos, um por braço, então qualquer identificador estável do áudio
     particiona os participantes em dois grupos.
  5. Papéis: participante não lê o registro do estudo; equipe não usa a rota do participante.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core import auth
from app.core.models import (Participant, Allocation, AudioProtocol, StaffUser,
                             Session as SessionModel)
from tests.helpers import start_body

SESSIONS = "/v1/sessions"
REGISTRY = "/v1/sessions/registry"


@pytest.fixture
def cenario(api):
    """Dois participantes em braços diferentes, com uma sessão concluída cada."""
    client, TestSession = api
    with TestSession() as s:
        for pid, beat in (("sr-a", 3.0), ("sr-b", 0.0)):
            s.add(AudioProtocol(protocol_id=pid, version="1.0.0", band="delta",
                                carrier_hz=250.0, beat_hz=beat, duration_s=100.0,
                                target_peak_dbfs=-12.0, sample_rate=48000,
                                fade_in_s=1.0, fade_out_s=1.0,
                                content_hash=("a" if beat else "b") * 64))
        pessoas = {}
        for codigo, arm in (("P-S1", "A"), ("P-S2", "B")):
            p = Participant(study_code=codigo); s.add(p); s.flush()
            s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1,
                             sequence_seed_ref="ref"))
            pessoas[codigo] = p.id
        s.commit()

    tokens = {c: {"Authorization": f"Bearer {auth.issue_access(str(i), 'participant')}"}
              for c, i in pessoas.items()}
    for codigo, hdr in tokens.items():
        r = client.post(SESSIONS, headers=hdr, json=start_body("delta"))
        assert r.status_code == 201, r.text
        sid = r.json()["session_id"]
        r = client.post(f"{SESSIONS}/{sid}/complete", headers=hdr, json={
            "effective_seconds": 95, "interruptions": 2, "paused_seconds": 40,
            "gain_mean": 0.8, "gain_peak": 0.8, "relaxation_0_10": 7})
        assert r.status_code == 200, r.text
    return client, TestSession, tokens


def _staff(TestSession, role="researcher"):
    # E-mail único por chamada: mais de um teste cria staff duas vezes, e o e-mail é UNIQUE.
    with TestSession() as s:
        u = StaffUser(email=f"{role}-{uuid.uuid4().hex[:8]}@uninta.edu.br",
                      password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


# ------------------------------------------------------- 1 e 2. o histórico do participante
def test_participante_le_o_proprio_historico(cenario):
    """A rota que o contrato prometia e que não existia."""
    client, _TestSession, tokens = cenario
    r = client.get(SESSIONS, headers=tokens["P-S1"])
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert len(itens) == 1                              # só as SUAS, não as duas do estudo
    assert itens[0]["completed"] is True
    assert itens[0]["effective_seconds"] == 95
    assert itens[0]["relaxation_0_10"] == 7


def test_o_historico_nao_repete_identificador_do_audio(cenario):
    """Dois participantes comparando o hash do áudio saberiam que estão em braços diferentes."""
    client, _TestSession, tokens = cenario
    bruto = client.get(SESSIONS, headers=tokens["P-S1"]).text.lower()
    for proibido in ("content_hash", "protocol", "handle", "hash"):
        assert proibido not in bruto, f"o histórico devolveu {proibido!r}"


# ------------------------------------------------------------- 3 e 4. o registro da equipe
def test_equipe_le_as_seis_colunas_do_adr_107(cenario):
    """As colunas existiam desde o ADR-107 e ninguém as alcançava fora do SQL."""
    client, TestSession, _tokens = cenario
    r = client.get(REGISTRY, headers=_staff(TestSession))
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert len(itens) == 2                              # o estudo inteiro, não um participante
    x = itens[0]
    assert x["interruptions"] == 2 and x["paused_seconds"] == 40
    assert x["gain_mean"] == 0.8 and x["gain_peak"] == 0.8
    assert x["relaxation_0_10"] == 7
    assert x["headphones_ok"] is True
    assert x["study_code"] in ("P-S1", "P-S2")


def test_o_registro_da_equipe_nao_carrega_nada_do_protocolo(cenario):
    """Item de CEGAMENTO. Só há dois protocolos, um por braço: qualquer identificador estável
    do áudio particiona os participantes em dois grupos, e saber quem está com quem já quebra
    o cegamento da análise — que tem rito próprio, com dois admins (ADR-075)."""
    client, TestSession, _tokens = cenario
    bruto = client.get(REGISTRY, headers=_staff(TestSession)).text.lower()
    for proibido in ("protocol", "content_hash", "arm", "condition", "sham", "beat", "delta"):
        assert proibido not in bruto, f"o registro vazou {proibido!r}"

    # E os dois braços saem indistinguíveis: mesmas chaves, mesma forma.
    itens = client.get(REGISTRY, headers=_staff(TestSession)).json()["items"]
    assert {frozenset(i) for i in itens} == {frozenset(itens[0])}


def test_filtro_por_study_code(cenario):
    client, TestSession, _tokens = cenario
    staff = _staff(TestSession)
    so_um = client.get(f"{REGISTRY}?study_code=P-S2", headers=staff).json()["items"]
    assert [i["study_code"] for i in so_um] == ["P-S2"]
    # Código inexistente é lista vazia, não 404: "nenhuma sessão" é resposta legítima.
    r = client.get(f"{REGISTRY}?study_code=NAO-EXISTE", headers=staff)
    assert r.status_code == 200 and r.json()["items"] == []


# ------------------------------------------------------------------------------- 5. papéis
def test_papeis_de_cada_leitura(cenario):
    client, TestSession, tokens = cenario
    staff = _staff(TestSession)
    assert client.get(REGISTRY, headers=tokens["P-S1"]).status_code == 403
    assert client.get(SESSIONS, headers=staff).status_code == 403
    assert client.get(SESSIONS).status_code == 401
    assert client.get(REGISTRY).status_code == 401


def test_o_registro_ve_sessao_ainda_aberta(cenario):
    """Sessão iniciada e não encerrada aparece com os campos do fim nulos — é o que permite
    à equipe ver quem começou e não terminou, em vez de só o que já fechou."""
    client, TestSession, tokens = cenario
    r = client.post(SESSIONS, headers=tokens["P-S1"], json=start_body("delta"))
    assert r.status_code == 201
    aberta = [i for i in client.get(REGISTRY, headers=_staff(TestSession)).json()["items"]
              if i["session_id"] == r.json()["session_id"]]
    assert len(aberta) == 1
    assert aberta[0]["completed"] is False
    assert aberta[0]["effective_seconds"] is None and aberta[0]["ended_at"] is None


def test_o_participante_so_ve_as_suas_mesmo_com_muitas_no_estudo(cenario):
    """IDOR por omissão: o filtro vem do token, não de parâmetro — não há como pedir as alheias."""
    client, TestSession, tokens = cenario
    minhas = client.get(SESSIONS, headers=tokens["P-S2"]).json()["items"]
    with TestSession() as s:
        pid = s.scalar(select(Participant.id).where(Participant.study_code == "P-S2"))
        do_banco = s.scalars(select(SessionModel.id).where(
            SessionModel.participant_id == pid)).all()
    assert {i["session_id"] for i in minhas} == {str(x) for x in do_banco}
