"""
scripts/seed_demo.py — Semeia um cenário DEMO completo para experimentar o app localmente.

DEV apenas. Cria:
  - Participant (study_code = "DEMO") + ContactInfo cifrado (para o OTP);
  - 2 AudioProtocol curtos (alpha ativo Δf=10 / sham Δf=0, 30 s) — para a sessão tocar;
  - Screening elegível + ConsentRecord aceito + Allocation (braço A) — para "Iniciar sessão".

Assim dá para: logar (código no log com EMAIL_DEV_CONSOLE=1) → consentir → Home → fazer uma
sessão de ~30 s → pós-sessão → e os registros (linha de base, diário, seguimento, EA).

Uso (dentro do contêiner):  python scripts/seed_demo.py
"""
from __future__ import annotations
import datetime as dt
import hashlib
import os
import sys

# Permite rodar como `python scripts/seed_demo.py` (adiciona a raiz do backend ao path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import get_engine  # noqa: E402
from app.core.models import (  # noqa: E402
    Participant, ContactInfo, AudioProtocol, Screening, ConsentRecord, Allocation)
from app.core import pii_crypto  # noqa: E402

STUDY_CODE = os.getenv("DEMO_STUDY_CODE", "DEMO")
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "voce@example.com")


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _ensure_protocols(s: Session) -> None:
    if s.scalar(select(AudioProtocol).where(AudioProtocol.band == "alpha")) is not None:
        return
    s.add(AudioProtocol(protocol_id="demo-alpha-active", version="1.0.0", band="alpha",
                        carrier_hz=200, beat_hz=10, duration_s=30, target_peak_dbfs=-12.0,
                        content_hash=_sha("demo-active")))
    s.add(AudioProtocol(protocol_id="demo-alpha-sham", version="1.0.0", band="alpha",
                        carrier_hz=200, beat_hz=0, duration_s=30, target_peak_dbfs=-12.0,
                        content_hash=_sha("demo-sham")))


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    with Session(get_engine()) as s:
        _ensure_protocols(s)

        p = s.scalar(select(Participant).where(Participant.study_code == STUDY_CODE))
        if p is None:
            p = Participant(study_code=STUDY_CODE)
            s.add(p)
            s.flush()

        if s.scalar(select(ContactInfo).where(ContactInfo.participant_id == p.id)) is None:
            s.add(ContactInfo(
                participant_id=p.id,
                enc_name=pii_crypto.encrypt("Participante Demo", aad=pii_crypto.aad_for(p.id, "name")),
                enc_email=pii_crypto.encrypt(DEMO_EMAIL, aad=pii_crypto.aad_for(p.id, "email")),
            ))
        if s.scalar(select(Screening).where(Screening.participant_id == p.id)) is None:
            s.add(Screening(participant_id=p.id, eligible=True, criteria={"version": "1.0.0"}))
        if s.scalar(select(ConsentRecord).where(ConsentRecord.participant_id == p.id)) is None:
            s.add(ConsentRecord(participant_id=p.id, tcle_version="1.0.0", accepted=True,
                                accepted_at=now, content_hash="0" * 64))
        if s.scalar(select(Allocation).where(Allocation.participant_id == p.id)) is None:
            s.add(Allocation(participant_id=p.id, arm_coded="A", block=1, sequence_seed_ref="demo"))

        s.commit()
        print("=" * 62)
        print(f"[seed] Cenario DEMO pronto. CODIGO DE ESTUDO = {STUDY_CODE}")
        print(f"[seed] No app: informe '{STUDY_CODE}' e clique 'Enviar codigo'.")
        print("[seed] O codigo do OTP aparece NESTE log (linha '[email -> ...]').")
        print("[seed] Depois: consinta -> Home -> Iniciar sessao (~30s) -> registros.")
        print("=" * 62)


if __name__ == "__main__":
    main()
