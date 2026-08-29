"""
scripts/purge_otp.py — Expurgo agendado dos desafios de OTP expirados (E2).

Ponto de entrada do job de retenção. Apaga o que **já expirou** há mais de
`OTP_PURGE_GRACE_MIN` minutos (padrão 60) e registra a contagem na auditoria. Duas tabelas,
mesma política de transitórios: `otp_challenge` (E2/ADR-091) e `staff_setup_token`
(convite/redefinição de senha de staff, ADR-094). Só toca em dado **transitório** — nada de
pesquisa, nada de PII (ver `modules/retention/service.py`).

Uso:
    python scripts/purge_otp.py                # usa OTP_PURGE_GRACE_MIN (padrão 60)
    python scripts/purge_otp.py --grace-min 0  # apaga tudo que já expirou
    python scripts/purge_otp.py --dry-run      # só conta, não apaga

Agendamento (o expurgo é diário pela política; ver docs/politica-retencao-descarte.md §4):
    fly ssh console --app sereno-piloto-api -C "python scripts/purge_otp.py"
    # ou cron no host:  0 4 * * *  cd /app && python scripts/purge_otp.py

Idempotente e seguro para rodar com frequência: o critério é absoluto (`expires_at`), então
rodar duas vezes seguidas apaga 0 na segunda. Sai com código 0 em sucesso, 1 em falha —
para o agendador conseguir alertar.
"""
from __future__ import annotations
import argparse
import json
import os
import sys

# Permite rodar como `python scripts/purge_otp.py` (adiciona a raiz do backend ao path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import get_engine  # noqa: E402
from app.core.models import OtpChallenge  # noqa: E402
from app.modules.retention.service import (purge_expired_otp,  # noqa: E402
                                           purge_expired_staff_tokens, DEFAULT_GRACE_MIN)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Expurga credenciais transitórias expiradas: OTP (E2) e tokens de "
                    "convite/redefinição de senha de staff (ADR-094).")
    ap.add_argument("--grace-min", type=int,
                    default=int(os.getenv("OTP_PURGE_GRACE_MIN", str(DEFAULT_GRACE_MIN))),
                    help="Minutos APÓS a expiração antes de apagar (padrão 60).")
    ap.add_argument("--dry-run", action="store_true", help="Só conta; não apaga nada.")
    args = ap.parse_args()

    with Session(get_engine()) as db:
        total = db.scalar(select(func.count()).select_from(OtpChallenge)) or 0
        # Reusa os serviços em transação descartada no dry-run: conta pelo MESMO critério do
        # expurgo real, sem duplicar a regra aqui (duas regras divergiriam com o tempo).
        deleted = purge_expired_otp(db, grace_min=args.grace_min)
        deleted_tokens = purge_expired_staff_tokens(db, grace_min=args.grace_min)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    print(json.dumps({"deleted": deleted, "remaining": total - (0 if args.dry_run else deleted),
                      "staff_tokens_deleted": deleted_tokens,
                      "grace_min": args.grace_min, "dry_run": args.dry_run}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — o agendador precisa de código de saída != 0
        # Sem detalhe do erro no stdout (pode carregar DSN): tipo + mensagem no stderr.
        print(f"purge_otp falhou: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
