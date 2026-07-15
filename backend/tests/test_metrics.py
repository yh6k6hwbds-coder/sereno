"""
tests/test_metrics.py — Endpoint de métricas Prometheus (ADR-080).

Prova o "Pronto (DoD)":
  - ``GET /metrics`` responde no formato texto do Prometheus e reflete o tráfego;
  - o rótulo de rota é o **template** (baixa cardinalidade), nunca o caminho concreto —
    um UUID no caminho NÃO aparece nas métricas (sem PII/braço, sem explosão de cardinalidade);
  - o próprio ``/metrics`` não se auto-mede;
  - com ``METRICS_TOKEN`` setado, o endpoint exige ``Authorization: Bearer <token>`` (401 sem).
"""
from __future__ import annotations
import re


def _metric_value(body: str, name: str, **labels) -> float:
    """Extrai o valor de uma amostra `name{labels...}` do texto Prometheus (0.0 se ausente)."""
    for line in body.splitlines():
        if not line.startswith(name + "{"):
            continue
        if all(f'{k}="{v}"' in line for k, v in labels.items()):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def test_metrics_endpoint_exposes_prometheus_text(api):
    client, _ = api
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in r.text


def test_health_request_is_counted(api):
    client, _ = api
    before = float(_metric_value(client.get("/metrics").text,
                                 "http_requests_total", method="GET", path="/health", status="200"))
    client.get("/health")
    after = float(_metric_value(client.get("/metrics").text,
                                "http_requests_total", method="GET", path="/health", status="200"))
    assert after == before + 1


def test_route_template_not_concrete_path(api):
    client, _ = api
    # Rota parametrizada, sem auth → 401, mas a rota CASA (o template é registrado).
    concrete = "/v1/sessions/11111111-1111-1111-1111-111111111111/audio"
    assert client.get(concrete).status_code == 401
    body = client.get("/metrics").text
    # o template (relativo ao mount, sem o /v1 constante) aparece; o UUID concreto NÃO
    assert 'path="/sessions/{session_id}/audio"' in body
    assert "11111111-1111-1111-1111-111111111111" not in body


def test_metrics_path_is_not_self_measured(api):
    client, _ = api
    client.get("/metrics")
    body = client.get("/metrics").text
    assert 'path="/metrics"' not in body


def test_metrics_requires_token_when_configured(api, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cret")
    client, _ = api
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert "http_requests_total" in ok.text


def test_unmatched_path_collapses_to_sentinel(api):
    client, _ = api
    client.get("/v1/rota-que-nao-existe-xyz")
    body = client.get("/metrics").text
    assert 'path="<unmatched>"' in body
    assert "rota-que-nao-existe-xyz" not in body


def test_metrics_content_has_no_arm_labels(api):
    client, _ = api
    body = client.get("/metrics").text
    # nenhuma métrica deve expor condição do estudo
    assert not re.search(r"\b(active|sham|arm|beat_hz|condition)\b", body, re.IGNORECASE)
