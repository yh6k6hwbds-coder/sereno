"""
core/client_ip.py — Resolução do IP real do cliente atrás de proxy confiável.

Atrás de um proxy/borda (Fly.io, balanceador), ``request.client.host`` é o IP do
**proxy**, não do participante. Sem tratar isso, dois efeitos ruins em produção:

  - o **rate limit por IP** (``core/rate_limit.py``) vira um bucket global — todos os
    usuários compartilham o IP da borda e a defesa contra força-bruta cai (ADR-064);
  - o ``ip_address`` gravado no **consentimento** registra o proxy, não quem consentiu.

Cabeçalhos de encaminhamento são **falsificáveis pelo cliente**, então NUNCA se confia
neles por padrão. A confiança é *opt-in* e explícita, por ambiente:

  - ``CLIENT_IP_HEADER`` — nome de um cabeçalho **de confiança única** que a plataforma
    injeta e **sobrescreve** (à prova de spoof). Na Fly é ``Fly-Client-IP``. Tem
    precedência quando definido.
  - ``TRUSTED_PROXY_HOPS`` — número de proxies confiáveis à frente do app. Aplica-se a
    ``X-Forwarded-For``: só as ``hops`` entradas mais à direita (nossos proxies) são
    confiáveis; o cliente é a próxima à esquerda. Valores forjados pelo cliente ficam
    à esquerda dessa posição e são **ignorados**. Padrão ``0`` = não confia em XFF.

Sem nenhuma das duas configurações (dev/sem proxy), usa ``request.client.host`` — o
comportamento seguro anterior. Ver ADR-078.
"""
from __future__ import annotations
import os

from fastapi import Request

UNKNOWN = "unknown"


def _peer(request: Request) -> str:
    return request.client.host if request and request.client else UNKNOWN


def _trusted_hops() -> int:
    try:
        return max(0, int(os.getenv("TRUSTED_PROXY_HOPS", "0")))
    except ValueError:
        return 0


def client_ip(request: Request) -> str:
    """IP real do cliente, respeitando apenas proxies **explicitamente** confiáveis.

    Precedência: (1) ``CLIENT_IP_HEADER`` se configurado e presente; (2) ``X-Forwarded-For``
    com ``TRUSTED_PROXY_HOPS`` > 0; (3) o peer direto (``request.client.host``)."""
    if request is None:
        return UNKNOWN

    # (1) Cabeçalho de confiança única fornecido pela plataforma (ex.: Fly-Client-IP).
    header = os.getenv("CLIENT_IP_HEADER", "").strip()
    if header:
        val = request.headers.get(header)
        if val:
            # Se por acaso vier uma lista, o cliente real é a primeira entrada.
            return val.split(",")[0].strip()

    # (2) X-Forwarded-For, confiando só nas `hops` entradas mais à direita (nossos proxies).
    hops = _trusted_hops()
    if hops > 0:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                # Cadeia completa = [xff..., peer]; a mais à direita é o proxy mais próximo.
                # Com `hops` proxies confiáveis, o cliente está `hops+1` posições do fim.
                chain = parts + [_peer(request)]
                idx = len(chain) - (hops + 1)
                return chain[idx] if idx >= 0 else chain[0]

    # (3) Sem proxy confiável configurado: o peer direto é o mais seguro.
    return _peer(request)
