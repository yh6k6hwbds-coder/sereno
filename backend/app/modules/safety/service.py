"""
modules/safety/service.py — Gatilho de risco e fluxo de encaminhamento (G5).

O protocolo é explícito: se a triagem ou qualquer avaliação de seguimento identificar
**GAD-7 >= 15**, **resposta positiva ao item 9 do PHQ-9** ou relato de sofrimento psíquico,
o candidato não é incluído — ou, se já incluído, é **retirado do protocolo** — e é acolhido
pela pesquisadora responsável e encaminhado de forma **formal e documentada**.

Três coisas ficam aqui, num lugar só, porque precisam valer igual na triagem e no seguimento:

  1. a REGRA (versionada) que decide o que é risco;
  2. a abertura da FICHA de encaminhamento (uma por vez — reabrir a cada questionário
     transformaria a ficha em fila de duplicatas);
  3. o aviso à equipe, sem PII e sem escore.

O que este módulo **não** faz: decidir conduta clínica. Ele interrompe a exposição, documenta
e chama gente. Ver ADR-102.
"""
from __future__ import annotations

import os
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.email import EmailMessage, get_email_delivery
from app.core.models import Participant, Referral, SafetyAssessment
from app.modules.audit.service import record_event

# Versão da REGRA (separada da versão do escore): mudar o ponto de corte muda a regra, não
# o algoritmo do PHQ-9 — e a análise precisa saber qual regra estava valendo.
RISK_RULE_VERSION = "1.0.0"
GAD7_RISK_CUTOFF = 15                 # critério de exclusão (d) do protocolo

# Orientação SEMPRE presente na resposta, como no relato de evento adverso (ADR-051). Não
# prescreve conduta: diz a quem recorrer. Os contatos são os do TCLE.
GUIDANCE = (
    "Se você estiver em sofrimento agora, procure ajuda: CVV 188 (24h, gratuito), "
    "SAMU 192 ou a emergência mais próxima. A pesquisadora responsável vai entrar em "
    "contato para acolhimento e encaminhamento. O aplicativo é ferramenta complementar "
    "e não substitui avaliação profissional."
)


def evaluate_risk(*, gad7_total: int | None = None, phq9_item9: int | None = None,
                  self_reported: bool = False) -> list[str]:
    """Motivos de risco acionados. Lista vazia = sem gatilho.

    Devolve os motivos (e não um booleano) porque a ficha precisa registrar **por que** foi
    aberta: o relato ao CEP e o acolhimento mudam conforme o gatilho."""
    reasons: list[str] = []
    if gad7_total is not None and gad7_total >= GAD7_RISK_CUTOFF:
        reasons.append("gad7_grave")
    if phq9_item9 is not None and phq9_item9 > 0:
        reasons.append("phq9_item9")
    if self_reported:
        reasons.append("relato")
    return reasons


def open_referral(db: Session, participant_id: uuid.UUID, reasons: list[str], *,
                  assessment_id: uuid.UUID | None = None,
                  actor_type: str = "participant",
                  actor_id: uuid.UUID | None = None) -> Referral:
    """Abre a ficha (ou devolve a que já está aberta) e audita, sem PII e sem escore."""
    aberta = db.scalar(select(Referral).where(
        Referral.participant_id == participant_id,
        Referral.status.in_(("aberto", "encaminhado"))))
    if aberta is not None:
        # Motivo novo em ficha já aberta: acumula, não duplica a ficha.
        atuais = list(aberta.reasons or [])
        novos = [r for r in reasons if r not in atuais]
        if novos:
            aberta.reasons = atuais + novos
            db.flush()
        return aberta

    ficha = Referral(participant_id=participant_id, reasons=reasons,
                     assessment_id=assessment_id, status="aberto")
    db.add(ficha)
    db.flush()
    record_event(db, action="referral.opened", resource_type="referral",
                 actor_type=actor_type, actor_id=actor_id, resource_id=ficha.id,
                 meta={"reasons": reasons, "rule_version": RISK_RULE_VERSION})
    notify_team(ficha.id, reasons)
    return ficha


def remove_from_protocol(db: Session, participant_id: uuid.UUID) -> None:
    """Interrompe a participação no protocolo (o protocolo manda retirar, não só avisar).

    Não é retirada de consentimento nem conclusão: o status próprio (``removed``) mantém as
    três situações distinguíveis no relato ao CEP. O dado já coletado permanece — apagá-lo
    aqui seria decisão do titular, não da equipe."""
    p = db.get(Participant, participant_id)
    if p is not None and p.status == "active":
        p.status = "removed"
        db.flush()


def notify_team(referral_id: uuid.UUID, reasons: list[str]) -> None:
    """Avisa a equipe. Best-effort, **sem PII e sem escore** — só o id da ficha e o gatilho.

    Um e-mail com o total do PHQ-9 espalharia dado de saúde por caixa de entrada; quem precisa
    do número entra na API de pesquisa. Sem ``TEAM_NOTIFY_EMAIL`` configurado, não notifica
    (item F3.7 do roadmap)."""
    to = os.getenv("TEAM_NOTIFY_EMAIL")
    if not to:
        return
    get_email_delivery().deliver(EmailMessage(
        to=to,
        subject="[Sereno] Encaminhamento aberto (fluxo de segurança)",
        body=(f"O fluxo de encaminhamento foi acionado (ficha {referral_id}; "
              f"gatilho: {', '.join(reasons)}). O participante foi retirado do protocolo e "
              f"aguarda acolhimento. Detalhes na API de pesquisa."),
    ))


def record_assessment(db: Session, participant_id: uuid.UUID, *, moment: str,
                      phq9: dict | None, gad7_total: int | None,
                      self_reported: bool = False,
                      actor_type: str = "participant",
                      actor_id: uuid.UUID | None = None) -> tuple[SafetyAssessment, Referral | None]:
    """Grava a avaliação de segurança e, havendo gatilho, abre a ficha e retira do protocolo."""
    item9 = phq9.get("item9") if phq9 else None
    reasons = evaluate_risk(gad7_total=gad7_total, phq9_item9=item9, self_reported=self_reported)

    avaliacao = SafetyAssessment(
        participant_id=participant_id, moment=moment,
        phq9_total=phq9.get("total") if phq9 else None,
        phq9_item9=item9, gad7_total=gad7_total,
        risk_detected=bool(reasons), reasons=reasons,
        score_version=(phq9 or {}).get("version", "-"),
        rule_version=RISK_RULE_VERSION,
    )
    db.add(avaliacao)
    db.flush()

    if not reasons:
        return avaliacao, None

    ficha = open_referral(db, participant_id, reasons, assessment_id=avaliacao.id,
                          actor_type=actor_type, actor_id=actor_id)
    remove_from_protocol(db, participant_id)
    return avaliacao, ficha
