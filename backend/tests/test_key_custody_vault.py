"""
tests/test_key_custody_vault.py — Adaptador KMS real: Vault Transit (F4.1/ADR-095).

Prova o "Pronto (DoD)", sem rede: um Vault de mentira responde no transporte do httpx.
  (1) round-trip de PII ponta a ponta com a custódia no Vault — a KEK nunca aparece na app;
  (2) o AAD vira `context` da *derived key*: contexto diferente **não** decifra;
  (3) MIGRAÇÃO: dado embrulhado antes (env) continua legível pelo provedor Vault;
  (4) `by_id` de um id do Vault falha explícito (a KEK não sai do cofre);
  (5) Vault fora → `KeyMissing`, sem vazar token nem corpo da resposta na exceção;
  (6) HTTP 4xx/5xx do Vault → `KeyMissing` só com o status;
  (7) `KEY_PROVIDER=vault` sem `VAULT_ADDR`/`VAULT_TOKEN` levanta (não cai calado para env);
  (8) o token do Vault não vai para a mensagem de erro nem para a URL.
"""
from __future__ import annotations
import base64
import json
import uuid

import httpx
import pytest

from app.core import keyring, pii_crypto
from app.core.keyring import (EnvKeyProvider, KeyMissing, VaultTransitKeyProvider,
                              set_key_provider)

_AAD = pii_crypto.aad_for(uuid.uuid4(), "email")
_OUTRO_AAD = pii_crypto.aad_for(uuid.uuid4(), "email")
_KEY_ENV = base64.b64encode(b"E" * 32).decode()
_TOKEN = "s.segredo-do-vault-nao-pode-vazar"


class _VaultFalso:
    """Emula o Transit: guarda (context → plaintext) e devolve um ciphertext opaco.

    Não é criptografia — é o contrato: mesmo contexto decifra, contexto diferente não."""

    def __init__(self, *, status: int = 200, erro: Exception | None = None) -> None:
        self.cofre: dict[str, tuple[str, str]] = {}
        self.status = status
        self.erro = erro
        self.tokens_vistos: list[str] = []
        self.urls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.tokens_vistos.append(request.headers.get("X-Vault-Token", ""))
        self.urls.append(str(request.url))
        if self.erro is not None:
            raise self.erro
        if self.status >= 400:
            return httpx.Response(self.status, json={"errors": ["contexto secreto vazado"]})
        body = json.loads(request.content.decode())
        if request.url.path.endswith("/encrypt/sereno-pii-kek"):
            ref = f"vault:v1:{len(self.cofre)}"
            self.cofre[ref] = (body["context"], body["plaintext"])
            return httpx.Response(200, json={"data": {"ciphertext": ref}})
        guardado = self.cofre.get(body["ciphertext"])
        if guardado is None or guardado[0] != body["context"]:
            # É assim que o Transit se comporta com derived=true e contexto errado.
            return httpx.Response(400, json={"errors": ["unable to decrypt"]})
        return httpx.Response(200, json={"data": {"plaintext": guardado[1]}})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def _provider(vault: _VaultFalso, **kw) -> VaultTransitKeyProvider:
    return VaultTransitKeyProvider(addr="https://vault.interno:8200", token=_TOKEN,
                                   key_name="sereno-pii-kek", client=vault.client(), **kw)


def test_roundtrip_de_pii_com_custodia_no_vault(monkeypatch):
    vault = _VaultFalso()
    set_key_provider(_provider(vault))
    token = pii_crypto.encrypt("Maria de Souza", aad=_AAD)
    assert b"Maria" not in token                       # cifrado, obviamente
    assert pii_crypto.decrypt(token, aad=_AAD) == "Maria de Souza"
    # A app nunca viu a KEK: só mandou/recebeu blobs do cofre.
    assert vault.cofre and all(t == _TOKEN for t in vault.tokens_vistos)
    set_key_provider(None)


def test_contexto_diferente_nao_decifra(monkeypatch):
    vault = _VaultFalso()
    set_key_provider(_provider(vault))
    token = pii_crypto.encrypt("Maria", aad=_AAD)
    # O AAD vira `context`: mover o valor para outro participante/campo não decifra.
    with pytest.raises(KeyMissing):
        pii_crypto.decrypt(token, aad=_OUTRO_AAD)
    set_key_provider(None)


def test_dado_embrulhado_antes_do_vault_continua_legivel(monkeypatch):
    # Cifra com o provedor de ambiente (situação atual do piloto)...
    monkeypatch.setenv("PII_ENC_KEY", _KEY_ENV)
    monkeypatch.setenv("PII_ENC_KEY_ID", "env1")
    set_key_provider(EnvKeyProvider())
    antigo = pii_crypto.encrypt("Antes do Vault", aad=_AAD)

    # ...e passa a usar o Vault: o registro antigo NÃO pode ficar ilegível.
    vault = _VaultFalso()
    set_key_provider(_provider(vault, fallback=EnvKeyProvider()))
    assert pii_crypto.decrypt(antigo, aad=_AAD) == "Antes do Vault"
    # E o novo já nasce embrulhado pelo cofre.
    novo = pii_crypto.encrypt("Depois do Vault", aad=_AAD)
    assert pii_crypto.decrypt(novo, aad=_AAD) == "Depois do Vault"
    assert len(vault.cofre) == 1
    set_key_provider(None)


def test_by_id_de_chave_do_vault_falha_explicito():
    vault = _VaultFalso()
    p = _provider(vault)
    with pytest.raises(KeyMissing, match="não sai do cofre"):
        p.by_id("vault:transit:sereno-pii-kek")


def test_vault_fora_falha_sem_vazar_token():
    vault = _VaultFalso(erro=httpx.ConnectError("sem rota"))
    p = _provider(vault)
    with pytest.raises(KeyMissing) as e:
        p.wrap(b"D" * 32, aad=_AAD)
    assert _TOKEN not in str(e.value) and "ConnectError" in str(e.value)


def test_erro_http_do_vault_nao_ecoa_corpo():
    vault = _VaultFalso(status=403)
    p = _provider(vault)
    with pytest.raises(KeyMissing) as e:
        p.wrap(b"D" * 32, aad=_AAD)
    msg = str(e.value)
    assert "403" in msg
    assert "contexto secreto vazado" not in msg and _TOKEN not in msg


def test_modo_vault_sem_endereco_ou_token_levanta(monkeypatch):
    monkeypatch.setenv("KEY_PROVIDER", "vault")
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    set_key_provider(None)
    # Cair calado para o env daria a impressão de custódia em HSM sem que ela exista.
    with pytest.raises(KeyMissing, match="VAULT_ADDR"):
        keyring.get_key_provider()
    set_key_provider(None)


def test_padrao_continua_sendo_o_ambiente(monkeypatch):
    monkeypatch.delenv("KEY_PROVIDER", raising=False)
    set_key_provider(None)
    assert isinstance(keyring.get_key_provider(), EnvKeyProvider)
    set_key_provider(None)


def test_token_nao_vai_na_url():
    vault = _VaultFalso()
    p = _provider(vault)
    p.wrap(b"D" * 32, aad=_AAD)
    assert all(_TOKEN not in u for u in vault.urls)     # segredo só no cabeçalho
