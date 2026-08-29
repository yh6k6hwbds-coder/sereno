"""
core/keyring.py — Custódia e resolução de chaves de cifra de PII (porta `KeyProvider`).

Abstrai **de onde vem** a chave que cifra a PII (`pii_crypto`), separando custódia de uso.
Mesmo padrão das outras portas do projeto (`EmailSender`, `AudioStorage`, `WearableSink`):

  - `EnvKeyProvider` (**padrão**): a chave (KEK) vem do ambiente/secret (`PII_ENC_KEY`),
    custódia atual do piloto. Lê o ambiente **a cada chamada** — permite rotação sem
    reiniciar o processo.
  - `VaultTransitKeyProvider` (`KEY_PROVIDER=vault`, ADR‑095): implementa a MESMA porta
    contra o **motor Transit do HashiCorp Vault** — a KEK nunca sai do cofre; a app só pede
    wrap/unwrap. É a "custódia evolui para KMS" prometida no ADR‑059, agora construída.
    Dado cifrado antes da adoção continua legível: `unwrap` de id não‑Vault delega ao env.

**Rotação:** cada ciphertext carrega o **id da chave** que o cifrou (ver `pii_crypto`). A chave
ativa (`PII_ENC_KEY` + `PII_ENC_KEY_ID`) cifra o novo; chaves **aposentadas** (`PII_ENC_KEYS`,
`id:base64,...`) seguem disponíveis só para **decifrar** o que já existe. Assim dá para trocar a
chave sem re‑cifrar tudo de uma vez. Nada aqui é logado; chave ausente/ inválida falha explícito."""
from __future__ import annotations
import base64
import os
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_KEY_ID = "env1"
_ACTIVE_ENV = "PII_ENC_KEY"
_ACTIVE_ID_ENV = "PII_ENC_KEY_ID"
_RETIRED_ENV = "PII_ENC_KEYS"      # "id:base64,id:base64" — aposentadas (decrypt-only na rotação)


class KeyMissing(RuntimeError):
    """Chave ausente/ inválida/ desconhecida — falha explícita, sem fallback inseguro."""


def _decode(raw: str, label: str) -> bytes:
    try:
        key = base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise KeyMissing(f"{label} não é base64 válido.") from e
    if len(key) != 32:
        raise KeyMissing(f"{label} deve ter 32 bytes (AES-256).")
    return key


class KeyProvider(Protocol):
    def active(self) -> tuple[str, bytes]: ...   # (key_id, KEK de 32 bytes) — v1/legado
    def by_id(self, key_id: str) -> bytes: ...    # resolve a KEK p/ decifrar v1/legado
    # Envelope (ADR-088): a KEK **embrulha/desembrulha** a DEK; o blob é OPACO ao chamador.
    # Num KMS real é aqui que a app chama wrap/unwrap — a KEK nunca sai do HSM.
    def wrap(self, dek: bytes, *, aad: bytes) -> tuple[str, bytes]: ...     # -> (key_id, blob)
    def unwrap(self, key_id: str, blob: bytes, *, aad: bytes) -> bytes: ...  # -> dek


class EnvKeyProvider:
    """Chaves via ambiente/secret. Lê o ambiente a cada chamada (rotação sem reiniciar).

    O envelope é feito **localmente** (AES-GCM com a KEK do ambiente). Um KmsKeyProvider
    faria o mesmo chamando o KMS — a KEK nunca exposta à aplicação."""

    def active(self) -> tuple[str, bytes]:
        raw = os.getenv(_ACTIVE_ENV)
        if not raw:
            raise KeyMissing(f"{_ACTIVE_ENV} não configurada (base64 de 32 bytes).")
        kid = (os.getenv(_ACTIVE_ID_ENV) or DEFAULT_KEY_ID).strip() or DEFAULT_KEY_ID
        return kid, _decode(raw, _ACTIVE_ENV)

    def by_id(self, key_id: str) -> bytes:
        active_id, active_key = self.active()
        if key_id == active_id:
            return active_key
        for pair in (os.getenv(_RETIRED_ENV) or "").split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            kid, b64 = pair.split(":", 1)
            if kid.strip() == key_id:
                return _decode(b64.strip(), f"{_RETIRED_ENV}[{key_id}]")
        raise KeyMissing(
            f"chave de id '{key_id}' indisponível (rotação: verifique {_RETIRED_ENV}).")

    def wrap(self, dek: bytes, *, aad: bytes) -> tuple[str, bytes]:
        """Embrulha a DEK com a KEK ativa. Blob = ``nonce(12) || dek_cifrada+tag`` (opaco)."""
        key_id, kek = self.active()
        nonce = os.urandom(12)
        return key_id, nonce + AESGCM(kek).encrypt(nonce, dek, aad)

    def unwrap(self, key_id: str, blob: bytes, *, aad: bytes) -> bytes:
        """Desembrulha a DEK com a KEK de ``key_id`` (rotação: pode ser uma aposentada)."""
        kek = self.by_id(key_id)
        nonce, wrapped = blob[:12], blob[12:]
        return AESGCM(kek).decrypt(nonce, wrapped, aad)


class VaultTransitKeyProvider:
    """Custódia real em **HashiCorp Vault (motor Transit)** — a KEK nunca sai do cofre.

    Implementa a MESMA porta do `EnvKeyProvider`, mas `wrap`/`unwrap` viram chamadas ao Vault:
    a aplicação manda a DEK e recebe o blob embrulhado, sem jamais ver a KEK. É a promessa do
    ADR-087/088 cumprida (F4.1/ADR-095).

    **Mapeamento do AAD:** o Transit não tem AAD; tem ``context``, das *derived keys*. Com a
    chave criada com ``derived=true``, o contexto participa da derivação — decifrar com outro
    contexto **falha**, que é exatamente a garantia que o AAD dá aqui (o valor fica preso ao
    participante e ao campo). Por isso a chave **precisa** ser criada com ``derived=true``:
    ``vault write -f transit/keys/<nome> derived=true``.

    **Rotação** é do Vault: o ciphertext carrega a versão (``vault:v2:...``) e o decrypt
    continua funcionando após ``rotate``. Por isso o ``key_id`` guardado no token não precisa
    (nem deve) carregar a versão.

    **Migração:** ``unwrap`` de um ``key_id`` que não é do Vault, ``by_id`` e ``active``
    delegam ao ``fallback`` (env, por padrão) — dado cifrado antes da adoção do Vault
    continua legível, sem re-cifrar tudo num big bang."""

    PREFIX = "vault:"

    def __init__(self, *, addr: str, token: str, key_name: str, mount: str = "transit",
                 timeout_s: float = 5.0, client=None,
                 fallback: KeyProvider | None = None) -> None:
        self._addr = addr.rstrip("/")
        self._token = token                      # NUNCA logado nem posto em exceção
        self._key = key_name
        self._mount = mount.strip("/")
        self._timeout = timeout_s
        self._client = client
        self._fallback = fallback or EnvKeyProvider()

    # -- porta ------------------------------------------------------------
    def active(self) -> tuple[str, bytes]:
        """Só existe para o formato LEGADO (KEK cifrando direto). Delega ao fallback.

        Com Vault não há "chave ativa em bytes" — é esse o ponto. Cifrar novo sempre passa
        por ``wrap``."""
        return self._fallback.active()

    def by_id(self, key_id: str) -> bytes:
        """Chaves v1/legado (bytes) — só o fallback pode resolvê-las."""
        if key_id.startswith(self.PREFIX):
            raise KeyMissing(
                f"'{key_id}' é uma chave custodiada no Vault: a KEK não sai do cofre. "
                "Tokens v1 (KEK direta) precisam ser migrados para envelope (ADR-088).")
        return self._fallback.by_id(key_id)

    def wrap(self, dek: bytes, *, aad: bytes) -> tuple[str, bytes]:
        data = self._call("encrypt", {
            "plaintext": base64.b64encode(dek).decode("ascii"),
            "context": base64.b64encode(aad).decode("ascii"),
        })
        ciphertext = data.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext:
            raise KeyMissing("Vault não devolveu ciphertext no wrap.")
        return f"{self.PREFIX}{self._mount}:{self._key}", ciphertext.encode("utf-8")

    def unwrap(self, key_id: str, blob: bytes, *, aad: bytes) -> bytes:
        if not key_id.startswith(self.PREFIX):
            # Registro anterior à adoção do Vault: segue legível pelo provedor antigo.
            return self._fallback.unwrap(key_id, blob, aad=aad)
        data = self._call("decrypt", {
            "ciphertext": blob.decode("utf-8"),
            "context": base64.b64encode(aad).decode("ascii"),
        })
        plaintext = data.get("plaintext")
        if not isinstance(plaintext, str) or not plaintext:
            raise KeyMissing("Vault não devolveu plaintext no unwrap.")
        return base64.b64decode(plaintext)

    # -- transporte -------------------------------------------------------
    def _call(self, op: str, payload: dict) -> dict:
        """POST no Transit. Erros viram ``KeyMissing`` **sem** eco do token nem do corpo."""
        import httpx
        url = f"{self._addr}/v1/{self._mount}/{op}/{self._key}"
        client = self._client
        try:
            if client is None:
                with httpx.Client(timeout=self._timeout) as c:
                    resp = c.post(url, json=payload,
                                  headers={"X-Vault-Token": self._token})
            else:
                resp = client.post(url, json=payload,
                                   headers={"X-Vault-Token": self._token})
            if resp.status_code >= 400:
                # O corpo de erro do Vault pode ecoar o contexto — só o status sai daqui.
                raise KeyMissing(f"Vault recusou '{op}' (HTTP {resp.status_code}).")
            return resp.json().get("data") or {}
        except KeyMissing:
            raise
        except Exception as e:  # noqa: BLE001 — rede/JSON/timeout: falha explícita e opaca
            raise KeyMissing(f"Vault indisponível em '{op}' ({type(e).__name__}).") from None


_provider: KeyProvider | None = None


def _build_from_env() -> KeyProvider:
    """`KEY_PROVIDER=vault` → Transit; qualquer outro valor (padrão) → ambiente/secret.

    Falta de `VAULT_ADDR`/`VAULT_TOKEN` no modo vault **levanta**: cair calado para o env
    daria a impressão de custódia em HSM sem que ela exista — pior que não ter Vault."""
    if (os.getenv("KEY_PROVIDER") or "env").strip().lower() != "vault":
        return EnvKeyProvider()
    addr, token = os.getenv("VAULT_ADDR"), os.getenv("VAULT_TOKEN")
    if not addr or not token:
        raise KeyMissing("KEY_PROVIDER=vault exige VAULT_ADDR e VAULT_TOKEN.")
    return VaultTransitKeyProvider(
        addr=addr, token=token,
        key_name=os.getenv("VAULT_TRANSIT_KEY", "sereno-pii-kek"),
        mount=os.getenv("VAULT_TRANSIT_MOUNT", "transit"),
        timeout_s=float(os.getenv("VAULT_TIMEOUT_S", "5")),
    )


def get_key_provider() -> KeyProvider:
    global _provider
    if _provider is None:
        _provider = _build_from_env()
    return _provider


def set_key_provider(provider: KeyProvider | None) -> None:
    """Injeta um provedor (teste / adaptador KMS) ou força reconstrução (None)."""
    global _provider
    _provider = provider
