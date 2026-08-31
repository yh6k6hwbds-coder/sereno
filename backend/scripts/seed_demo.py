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
from app.modules.consent.router import TCLE_CURRENT  # noqa: E402  # versao vigente do termo
from app.modules.screening import service as screening_service  # noqa: E402

STUDY_CODE = os.getenv("DEMO_STUDY_CODE", "DEMO")
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "voce@example.com")


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _ensure_protocols(s: Session) -> None:
    """Par CURTO na mesma faixa do estudo (delta, 250/253 Hz) — 30 s para a demo caber.

    A duração é a única diferença deliberada em relação ao protocolo real (20 min): o resto
    espelha ``scripts/seed_protocols.py`` para que a demo exercite o mesmo caminho do piloto,
    inclusive o handle ``delta`` que o aplicativo envia. Isto é DEV — nenhum participante
    ouve estes arquivos."""
    if s.scalar(select(AudioProtocol).where(AudioProtocol.band == "delta")) is not None:
        return
    s.add(AudioProtocol(protocol_id="demo-01", version="1.0.0", band="delta",
                        carrier_hz=250, beat_hz=3, duration_s=30, target_peak_dbfs=-12.0,
                        sample_rate=48000, fade_in_s=3.0, fade_out_s=3.0,
                        content_hash=_sha("demo-01")))
    s.add(AudioProtocol(protocol_id="demo-02", version="1.0.0", band="delta",
                        carrier_hz=250, beat_hz=0, duration_s=30, target_peak_dbfs=-12.0,
                        sample_rate=48000, fade_in_s=3.0, fade_out_s=3.0,
                        content_hash=_sha("demo-02")))


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
            # Critérios do protocolo em vigor (G8/ADR-105) — não uma versão inventada: a
            # triagem semeada aqui é a que a demo mostra, e mostrar o formato errado ensina
            # o formato errado a quem for operar.
            s.add(Screening(
                participant_id=p.id, eligible=True,
                criteria={"version": screening_service.CRITERIA_VERSION,
                          "inclusion": {k: True for k in screening_service.INCLUSION_CRITERIA},
                          "exclusion": {k: False for k in screening_service.EXCLUSION_CRITERIA},
                          "scores": {"gad7_total": 8, "psqi_global": 9}}))
        if s.scalar(select(ConsentRecord).where(ConsentRecord.participant_id == p.id)) is None:
            s.add(ConsentRecord(participant_id=p.id, tcle_version=TCLE_CURRENT, accepted=True,
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
