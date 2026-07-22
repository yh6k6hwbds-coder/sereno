"""
modules/sessions/storage.py — Porta de ENTREGA de áudio (A1 → E3/ADR-082).

Abstrai *como* o WAV chega ao cliente, sem tocar na síntese/validação (inegociável #3)
nem no cegamento (inegociável #2). Dois modos, escolhidos por ``AUDIO_DELIVERY``:

  - ``inline`` (padrão): o backend transmite os bytes pelo caminho autenticado — o
    comportamento A1 permanece **inalterado**.
  - ``signed-url``: o backend devolve uma **URL assinada de curta duração** e a
    transferência sai do caminho autenticado. Prepara o offload para storage em nuvem —
    um presign de S3 encaixa nesta MESMA porta depois, sem mexer no router (Fase E).

A chave do objeto é o ``content_hash`` **opaco** (nunca revela ativo/sham; o cliente já
o recebe no start da sessão). A assinatura é HMAC-SHA256 sobre ``content_hash|exp`` com
uma subchave dedicada (derivada de ``AUDIO_URL_SIGNING_KEY`` ou, na falta, do
``JWT_SECRET`` — nunca a própria chave do JWT em claro). Verificação em tempo constante.
Nada aqui expõe ou depende do braço. Ver ADR-082.

**Rotação da chave de assinatura (ADR-090):** mesma forma do ``keyring`` da PII — a chave
**ativa** (``AUDIO_URL_SIGNING_KEY``) é a única que ASSINA; chaves **anteriores**
(``AUDIO_URL_SIGNING_KEYS_PREVIOUS``, separadas por vírgula) seguem aceitas só para
**verificar**. Sem isso, trocar a chave invalidaria na hora toda URL já entregue e
derrubaria a sessão em curso de quem está ouvindo; com isso, a janela de convivência é o
próprio TTL da URL (minutos) — passado ele, basta remover a anterior. O ambiente é lido a
cada chamada (rotação sem reiniciar o processo).
"""
from __future__ import annotations
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

from app.core import auth

# TTL padrão da URL assinada (segundos). Curto de propósito: a URL é uma capability.
_DEFAULT_TTL_S = 300


def signed_delivery_enabled() -> bool:
    """True quando ``AUDIO_DELIVERY`` pede entrega por URL assinada (lido em tempo de uso)."""
    return os.getenv("AUDIO_DELIVERY", "inline").strip().lower() in ("signed", "signed-url", "url")


def _ttl_s() -> int:
    try:
        return max(int(os.getenv("AUDIO_URL_TTL_S", str(_DEFAULT_TTL_S))), 1)
    except ValueError:
        return _DEFAULT_TTL_S


def _derive(raw: str) -> bytes:
    """Subchave dedicada à assinatura de URLs de áudio (não reusa a chave do JWT em claro)."""
    return hashlib.sha256(("sereno-audio-url:" + raw).encode()).digest()


def _signing_key() -> bytes:
    """Chave ATIVA — a única que assina."""
    return _derive(os.getenv("AUDIO_URL_SIGNING_KEY") or auth.JWT_SECRET)


def _verification_keys() -> list[bytes]:
    """Ativa + anteriores (verify-only), na ordem. Rotação sem invalidar URL já emitida."""
    keys = [_signing_key()]
    for raw in (os.getenv("AUDIO_URL_SIGNING_KEYS_PREVIOUS") or "").split(","):
        raw = raw.strip()
        if raw:
            keys.append(_derive(raw))
    return keys


def _sign_with(key: bytes, content_hash: str, exp: int) -> str:
    return hmac.new(key, f"{content_hash}|{exp}".encode(), hashlib.sha256).hexdigest()


def _sign(content_hash: str, exp: int) -> str:
    return _sign_with(_signing_key(), content_hash, exp)


def build_signed_path(content_hash: str, ttl_s: int | None = None) -> str:
    """Caminho relativo assinado para o áudio: ``/v1/audio/<hash>?exp=..&sig=..``.

    Relativo de propósito — funciona atrás de qualquer host/túnel/CDN sem embutir a
    origem. A troca por um presign absoluto de nuvem é local a esta função."""
    exp = int(time.time()) + (ttl_s if ttl_s is not None else _ttl_s())
    qs = urlencode({"exp": exp, "sig": _sign(content_hash, exp)})
    return f"/v1/audio/{content_hash}?{qs}"


def verify_signed(content_hash: str, exp: str | int | None, sig: str | None) -> bool:
    """Valida a assinatura e a validade. Falha (sem distinguir o motivo) se inválida/expirada.

    Aceita a chave ativa **ou** uma anterior (rotação). Sem short-circuit: todas as
    candidatas são comparadas em tempo constante, para não temporizar qual chave casou."""
    if not sig or exp is None:
        return False
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_i < int(time.time()):
        return False                                  # expirada
    ok = False
    for key in _verification_keys():
        ok |= hmac.compare_digest(_sign_with(key, content_hash, exp_i), sig)
    return ok
