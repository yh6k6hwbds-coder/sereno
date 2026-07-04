"""
tests/test_notifications.py — Entrega real de OTP por e-mail + alerta de EA (fatia D1).

Prova o "Pronto (DoD)":
  - request-otp DISPARA o envio ao e-mail (decifrado de contact_info) e a verificação segue
    funcionando (extrai o código do e-mail e valida → token);
  - sem contato cadastrado, nada é enviado (resposta segue genérica);
  - evento adverso moderado/grave notifica a equipe (sem PII); leve não notifica;
  - sem configuração de e-mail, o padrão é NullEmailSender (não envia, não vaza o código).
Usa um EmailSender em memória (fake) — nenhum SMTP real é tocado.
"""
from __future__ import annotations
import base64
import re

from app.core.models import Participant, ContactInfo
from app.core import auth, pii_crypto
from app.core.email import MemoryEmailSender, set_email_sender, get_email_sender, EmailMessage

REQ = "/v1/auth/participant/request-otp"
VER = "/v1/auth/participant/verify-otp"
AE = "/v1/adverse-events"
_KEY = base64.b64encode(b"k" * 32).decode()


def _participant_token(TestSession, code="P-AE"):
    with TestSession() as s:
        p = Participant(study_code=code); s.add(p); s.commit(); pid = p.id
    return pid, {"Authorization": f"Bearer {auth.issue_access(str(pid), 'participant')}"}


def test_request_otp_emails_code_and_verify_works(api, monkeypatch):
    monkeypatch.setenv("PII_ENC_KEY", _KEY)
    fake = MemoryEmailSender(); set_email_sender(fake)
    client, TestSession = api
    with TestSession() as s:
        p = Participant(study_code="P-OTP"); s.add(p); s.flush(); pid = p.id
        s.add(ContactInfo(
            participant_id=pid,
            enc_name=pii_crypto.encrypt("Fulano", aad=pii_crypto.aad_for(pid, "name")),
            enc_email=pii_crypto.encrypt("user@example.com", aad=pii_crypto.aad_for(pid, "email")),
        ))
        s.commit()

    assert client.post(REQ, json={"study_code": "P-OTP"}).status_code == 200
    assert len(fake.outbox) == 1
    msg = fake.outbox[0]
    assert msg.to == "user@example.com"
    m = re.search(r"\d{6}", msg.body)
    assert m, "o e-mail deve conter o código de 6 dígitos"
    # a verificação segue funcionando com o código entregue por e-mail
    r = client.post(VER, json={"study_code": "P-OTP", "code": m.group()})
    assert r.status_code == 200


def test_request_otp_without_contact_sends_nothing(api, monkeypatch):
    monkeypatch.setenv("PII_ENC_KEY", _KEY)
    fake = MemoryEmailSender(); set_email_sender(fake)
    client, TestSession = api
    with TestSession() as s:
        s.add(Participant(study_code="P-NOCONTACT")); s.commit()
    assert client.post(REQ, json={"study_code": "P-NOCONTACT"}).status_code == 200
    assert fake.outbox == []          # sem contato, nada a enviar; resposta ainda genérica


def test_severe_adverse_event_notifies_team(api, monkeypatch):
    monkeypatch.setenv("TEAM_NOTIFY_EMAIL", "equipe@uninta.edu.br")
    fake = MemoryEmailSender(); set_email_sender(fake)
    client, TestSession = api
    pid, hdr = _participant_token(TestSession)
    r = client.post(AE, headers=hdr, json={"type": "headache", "severity": "severe"})
    assert r.status_code == 201 and r.json()["requires_attention"] is True
    assert len(fake.outbox) == 1
    msg = fake.outbox[0]
    assert msg.to == "equipe@uninta.edu.br" and "severe" in msg.body.lower()
    assert str(pid) not in msg.body    # alerta não carrega o participante


def test_mild_adverse_event_does_not_notify(api, monkeypatch):
    monkeypatch.setenv("TEAM_NOTIFY_EMAIL", "equipe@uninta.edu.br")
    fake = MemoryEmailSender(); set_email_sender(fake)
    client, TestSession = api
    _pid, hdr = _participant_token(TestSession)
    r = client.post(AE, headers=hdr, json={"type": "headache", "severity": "mild"})
    assert r.status_code == 201 and r.json()["requires_attention"] is False
    assert fake.outbox == []


def test_unconfigured_email_defaults_to_null_safe(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_DEV_CONSOLE", raising=False)
    set_email_sender(None)             # força reconstrução a partir do ambiente
    sender = get_email_sender()
    assert type(sender).__name__ == "NullEmailSender"
    # não envia e não levanta (padrão seguro; não vaza o código)
    sender.send(EmailMessage(to="x@example.com", subject="s", body="código 123456"))
