"""
tests/test_wearables.py — Ingestão de vestíveis (seam desacoplado, E2/ADR-084).

Prova o "Pronto (DoD)":
  (1) participante ingere um lote de FC/sono → 202 + contagem aceita;
  (2) o adaptador padrão (NullSink) NÃO persiste (é o seam preparado); com o MemorySink o
      seam funciona ponta a ponta (leituras chegam ao sink);
  (3) staff não ingere (403); anônimo (401); payload inválido (422);
  (4) auditoria SEM valores de saúde (só a contagem; nenhum valor/horário no log);
  (5) OFFLINE quanto à decisão: ingerir não cria recomendação e o feature_vector do
      recomendador NÃO ganha nenhum campo de vestível (inegociável #5).
"""
from __future__ import annotations
from sqlalchemy import func, select

from app.core.models import Participant, StaffUser, AuditLog, RecommendationLog
from app.core import auth
from app.modules.wearables.sink import MemoryWearableSink, set_wearable_sink

WEAR = "/v1/wearables/readings"
REC = "/v1/recommendations"


def _participant(TestSession, code="P-WEAR"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def _staff_hdr(TestSession):
    with TestSession() as s:
        u = StaffUser(email="r@uninta.edu.br", password_hash=auth.hash_password("Senha-Forte-123"),
                      role="researcher", mfa_enabled=False)
        s.add(u); s.commit(); uid = u.id
    return {"Authorization": f"Bearer {auth.issue_access(str(uid), 'researcher')}"}


def _batch(n_hr=2, n_sleep=1):
    reads = [{"kind": "heart_rate", "taken_at": "2026-07-20T22:00:00Z",
              "value": 58 + i, "unit": "bpm", "source": "healthkit"} for i in range(n_hr)]
    reads += [{"kind": "sleep", "taken_at": "2026-07-20T23:00:00Z",
               "value": 420, "unit": "min", "source": "googlefit"} for _ in range(n_sleep)]
    return {"readings": reads}


def test_participant_ingests_batch_202(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession)
    r = client.post(WEAR, headers=hdr, json=_batch(2, 1))
    assert r.status_code == 202
    assert r.json()["accepted"] == 3


def test_default_null_sink_does_not_persist(api):
    # Sem WEARABLE_SINK: o padrão é NullSink — aceita e descarta (nada a inspecionar).
    client, TestSession = api
    _pid, hdr = _participant(TestSession)
    r = client.post(WEAR, headers=hdr, json=_batch(1, 0))
    assert r.status_code == 202 and r.json()["accepted"] == 1
    # Não há tabela de leituras (sem migração): o seam é preparação, não persistência.
    assert "wearable_reading" not in {t.name for t in Participant.metadata.tables.values()
                                      if t.name == "wearable_reading"}


def test_memory_sink_receives_readings_end_to_end(api):
    client, TestSession = api
    sink = MemoryWearableSink()
    set_wearable_sink(sink)                       # injeta o seam de memória (o autouse limpa depois)
    pid, hdr = _participant(TestSession)
    client.post(WEAR, headers=hdr, json=_batch(2, 1))
    stored = sink.readings_for(pid)
    assert len(stored) == 3
    assert {r.kind for r in stored} == {"heart_rate", "sleep"}
    assert {r.source for r in stored} == {"healthkit", "googlefit"}


def test_staff_cannot_ingest_403(api):
    client, TestSession = api
    hdr = _staff_hdr(TestSession)
    assert client.post(WEAR, headers=hdr, json=_batch()).status_code == 403


def test_no_token_401(api):
    client, TestSession = api
    assert client.post(WEAR, json=_batch()).status_code == 401


def test_invalid_payload_422(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession)
    bad = [
        {"readings": []},                                                        # lote vazio
        {"readings": [{"kind": "steps", "taken_at": "2026-07-20T22:00:00Z",     # kind inválido
                       "value": 10, "unit": "n", "source": "x"}]},
        {"readings": [{"kind": "heart_rate", "taken_at": "nao-e-data",          # data inválida
                       "value": 60, "unit": "bpm", "source": "x"}]},
    ]
    for payload in bad:
        assert client.post(WEAR, headers=hdr, json=payload).status_code == 422


def test_ingest_audited_without_health_values(api):
    client, TestSession = api
    _pid, hdr = _participant(TestSession)
    client.post(WEAR, headers=hdr, json=_batch(2, 1))
    with TestSession() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.action == "wearable.ingested")).one()
        assert ev.resource_type == "wearable_reading" and ev.meta == {"accepted": 3}
        # Nenhum valor/horário/unidade de saúde no log — só a contagem.
        blob = f"{ev.meta}".lower()
        assert "58" not in blob and "bpm" not in blob and "420" not in blob


def test_ingestion_does_not_touch_live_recommender(api):
    """Inegociável #5: leituras de vestível não viram decisão nem feature ao vivo."""
    client, TestSession = api
    sink = MemoryWearableSink(); set_wearable_sink(sink)
    _pid, hdr = _participant(TestSession, "P-NODECIDE")
    client.post(WEAR, headers=hdr, json=_batch(3, 2))
    # Ingestão não cria recomendação alguma.
    with TestSession() as s:
        assert s.scalar(select(func.count()).select_from(RecommendationLog)) == 0
    # E o recomendador, ao rodar, não ganha nenhum campo de vestível no feature_vector.
    rid = client.post(REC, headers=hdr, json={"goal": "anxiety"}).json()["id"]
    with TestSession() as s:
        fv = s.get(RecommendationLog, __import__("uuid").UUID(rid)).inputs["feature_vector"]
        assert set(fv.keys()) == {"goal", "sleep_issue", "time_of_day",
                                  "recent_adverse_severity", "last_liked", "last_intensity"}
        assert not any("wear" in k or "hr" in k or "heart" in k for k in fv)
