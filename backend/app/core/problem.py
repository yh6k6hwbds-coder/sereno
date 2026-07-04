"""
core/problem.py — Erros padronizados em problem+json (RFC 9457).
Toda resposta de erro da API sai neste formato, com o media type correto.
Regra de segurança: mensagens não vazam detalhes internos (stack, PII, o braço).
"""
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

MEDIA = "application/problem+json"
BASE = "https://api.sereno.example/errors/"


class ProblemException(Exception):
    """Erro de aplicação já no formato problem+json."""
    def __init__(self, status: int, title: str, detail: str | None = None, type_: str | None = None):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type_ or (BASE + "about:blank")
        super().__init__(title)


def _problem(status: int, title: str, detail: str | None, type_: str, instance: str) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, "instance": instance}
    if detail:
        body["detail"] = detail
    return JSONResponse(status_code=status, content=body, media_type=MEDIA)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemException)
    async def _handle_problem(request: Request, exc: ProblemException):
        return _problem(exc.status, exc.title, exc.detail, exc.type, request.url.path)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError):
        # Resumo enxuto (campo + mensagem) — sem despejar a estrutura interna inteira.
        errs = exc.errors()
        first = errs[0] if errs else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        detail = f"{loc}: {first.get('msg', 'inválido')}" if loc else "Dados inválidos."
        return _problem(422, "Dados inválidos", detail, BASE + "validation", request.url.path)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException):
        title = exc.detail if isinstance(exc.detail, str) else "Erro"
        return _problem(exc.status_code, title, None, BASE + f"http/{exc.status_code}", request.url.path)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        # Nunca expõe a exceção original ao cliente (evita vazamento).
        return _problem(500, "Erro interno", None, BASE + "internal", request.url.path)
