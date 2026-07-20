"""
core/metrics.py — Métricas Prometheus SEM PII, braço nem alta cardinalidade.

Complementa os logs JSON (``core/logging.py``, ADR-067) com contadores/latência agregados
para observabilidade (ADR-080). Regras:

  - **rótulo por *template* de rota** (ex.: ``/sessions/{session_id}/audio``), **nunca** o
    caminho concreto — um UUID no caminho explodiria a cardinalidade e não agrega nada. O
    template é relativo ao mount (o prefixo constante ``/v1`` das rotas de API não entra —
    não distingue endpoints); cada router mantém seu próprio prefixo (``/sessions``, ``/research``…),
    então não há colisão. Caminhos sem rota casada (404) colapsam em ``<unmatched>`` (defesa
    contra cardinalidade dirigida);
  - só ``method``/``path``(template)/``status`` — **nenhum** corpo, PII ou condição (ativo/sham);
  - registro **dedicado** (``CollectorRegistry``): expõe só estas métricas, sem coletores de
    processo/plataforma (ruído e acoplamento).
"""
from __future__ import annotations

from fastapi import Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()
UNMATCHED = "<unmatched>"

REQUESTS = Counter(
    "http_requests_total",
    "Total de requisições HTTP por método, template de rota e status.",
    ["method", "path", "status"],
    registry=REGISTRY,
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latência das requisições HTTP (segundos) por método e template de rota.",
    ["method", "path"],
    registry=REGISTRY,
)
# Entrega de e-mail (OTP/alerta): só o DESFECHO agregado — nunca destinatário, assunto ou
# corpo (o código OTP jamais é observado). Torna visível a perda silenciosa de entrega (ADR-085).
EMAILS = Counter(
    "emails_total",
    "Total de tentativas de entrega de e-mail por desfecho (sent|failed).",
    ["outcome"],
    registry=REGISTRY,
)


def observe_email(outcome: str) -> None:
    """Conta uma entrega de e-mail por desfecho ('sent'|'failed'). Sem PII/corpo."""
    EMAILS.labels(outcome=outcome).inc()


def route_template(request: Request) -> str:
    """Template da rota casada (baixa cardinalidade); ``<unmatched>`` se nenhuma casou."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or UNMATCHED


def observe(*, method: str, path: str, status: int, duration_s: float) -> None:
    REQUESTS.labels(method=method, path=path, status=str(status)).inc()
    LATENCY.labels(method=method, path=path).observe(duration_s)


def render() -> tuple[bytes, str]:
    """Exposição no formato texto do Prometheus (corpo, content-type)."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
