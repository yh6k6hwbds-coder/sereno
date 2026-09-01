"""
tests/test_research_participants.py — A lista de participantes deixa de mentir (H6, ADR-113).

`GET /v1/research/participants` era um stub: devolvia `{"items": [], "next_cursor": null}` com
um `TODO` no corpo. Não é o mesmo que uma rota faltando — uma rota ausente dá 404 e quem chama
percebe. Esta **respondia errado em silêncio**: quem a consultasse concluiria que não há
participantes no estudo, e nada indicaria o contrário.

O que se prova aqui:

  1. A lista traz quem está no estudo, com adesão e contagem de eventos adversos.
  2. **As contagens não se multiplicam.** Sessões e eventos adversos na mesma linha, por `join`,
     dariam o produto das duas — e a adesão sairia errada por um fator, continuando plausível.
  3. O braço sai **codificado** (A/B) e nunca traduzido; participante não randomizado sai nulo.
  4. A paginação por cursor não repete nem pula linhas, mesmo com inscrições no mesmo instante.
  5. Papel errado é 403; sem token é 401.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from app.core import auth
from app.core.models import (Participant, Allocation, AudioProtocol, AdverseEvent, StaffUser,
                             Session as SessionModel)

URL = "/v1/research/participants"


def _staff(TestSession, role="researcher"):
    with TestSession() as s:
        u = StaffUser(email=f"{role}-{uuid.uuid4().hex[:8]}@uninta.edu.br",
                      password_hash=auth.hash_password("Senha-Forte-123"),
                      role=role, mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), role)}"}


@pytest.fixture
def povoado(api):
    """P-01: 3 sessões concluídas (1 não) e 2 eventos adversos. P-02: nada. P-03: sem alocação."""
    client, TestSession = api
    base = dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.timezone.utc)
    with TestSession() as s:
        proto = AudioProtocol(protocol_id="rp-1", version="1.0.0", band="delta",
                              carrier_hz=250.0, beat_hz=3.0, duration_s=1200.0,
                              target_peak_dbfs=-12.0, sample_rate=48000,
                              fade_in_s=1.0, fade_out_s=1.0, content_hash="e" * 64)
        s.add(proto); s.flush()

        ids = {}
        for i, (codigo, arm) in enumerate((("P-01", "A"), ("P-02", "B"), ("P-03", None))):
            p = Participant(study_code=codigo, enrolled_at=base + dt.timedelta(days=i))
            s.add(p); s.flush()
            ids[codigo] = p.id
            if arm is not None:
                s.add(Allocation(participant_id=p.id, arm_coded=arm, block=1,
                                 sequence_seed_ref="ref"))

        for n, concluida in enumerate([True, True, True, False]):
            s.add(SessionModel(participant_id=ids["P-01"], protocol_uuid=proto.id,
                               protocol_hash=proto.content_hash, headphones_ok=True,
                               completed=concluida,
                               started_at=base + dt.timedelta(days=10 + n)))
        for tipo in ("cefaleia", "tontura"):
            s.add(AdverseEvent(participant_id=ids["P-01"], type=tipo, severity="mild",
                               occurred_at=base + dt.timedelta(days=11)))
        s.commit()
    return client, TestSession, ids


def test_a_lista_deixa_de_vir_vazia(povoado):
    """O defeito original: a rota respondia `items: []` com participantes no banco."""
    client, TestSession, _ids = povoado
    r = client.get(URL, headers=_staff(TestSession))
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert [i["study_code"] for i in itens] == ["P-03", "P-02", "P-01"]   # mais recente 1º


def test_as_contagens_nao_se_multiplicam(povoado):
    """3 sessões concluídas e 2 eventos adversos — não 6 e 6.

    É o defeito que um `join` das duas tabelas produziria, e que passa despercebido porque o
    número continua parecendo plausível: a adesão sairia multiplicada por um fator inteiro."""
    client, TestSession, _ids = povoado
    itens = client.get(URL, headers=_staff(TestSession)).json()["items"]
    p01 = next(i for i in itens if i["study_code"] == "P-01")
    assert p01["sessions_completed"] == 3            # a 4ª não contou para a adesão
    assert p01["adverse_events"] == 2
    assert p01["adherence_pct"] == 15.0             # 3 de 20 sessões prescritas

    p02 = next(i for i in itens if i["study_code"] == "P-02")
    assert (p02["sessions_completed"], p02["adverse_events"], p02["adherence_pct"]) == (0, 0, 0.0)


def test_o_braco_sai_codificado_e_nunca_traduzido(povoado):
    """A/B não dizem qual é o ativo; o mapa fica selado até o data lock (ADR-075)."""
    client, TestSession, _ids = povoado
    r = client.get(URL, headers=_staff(TestSession))
    assert {i["arm_coded"] for i in r.json()["items"]} == {"A", "B", None}
    bruto = r.text.lower()
    # "active" fica FORA da varredura de propósito: é o `status` do participante (inscrito e
    # ativo), palavra igual a um dos valores da condição e coisa completamente diferente.
    # Varrer por ela aqui reprovaria a resposta correta — e um item que grita no caso certo
    # deixa de ser lido quando grita no caso errado.
    for proibido in ("sham", "condition", "protocol", "content_hash", "beat_hz"):
        assert proibido not in bruto, f"a listagem vazou {proibido!r}"
    # O que de fato não pode aparecer é a CONDIÇÃO traduzida ao lado do braço codificado.
    assert '"condition"' not in bruto and '"sham"' not in bruto


def test_quem_ainda_nao_foi_randomizado_aparece_com_braco_nulo(povoado):
    """Inscrito e não alocado é estado REAL do estudo — sumir com a linha esconderia a fila."""
    client, TestSession, _ids = povoado
    itens = client.get(URL, headers=_staff(TestSession)).json()["items"]
    p03 = next(i for i in itens if i["study_code"] == "P-03")
    assert p03["arm_coded"] is None and p03["status"] == "active"


def test_paginacao_por_cursor_nao_repete_nem_pula(povoado):
    client, TestSession, _ids = povoado
    staff = _staff(TestSession)
    pag1 = client.get(f"{URL}?limit=2", headers=staff).json()
    assert len(pag1["items"]) == 2 and pag1["next_cursor"]

    pag2 = client.get(f"{URL}?limit=2&cursor={pag1['next_cursor']}", headers=staff).json()
    vistos = [i["study_code"] for i in pag1["items"] + pag2["items"]]
    assert vistos == ["P-03", "P-02", "P-01"]        # sem repetir, sem pular
    assert pag2["next_cursor"] is None               # última página


def test_cursor_desempata_inscricoes_no_mesmo_instante(api):
    """Sem desempate por id, empate em `enrolled_at` faz página repetir ou pular linha."""
    client, TestSession = api
    instante = dt.datetime(2026, 8, 20, 9, 0, tzinfo=dt.timezone.utc)
    with TestSession() as s:
        for n in range(5):
            s.add(Participant(study_code=f"E-{n}", enrolled_at=instante))
        s.commit()
    staff = _staff(TestSession)

    vistos, cursor = [], None
    for _ in range(5):
        url = f"{URL}?limit=2" + (f"&cursor={cursor}" if cursor else "")
        pag = client.get(url, headers=staff).json()
        vistos += [i["study_code"] for i in pag["items"]]
        cursor = pag["next_cursor"]
        if cursor is None:
            break
    assert sorted(vistos) == ["E-0", "E-1", "E-2", "E-3", "E-4"]
    assert len(vistos) == len(set(vistos))


def test_papeis(povoado):
    client, TestSession, ids = povoado
    hdr = {"Authorization": f"Bearer {auth.issue_access(str(ids['P-01']), 'participant')}"}
    assert client.get(URL, headers=hdr).status_code == 403
    assert client.get(URL).status_code == 401


def test_o_banco_confirma_o_que_a_lista_diz(povoado):
    """Guarda contra o retorno do stub: a lista tem de refletir o banco, não um literal."""
    client, TestSession, _ids = povoado
    itens = client.get(URL, headers=_staff(TestSession)).json()["items"]
    with TestSession() as s:
        codigos = s.scalars(select(Participant.study_code)).all()
    assert {i["study_code"] for i in itens} == set(codigos)
