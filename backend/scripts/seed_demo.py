"""
scripts/seed_demo.py — Cria um participante de teste para experimentar o login localmente.

DEV apenas. Insere um Participant (study_code = "DEMO") e um ContactInfo cifrado (para o
fluxo de OTP). Com EMAIL_DEV_CONSOLE=1, o código do OTP é impresso no log do backend ao
solicitar o código — copie de lá e cole no app.

Uso (dentro do contêiner):  python scripts/seed_demo.py
"""
from __future__ import annotations
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.models import Participant, ContactInfo
from app.core import pii_crypto

STUDY_CODE = os.getenv("DEMO_STUDY_CODE", "DEMO")
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "voce@example.com")


def main() -> None:
    with Session(get_engine()) as s:
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
        s.commit()
        print("=" * 60)
        print(f"[seed] Participante de teste pronto. CÓDIGO DE ESTUDO = {STUDY_CODE}")
        print(f"[seed] No app, informe '{STUDY_CODE}'. O código do OTP sairá NESTE log")
        print("[seed] (linha '[email -> ...]') se EMAIL_DEV_CONSOLE=1. Cole-o no app.")
        print("=" * 60)


if __name__ == "__main__":
    main()
