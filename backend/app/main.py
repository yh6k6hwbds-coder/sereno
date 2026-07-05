"""
app/main.py — Ponto de entrada da API (FastAPI, monólito modular).

Monta os módulos sob /v1, instala os handlers problem+json e expõe health/ready.
Rodar: `uvicorn app.main:app --reload` (a partir de backend/).

Aviso: ferramenta complementar de pesquisa; não substitui cuidado profissional.
"""
from __future__ import annotations
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.problem import install_problem_handlers
from app.core.logging import setup_logging, request_logger

# Roteadores por domínio (fronteiras explícitas do monólito modular).
from app.modules.identity.router import router as identity_router
from app.modules.consent.router import router as consent_router
from app.modules.screening.router import router as screening_router
from app.modules.allocation.router import router as allocation_router
from app.modules.sessions.router import router as sessions_router
from app.modules.instruments.router import router as instruments_router
from app.modules.recommender.router import router as recommender_router
from app.modules.research.router import router as research_router
from app.modules.audit.router import router as audit_router
from app.modules.participant_auth.router import router as participant_auth_router
from app.modules.staff.router import router as staff_router
from app.modules.contact.router import router as contact_router
from app.modules.diary.router import router as diary_router
from app.modules.followup.router import router as followup_router
from app.modules.adverse_events.router import router as adverse_events_router

API_PREFIX = "/v1"

# Em produção: carregar de configuração/variáveis de ambiente. CORS RESTRITO.
ALLOWED_ORIGINS = ["https://app.sereno.example"]


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Sereno API",
        version="1.0.0",
        description="API do piloto de neuromodulação não invasiva. Ferramenta complementar; "
                    "não substitui cuidado profissional. Erros em problem+json (RFC 9457).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,          # nunca "*": dados sensíveis
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        # Observabilidade SEM PII: só método/caminho/status/latência (nunca corpo nem braço).
        start = time.perf_counter()
        response = await call_next(request)
        request_logger.info("request", extra={"extra_fields": {
            "method": request.method, "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1)}})
        return response

    install_problem_handlers(app)

    @app.get("/health", tags=["infra"])
    async def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["infra"])
    async def ready():
        # TODO: checar conexões (DB, Redis) antes de reportar pronto.
        return {"status": "ready"}

    for r in (identity_router, consent_router, screening_router, allocation_router,
              sessions_router, instruments_router, recommender_router, research_router,
              audit_router, participant_auth_router, staff_router, contact_router,
              diary_router, followup_router, adverse_events_router):
        app.include_router(r, prefix=API_PREFIX)

    return app


app = create_app()
