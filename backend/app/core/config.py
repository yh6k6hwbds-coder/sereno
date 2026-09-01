"""
core/config.py — Ambiente (dev/produção) e validação de runtime (fail-fast em produção).

Centraliza a distinção dev/produção (``APP_ENV``) e as invariantes que **não podem valer
em produção**, porque violam decisões inegociáveis do ``CLAUDE.md``:

  - a **chave selada** A/B→condição (``ARM_CONDITION_MAP``) precisa ser custodiada por fora
    e **jamais** cair no default público — do contrário o braço codificado (exportado como
    A/B) revela ativo/sham e o cegamento cai (inegociável #2);
  - ``EMAIL_DEV_CONSOLE`` imprime o código OTP no log — proibido em produção (inegociável #6).

``validate_runtime_config()`` é chamada no startup (``create_app``) e **levanta** em produção
se algo acima estiver errado; em dev/teste é no-op (defaults de conveniência valem). A
recusa é reforçada em profundidade no ponto de uso (``sessions.service._sealed_map``).
"""
from __future__ import annotations
import os

# Default do mapa selado aceitável SÓ em dev/teste. Em produção é recusado (o mapa real é
# um sorteio custodiado, setado como secret e nunca versionado). Ver ADR-077.
DEV_ARM_CONDITION_MAP = "A:active,B:sham"


# G3 — "limite máximo imposto por software" do protocolo. O ganho digital com que o cliente
# reproduz é declarado ao iniciar a sessão e recusado acima deste teto; o participante não tem
# como alterá-lo pelo aplicativo. O valor absoluto em dB(A) depende do transdutor e sai da
# calibração em acoplador de orelha (etapa (i) do protocolo) — daí ser configurável por
# ambiente, e não uma constante escondida no código.
DEFAULT_AUDIO_MAX_GAIN = 1.0

# G1 — formato do artefato de áudio servido. FLAC é sem perdas (o PCM decodificado é
# idêntico ao do WAV, inegociável #3) e derruba os 230 MB de uma sessão de 20 min para
# ~33 MB, o que é a diferença entre o piloto rodar em 4G e não rodar. ``wav`` continua
# disponível para depuração e para ambiente sem o codificador.
DEFAULT_AUDIO_FORMAT = "flac"
AUDIO_FORMATS = ("flac", "wav")

# G4 — a verificação dicótica de fones precisa de mais de uma rodada: com uma só, quem
# chutasse acertaria metade das vezes. Duas rodadas deixam o acerto por acaso em 25%.
MIN_HEADPHONE_CHECK_ROUNDS = 2

# G7 — blocos permutados de tamanho VARIÁVEL (4 e 6), como o protocolo especifica. Fica aqui,
# e não como constante no router, porque é parâmetro de protocolo: mudá-lo é emenda, e o valor
# em vigor precisa ser legível junto às demais invariantes do estudo.
DEFAULT_ALLOCATION_BLOCK_SIZES = (4, 6)
LEGACY_BLOCK_SIZE_VAR = "ALLOCATION_BLOCK_SIZE"


def allocation_block_sizes() -> tuple[int, ...]:
    """Tamanhos de bloco permitidos na randomização (``ALLOCATION_BLOCK_SIZES``, ex. "4,6")."""
    # A variável ANTIGA (singular) fixava o bloco. Ignorá-la em silêncio seria trocar a
    # randomização de um ambiente que a define sem que ninguém percebesse — e a sequência de
    # alocação é auditada. Melhor recusar subir e obrigar a troca explícita.
    if os.getenv(LEGACY_BLOCK_SIZE_VAR) is not None:
        raise InsecureConfigError(
            f"{LEGACY_BLOCK_SIZE_VAR} não é mais lida: o protocolo pede blocos de tamanho "
            "variável (G7). Substitua por ALLOCATION_BLOCK_SIZES (ex.: \"4,6\").")
    raw = os.getenv("ALLOCATION_BLOCK_SIZES")
    if not raw or not raw.strip():
        return DEFAULT_ALLOCATION_BLOCK_SIZES
    try:
        sizes = tuple(sorted({int(p) for p in raw.split(",") if p.strip()}))
    except ValueError:
        raise InsecureConfigError(f"ALLOCATION_BLOCK_SIZES inválido: {raw!r}") from None
    if not sizes or any(b <= 0 or b % 2 != 0 for b in sizes):
        raise InsecureConfigError(
            "ALLOCATION_BLOCK_SIZES deve listar inteiros pares positivos (ex.: \"4,6\").")
    return sizes


def audio_max_gain() -> float:
    """Teto de ganho digital aceito ao iniciar sessão (0 < g <= 1)."""
    raw = os.getenv("AUDIO_MAX_GAIN")
    if not raw:
        return DEFAULT_AUDIO_MAX_GAIN
    try:
        valor = float(raw)
    except ValueError:
        raise InsecureConfigError(f"AUDIO_MAX_GAIN inválido: {raw!r}") from None
    if not 0.0 < valor <= 1.0:
        raise InsecureConfigError("AUDIO_MAX_GAIN deve estar em (0, 1].")
    return valor


def audio_calibrated_spl_dba() -> float | None:
    """Nível em dB(A) medido em ACOPLADOR DE ORELHA com o ganho digital em 1,0 (G9).

    ``None`` = a calibração da etapa (i) do protocolo ainda não foi feita, e a dose de
    exposição é estimada no nível **prescrito** (60 dB(A)), não medido — ver
    ``core.hearing``. Não há default numérico de propósito: um valor plausível chutado aqui
    viraria "dose medida" na tela do participante e num relatório ao CEP."""
    raw = os.getenv("AUDIO_CALIBRATED_SPL_DBA")
    if not raw or not raw.strip():
        return None
    try:
        valor = float(raw)
    except ValueError:
        raise InsecureConfigError(f"AUDIO_CALIBRATED_SPL_DBA inválido: {raw!r}") from None
    # Faixa de sanidade larga: fora dela é erro de digitação (dBFS no lugar de dB(A), por
    # exemplo, entraria negativo), e uma dose calculada em cima de um erro de unidade é
    # pior do que não ter dose nenhuma.
    if not 0.0 < valor <= 120.0:
        raise InsecureConfigError(
            "AUDIO_CALIBRATED_SPL_DBA deve ser um nível em dB(A) dentro de (0, 120].")
    return valor


def audio_format() -> str:
    """Formato do áudio materializado e servido (``flac`` por padrão)."""
    raw = (os.getenv("AUDIO_FORMAT") or DEFAULT_AUDIO_FORMAT).strip().lower()
    if raw not in AUDIO_FORMATS:
        raise InsecureConfigError(
            f"AUDIO_FORMAT inválido: {raw!r} (esperado {' ou '.join(AUDIO_FORMATS)}).")
    return raw


class InsecureConfigError(RuntimeError):
    """Config que violaria uma decisão inegociável em produção (fail-fast no startup)."""


def app_env() -> str:
    return os.getenv("APP_ENV", "dev").strip().lower()


def is_production() -> bool:
    return app_env() in ("production", "prod")


def env_truthy(v: str | None) -> bool:
    # Mesma semântica de "ligado" usada pelo email.py: qualquer valor não-vazio conta,
    # exceto os desligamentos explícitos comuns.
    return bool(v) and v.strip().lower() not in ("0", "false", "no", "off")


def security_fail_open() -> bool:
    """Postura quando o backend de rate limit/denylist (Redis) está indisponível.

    ``True`` (padrão) = **fail-open**: prioriza disponibilidade — uma queda do Redis NÃO
    derruba login/OTP nem toda rota autenticada. O rate limit deixa passar e a denylist
    trata o token como não-revogado (a defesa fica best-effort durante a falha; tokens de
    acesso têm TTL curto). ``False`` = **fail-closed**: prioriza a defesa (429/401) ao custo
    de disponibilidade. Configurável por ``SECURITY_FAIL_OPEN``. Ver ADR-079."""
    return env_truthy(os.getenv("SECURITY_FAIL_OPEN", "1"))


def validate_runtime_config() -> None:
    """Falha rápido se a config de produção violar uma decisão inegociável.

    No-op fora de produção (``APP_ENV`` != production/prod), onde os defaults de
    conveniência são intencionais."""
    if not is_production():
        return
    problems: list[str] = []
    if not os.getenv("ARM_CONDITION_MAP"):
        problems.append(
            "ARM_CONDITION_MAP ausente: a chave selada A/B→condição não pode cair no default "
            "público (quebraria o cegamento — inegociável #2). Configure-a como secret "
            "custodiado, fora do repositório (ver ADR-077).")
    if env_truthy(os.getenv("EMAIL_DEV_CONSOLE")):
        problems.append(
            "EMAIL_DEV_CONSOLE ligado em produção: imprimiria o código OTP no log "
            "(inegociável #6). Remova e configure SMTP real.")
    if problems:
        raise InsecureConfigError(" | ".join(problems))
