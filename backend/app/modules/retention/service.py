"""
modules/retention/service.py — Expurgo de dados transitórios (política de retenção, E2).

Primeiro expurgo do item **E2** do `docs/lgpd-nit-checklist.md`: os **desafios de OTP**
(`otp_challenge`), classificados como **transitórios** pela política de retenção
(`docs/politica-retencao-descarte.md` §4: "expurgar registros expirados/consumidos —
proposta diário, nunca > 24 h"). É o único prazo da política que **não depende de aprovação
do CEP**: 5 minutos de TTL é parâmetro técnico de autenticação, não prazo de pesquisa. Por
isso este expurgo pôde ser construído antes dos demais, que aguardam os prazos do item E1.

**A invariante que sustenta a segurança do OTP:** só se apaga o que **já expirou**. Um
desafio ainda válido carrega o contador `attempts` — a defesa contra força bruta de um
código de 6 dígitos (`core/otp.py`). Apagá-lo cedo **zeraria** esse contador e devolveria ao
atacante um novo lote de tentativas: o expurgo viraria um oráculo de reset. O teste
`test_purge_nunca_apaga_desafio_valido` guarda exatamente isso.

Sem PII: a tabela guarda apenas `sha256(código+pepper)` e um id pseudônimo. O evento de
auditoria registra **só a contagem** — o que dá evidência de que o controle rodou (é o que o
RIPD, risco **R-10**, cobra) sem criar um novo registro sobre quem entrou e quando.
"""
from __future__ import annotations
import datetime as dt

from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session

from app.core.models import OtpChallenge
from app.modules.audit.service import record_event

# Carência após a expiração. Não é o prazo de retenção — é folga para não competir com uma
# requisição em voo que ainda esteja lendo o desafio recém-expirado.
DEFAULT_GRACE_MIN = 60


def purge_expired_otp(db: Session, *, grace_min: int = DEFAULT_GRACE_MIN,
                      now: dt.datetime | None = None) -> int:
    """Apaga desafios de OTP **expirados** há mais de ``grace_min``. Devolve quantos saíram.

    Idempotente: rodar de novo em seguida apaga 0. Seguro para rodar com frequência — o
    critério é sempre absoluto (``expires_at``), nunca "os N mais antigos"."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(minutes=max(grace_min, 0))

    # Conta antes de apagar: `rowcount` não é confiável entre dialetos/drivers, e a contagem
    # é o que vai para a auditoria e para o relatório do job.
    n = db.scalar(select(func.count()).select_from(OtpChallenge)
                  .where(OtpChallenge.expires_at < cutoff)) or 0
    if n == 0:
        return 0

    db.execute(delete(OtpChallenge).where(OtpChallenge.expires_at < cutoff))
    # Evidência de que o controle rodou (RIPD R-10). Sem PII e sem participante: só a
    # contagem e a janela aplicada. `actor_type="system"` — não houve operador humano.
    record_event(db, action="otp.purged", resource_type="otp_challenge",
                 actor_type="system", meta={"deleted": n, "grace_min": grace_min})
    return n
