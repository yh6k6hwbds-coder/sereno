"""
app/main.py — Ponto de entrada da API (FastAPI, monólito modular).

Monta os módulos sob /v1, instala os handlers problem+json e expõe health/ready.
Rodar: `uvicorn app.main:app --reload` (a partir de backend/).

Aviso: ferramenta complementar de pesquisa; não substitui cuidado profissional.
"""
from __future__ import annotations
import os
import time
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import get_db

from app.core.problem import install_problem_handlers, ProblemException
from app.core.logging import setup_logging, request_logger
from app.core.config import validate_runtime_config
from app.core import metrics, readiness

# Roteadores por domínio (fronteiras explícitas do monólito modular).
from app.modules.identity.router import router as identity_router
from app.modules.consent.router import router as consent_router
from app.modules.screening.router import router as screening_router
from app.modules.allocation.router import router as allocation_router
from app.modules.sessions.router import router as sessions_router, audio_router
from app.modules.instruments.router import router as instruments_router
from app.modules.recommender.router import router as recommender_router
from app.modules.research.router import router as research_router
from app.modules.audit.router import router as audit_router
from app.modules.participant_auth.router import router as participant_auth_router
from app.modules.staff.router import router as staff_router
from app.modules.contact.router import router as contact_router
from app.modules.data_rights.router import router as data_rights_router
from app.modules.diary.router import router as diary_router
from app.modules.followup.router import router as followup_router
from app.modules.adverse_events.router import router as adverse_events_router
from app.modules.wearables.router import router as wearables_router

API_PREFIX = "/v1"

# CORS por ambiente. Em produção, deixe restrito à origem do app. Em dev, use
# CORS_ALLOW_ORIGIN_REGEX (ex.: "http://localhost:\\d+") para liberar o app local.
ALLOWED_ORIGINS = [o.strip() for o in
                   os.getenv("CORS_ORIGINS", "https://app.sereno.example").split(",") if o.strip()]
CORS_ORIGIN_REGEX = os.getenv("CORS_ALLOW_ORIGIN_REGEX") or None


def create_app() -> FastAPI:
    setup_logging()
    # Fail-fast: em produção, recusa subir com config que quebre uma decisão inegociável
    # (chave selada no default público; OTP em log). No-op em dev/teste.
    validate_runtime_config()
    app = FastAPI(
        title="Sereno API",
        version="1.0.0",
        description="API do piloto de neuromodulação não invasiva. Ferramenta complementar; "
                    "não substitui cuidado profissional. Erros em problem+json (RFC 9457).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,          # nunca "*": dados sensíveis
        allow_origin_regex=CORS_ORIGIN_REGEX,   # dev: liberar http://localhost:<porta>
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def _observe_requests(request: Request, call_next):
        # Observabilidade SEM PII: só método/caminho/status/latência (nunca corpo nem braço).
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        # Log: caminho CONCRETO (pode ter UUID pseudônimo — útil p/ depurar; ver ADR-067).
        request_logger.info("request", extra={"extra_fields": {
            "method": request.method, "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(elapsed * 1000, 1)}})
        # Métrica: TEMPLATE da rota (baixa cardinalidade); o próprio /metrics não se mede.
        if request.url.path != "/metrics":
            metrics.observe(method=request.method, path=metrics.route_template(request),
                            status=response.status_code, duration_s=elapsed)
        return response

    install_problem_handlers(app)

    @app.get("/health", tags=["infra"])
    async def health():
        # Liveness puro: o processo está de pé. NÃO toca em dependência (senão uma queda
        # de banco viraria reinício em loop, que não conserta banco nenhum).
        return {"status": "ok"}

    @app.get("/ready", tags=["infra"])
    async def ready(response: Response, db=Depends(get_db)):
        # Readiness REAL (ADR-090): sonda banco (obrigatório) e Redis (peso conforme a
        # postura do ADR-079). Não pronto → 503, para o roteador parar de mandar tráfego.
        # Usa a sessão da REQUISIÇÃO — sondar uma engine à parte atestaria uma conexão
        # que nenhum endpoint usa.
        ok, body = readiness.probe(db)
        response.status_code = 200 if ok else 503
        return body

    @app.get("/metrics", tags=["infra"])
    async def prometheus_metrics(request: Request):
        # Só agregados (sem PII/braço). Guard opcional: se METRICS_TOKEN estiver setado,
        # exige `Authorization: Bearer <token>` (defesa em profundidade). Ver ADR-080.
        token = os.getenv("METRICS_TOKEN")
        if token and request.headers.get("authorization") != f"Bearer {token}":
            raise ProblemException(401, "Não autorizado", "Métricas exigem token.")
        body, content_type = metrics.render()
        return Response(content=body, media_type=content_type)

    for r in (identity_router, consent_router, screening_router, allocation_router,
              sessions_router, audio_router, instruments_router, recommender_router,
              research_router, audit_router, participant_auth_router, staff_router,
              contact_router, data_rights_router, diary_router, followup_router,
              adverse_events_router, wearables_router):
        app.include_router(r, prefix=API_PREFIX)

    return app


app = create_app()
