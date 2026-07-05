#!/bin/sh
# Entrypoint da API: aplica as migrações Alembic e sobe o uvicorn.
# As migrações no deploy garantem o schema versionado (produção NÃO usa create_all).
set -e

echo "[entrypoint] Aplicando migrações (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Iniciando a API (uvicorn)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
