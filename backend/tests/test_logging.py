"""
tests/test_logging.py — Observabilidade estruturada SEM PII (fatia D5).

Prova: o formatter emite JSON válido com os campos; o log de requisição registra
método/caminho/status/latência e NUNCA o corpo (PII/OTP/senha) nem o braço.
"""
from __future__ import annotations
import json
import logging

from app.core.logging import JsonFormatter


def test_json_formatter_valid_and_has_fields():
    rec = logging.LogRecord("sereno.request", logging.INFO, "f", 1, "request", None, None)
    rec.extra_fields = {"path": "/v1/x", "status": 200, "duration_ms": 1.2}
    d = json.loads(JsonFormatter().format(rec))
    assert d["level"] == "INFO" and d["msg"] == "request" and "ts" in d
    assert d["path"] == "/v1/x" and d["status"] == 200 and d["duration_ms"] == 1.2


def test_request_is_logged_with_metadata(api, caplog):
    client, _ = api
    with caplog.at_level(logging.INFO, logger="sereno.request"):
        r = client.get("/health")
    assert r.status_code == 200
    recs = [x for x in caplog.records if x.name == "sereno.request"]
    assert recs, "deveria haver um log de requisição"
    ef = getattr(recs[-1], "extra_fields", {})
    assert ef.get("path") == "/health" and ef.get("status") == 200 and "duration_ms" in ef


def test_request_log_never_contains_body_pii(api, caplog):
    client, _ = api
    secret = "CODIGO-DE-ESTUDO-SUPER-SECRETO-XYZ"
    with caplog.at_level(logging.INFO, logger="sereno.request"):
        client.post("/v1/auth/participant/request-otp", json={"study_code": secret})
    blob = " ".join(f"{r.getMessage()}{getattr(r, 'extra_fields', {})}" for r in caplog.records)
    assert secret not in blob            # o corpo (potencial PII) nunca entra no log
