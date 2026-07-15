"""
tests/test_client_ip.py — Resolução do IP real do cliente atrás de proxy (ADR-078).

Prova o "Pronto (DoD)":
  - **sem** config de proxy, ignora ``X-Forwarded-For`` e usa o peer direto (seguro);
  - ``CLIENT_IP_HEADER`` (ex.: ``Fly-Client-IP``) tem precedência e é à prova de spoof;
  - ``TRUSTED_PROXY_HOPS`` confia só nas entradas mais à direita do XFF — um valor
    **forjado** pelo cliente (à esquerda) é ignorado;
  - integração: com um proxy confiável, o rate limit passa a valer **por cliente real**
    (dois clientes distintos têm buckets separados), não por IP da borda.
"""
from __future__ import annotations
from starlette.requests import Request

from app.core.client_ip import client_ip

PROXY = "198.51.100.7"     # peer direto (o proxy/borda)
CLIENT = "203.0.113.42"    # cliente real
FORGED = "10.9.9.9"        # valor que um cliente malicioso injeta no XFF


def _req(headers: dict | None = None, peer: str = PROXY) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 12345)})


def test_default_uses_peer_and_ignores_xff(monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert client_ip(_req({"X-Forwarded-For": CLIENT})) == PROXY


def test_client_ip_header_takes_precedence(monkeypatch):
    monkeypatch.setenv("CLIENT_IP_HEADER", "Fly-Client-IP")
    # presente mesmo com XFF e peer diferentes → vence e é à prova de spoof
    r = _req({"Fly-Client-IP": CLIENT, "X-Forwarded-For": FORGED})
    assert client_ip(r) == CLIENT


def test_client_ip_header_absent_falls_through(monkeypatch):
    monkeypatch.setenv("CLIENT_IP_HEADER", "Fly-Client-IP")
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    # cabeçalho configurado mas ausente → cai para o peer direto
    assert client_ip(_req({"X-Forwarded-For": CLIENT})) == PROXY


def test_trusted_hops_returns_client(monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    # 1 proxy confiável (o peer); o XFF traz só o cliente real
    assert client_ip(_req({"X-Forwarded-For": CLIENT})) == CLIENT


def test_trusted_hops_ignores_forged_left_entries(monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    # cliente forjou "10.9.9.9"; o proxy confiável anexou o IP real à direita.
    # cadeia = [FORGED, CLIENT, peer]; com hops=1 o cliente é o penúltimo → CLIENT.
    r = _req({"X-Forwarded-For": f"{FORGED}, {CLIENT}"})
    assert client_ip(r) == CLIENT


def test_trusted_hops_two_proxies(monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    # dois proxies confiáveis; XFF = [cliente, proxy1], peer = proxy2
    r = _req({"X-Forwarded-For": f"{CLIENT}, 172.16.0.1"})
    assert client_ip(r) == CLIENT


def test_hops_exceeding_chain_falls_back_to_leftmost(monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "9")
    # menos entradas do que hops (cadeia mais curta que o esperado) → não estoura;
    # devolve a entrada mais à esquerda (o melhor palpite do cliente).
    assert client_ip(_req({"X-Forwarded-For": CLIENT})) == CLIENT


def test_invalid_hops_env_treated_as_zero(monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "nao-numero")
    assert client_ip(_req({"X-Forwarded-For": CLIENT})) == PROXY


# ---- Integração: o rate limit passa a valer por cliente real atrás de proxy ----

REQ_OTP = "/v1/auth/participant/request-otp"


def _seed_participant(TestSession, code):
    from app.core.models import Participant
    with TestSession() as s:
        s.add(Participant(study_code=code)); s.commit()


def test_rate_limit_is_per_real_client_behind_proxy(api, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setenv("OTP_RATE_LIMIT", "1")
    client, TestSession = api
    _seed_participant(TestSession, "P-PROXY")
    # Dois clientes reais distintos (mesmo peer/borda do TestClient) via XFF:
    a = {"X-Forwarded-For": "203.0.113.1"}
    b = {"X-Forwarded-For": "203.0.113.2"}
    # Cada um tem seu próprio bucket: ambos passam na 1ª tentativa...
    assert client.post(REQ_OTP, json={"study_code": "P-PROXY"}, headers=a).status_code == 200
    assert client.post(REQ_OTP, json={"study_code": "P-PROXY"}, headers=b).status_code == 200
    # ...e o cliente A estoura na 2ª (bucket dele, não o global da borda).
    assert client.post(REQ_OTP, json={"study_code": "P-PROXY"}, headers=a).status_code == 429


def test_rate_limit_ignores_xff_without_trusted_proxy(api, monkeypatch):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    monkeypatch.setenv("OTP_RATE_LIMIT", "1")
    client, TestSession = api
    _seed_participant(TestSession, "P-NOPROXY")
    # Sem proxy confiável, XFF é ignorado: os dois "clientes" caem no MESMO bucket (o peer).
    a = {"X-Forwarded-For": "203.0.113.1"}
    b = {"X-Forwarded-For": "203.0.113.2"}
    assert client.post(REQ_OTP, json={"study_code": "P-NOPROXY"}, headers=a).status_code == 200
    assert client.post(REQ_OTP, json={"study_code": "P-NOPROXY"}, headers=b).status_code == 429
