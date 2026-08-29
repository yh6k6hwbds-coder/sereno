"""
scripts/email_worker.py — Worker da fila de e-mail (RQ/Redis, F4.5/ADR-092).

Consome a fila alimentada por `QueueDelivery` (`EMAIL_DELIVERY=queue`) e executa o envio
FORA do processo da API: o request devolve na hora e a mensagem sobrevive a restart/deploy.

Uso:
    EMAIL_DELIVERY=queue REDIS_URL=redis://... python scripts/email_worker.py
    python scripts/email_worker.py --burst      # drena o que há e sai (útil em cron/CI)

Configuração (mesmas variáveis da API, para os dois lados falarem da mesma fila):
    REDIS_URL     — obrigatória; onde a fila vive
    EMAIL_QUEUE   — nome da fila (padrão `sereno-email`)
    SMTP_*        — o worker é quem realmente envia; precisa das credenciais SMTP

O worker NÃO deve subir com `EMAIL_DEV_CONSOLE` em produção (imprimiria o OTP no log —
inegociável #6): a mesma validação de runtime da API é aplicada aqui no boot.

Sai com 0 em encerramento limpo (SIGTERM/SIGINT) e 1 em falha de configuração — para o
supervisor/Fly conseguir distinguir "parei porque mandaram" de "não consegui subir".
"""
from __future__ import annotations
import argparse
import os
import sys

# Permite rodar como `python scripts/email_worker.py` (adiciona a raiz do backend ao path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import validate_runtime_config  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Worker da fila de e-mail (RQ).")
    ap.add_argument("--burst", action="store_true",
                    help="Processa o que estiver na fila e encerra (não fica ouvindo).")
    ap.add_argument("--queue", default=os.getenv("EMAIL_QUEUE", "sereno-email"),
                    help="Nome da fila (padrão: sereno-email).")
    args = ap.parse_args()

    setup_logging()
    # Mesmo fail-fast da API: um worker de produção com console de e-mail ligado imprimiria
    # o código OTP no log do worker — o guard tem de valer nos DOIS processos.
    validate_runtime_config()

    url = os.getenv("REDIS_URL")
    if not url:
        print("email_worker: REDIS_URL não definida (a fila vive no Redis).", file=sys.stderr)
        return 1

    import redis
    from rq import Queue, Worker

    connection = redis.Redis.from_url(url)
    worker = Worker([Queue(args.queue, connection=connection)], connection=connection)
    # `with_scheduler`: sem ele os jobs de RETRY (agendados para +10s/+60s/+300s) nunca
    # voltam para a fila — a durabilidade prometida pelo ADR-092 dependeria de sorte.
    worker.work(burst=args.burst, with_scheduler=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — o supervisor precisa de código de saída != 0
        # Sem detalhe no stdout (pode carregar DSN/credencial): só o tipo, no stderr.
        print(f"email_worker falhou: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
