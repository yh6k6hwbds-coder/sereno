"""
scripts/sweep_discontinuations.py — Varredura semanal da regra de adesão da 2ª semana (F3.11).

O protocolo descontinua quem chega ao fim da 2ª semana com **adesão inferior a 50%**. A
avaliação preguiçosa (ao iniciar sessão, ao abrir a tela inicial) nunca alcança justamente
**quem parou de abrir o aplicativo** — que é o caso que a regra existe para pegar. Por isso
existe a varredura; e enquanto ninguém a executa, ela não acontece.

**Por que um script, se já há `POST /v1/discontinuations/evaluate`?** Porque o endpoint exige
token de staff, e o login de staff exige **MFA** (TOTP) — de propósito. Agendar a chamada
obrigaria a guardar credencial e segredo de segundo fator no agendador, o que esvaziaria o MFA
para ganhar uma tarefa de rotina. O script roda **dentro do servidor**, com o mesmo acesso ao
banco que a aplicação já tem, e não precisa de credencial nenhuma.

O endpoint continua existindo e é o caminho quando uma pessoa quer rodar a varredura na hora.
Os dois chamam a **mesma** função de serviço: a regra vive em um lugar só.

Uso:
    python scripts/sweep_discontinuations.py             # aplica a regra
    python scripts/sweep_discontinuations.py --dry-run   # só diz quantos SERIAM descontinuados

Agendamento (semanal; a janela do T2 abre ao fim da 2ª semana — ADR-106):
    fly ssh console --app sereno-piloto-api -C "python scripts/sweep_discontinuations.py"
    # ou cron no host:  0 5 * * 1  cd /app && python scripts/sweep_discontinuations.py

Idempotente: descontinuação é **uma por participante**, então rodar duas vezes seguidas
descontinua 0 na segunda. Sai com código 0 em sucesso e 1 em falha — para o agendador alertar.

**A saída não nomeia ninguém.** Sai a contagem, e o registro de cada descontinuação (com o
motivo e as sessões que a motivaram) fica na tabela e na trilha de auditoria, onde a equipe lê
pelo `GET /v1/discontinuations`. Log de agendador é lido por quem opera infraestrutura, não
necessariamente por quem tem acesso ao dado do estudo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

# Permite rodar como `python scripts/sweep_discontinuations.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session                                    # noqa: E402

from app.core.db import get_engine                                    # noqa: E402
from app.modules.progress import service as progress                  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Aplica a regra de adesão da 2ª semana a quem está ativo (F3.11/ADR-106).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Conta quantos seriam descontinuados; não grava nada.")
    args = ap.parse_args()

    agora = dt.datetime.now(dt.timezone.utc)
    with Session(get_engine()) as db:
        # Mesma função que o endpoint chama — a regra não é reescrita aqui. No dry-run a
        # transação é descartada, então a contagem sai pelo critério REAL, sem duplicar regra.
        saidas = progress.sweep_week2(db, agora)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    print(json.dumps({"evaluated_at": agora.isoformat(),
                      "discontinued": len(saidas),
                      "dry_run": args.dry_run}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — o agendador precisa de código de saída != 0
        # Sem detalhe no stdout (pode carregar DSN): tipo do erro no stderr.
        print(f"sweep_discontinuations falhou: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
