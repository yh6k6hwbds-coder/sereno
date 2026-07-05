# Imagem da API do Sereno (FastAPI). Multi-stage não é necessário: usamos wheels.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependências primeiro (camada cacheável). Todos os pacotes têm wheels em manylinux;
# se algum exigir build, adicionar build-essential aqui.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação (backend/) e o entrypoint.
COPY backend/ ./
RUN chmod +x ./docker-entrypoint.sh

# Usuário não-root (segurança).
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# Aplica migrações e sobe a API (ver docker-entrypoint.sh).
ENTRYPOINT ["./docker-entrypoint.sh"]
