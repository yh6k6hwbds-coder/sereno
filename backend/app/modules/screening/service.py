"""
modules/screening/service.py — Elegibilidade (critérios do protocolo, versionados) + funil.

A triagem é o 1º passo da inscrição: decide elegibilidade por uma regra **determinística** —
todas as inclusões verdadeiras E nenhuma exclusão presente. Até aqui a meta-regra existia mas
as CHAVES eram livres: o formulário mandava o dicionário que quisesse e o servidor concordava.
Duas consequências ruins, e a segunda é a grave:

  - triagens de participantes diferentes não eram comparáveis (nem auditáveis pelo CEP);
  - ``evaluate_eligibility({}, {})`` respondia **elegível** — ``all([])`` é ``True``. Uma
    triagem enviada vazia (formulário incompleto, cliente com defeito) incluía a pessoa.

Agora as chaves são as do protocolo aprovado (G8), fechadas e versionadas em ``CRITERIA_VERSION``.
Mudar essa lista é **emenda de protocolo**, não refatoração.

**Critérios DERIVADOS não são declarados** — o servidor os calcula a partir dos escores: quem
preenche o formulário não decide se o GAD-7 caiu na faixa, a regra decide. Declará-los é 422.

**A assinatura do TCLE não é uma caixa aqui.** O protocolo a lista entre as inclusões, mas o
sistema já a possui como fato (``ConsentRecord``) e a exige no funil, em ``enrollment_blocker``.
Repetir como declaração o que o banco sabe de origem só criaria a chance de as duas divergirem
— e a triagem, no funil, acontece **antes** do consentimento.
"""
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Screening, ConsentRecord

# 2.0.0 — chaves concretas do protocolo aprovado (antes: só a meta-regra). Ver ADR-105.
CRITERIA_VERSION = "2.0.0"

# --- Inclusões (protocolo, "Critérios de inclusão") -------------------------
INCLUSION_CRITERIA: dict[str, str] = {
    "idade_18_ou_mais": "Idade igual ou superior a 18 anos",
    "vinculo_uninta": "Vínculo ativo como estudante ou funcionário do UNINTA",
    "smartphone_compativel": "Smartphone compatível com a versão distribuída do aplicativo",
    "fones_estereo": "Fones de ouvido estéreo, intra ou supra-auriculares, disponíveis",
    # Derivado dos escores: ansiedade leve a moderada E/OU má qualidade de sono.
    "sintomas_elegiveis": "GAD-7 entre 5 e 14 e/ou PSQI maior que 5",
    "autonomia_e_compreensao": ("Compreende as orientações em português e opera o aplicativo "
                                "de forma autônoma"),
}

# --- Exclusões (protocolo, alíneas (a) a (i)) -------------------------------
EXCLUSION_CRITERIA: dict[str, str] = {
    "a_otologico": ("Perda auditiva conhecida, assimetria auditiva, zumbido clinicamente "
                    "relevante, otalgia ou processo otológico em atividade, cirurgia otológica "
                    "prévia ou impossibilidade de usar fones estéreo adequadamente"),
    "b_neurologico": ("Epilepsia ou história de crises convulsivas, TCE moderado a grave, ou "
                      "doença neurológica que interfira no protocolo ou nos desfechos"),
    "c_psiquiatrico": ("Transtorno bipolar, transtorno psicótico ou transtorno por uso de "
                       "substâncias com prejuízo funcional"),
    # Derivado: mesma regra de risco do fluxo de encaminhamento (safety.evaluate_risk).
    "d_gad7_grave_ou_risco": ("GAD-7 igual ou superior a 15, ou identificação de risco de "
                              "autoextermínio na triagem"),
    "e_apneia": "Diagnóstico prévio ou alta probabilidade de apneia obstrutiva do sono",
    "f_turno_noturno": "Trabalho em turnos noturnos rotativos",
    "g_intervencao_recente": ("Início ou modificação de psicofármaco, psicoterapia ou outra "
                              "intervenção dirigida ao sono ou à ansiedade nas 4 semanas "
                              "anteriores à inclusão ou durante a intervenção"),
    "h_gestacao": "Gestação",
    "i_outro_protocolo": "Participação simultânea em outro protocolo de pesquisa com intervenção",
}

# Calculados pelo servidor a partir dos escores — o formulário não os declara.
DERIVED_INCLUSION = ("sintomas_elegiveis",)
DERIVED_EXCLUSION = ("d_gad7_grave_ou_risco",)

DECLARED_INCLUSION = tuple(k for k in INCLUSION_CRITERIA if k not in DERIVED_INCLUSION)
DECLARED_EXCLUSION = tuple(k for k in EXCLUSION_CRITERIA if k not in DERIVED_EXCLUSION)

# Faixa sintomática de inclusão (protocolo): ansiedade leve a moderada e/ou sono ruim.
GAD7_ELIGIBLE_MIN, GAD7_ELIGIBLE_MAX = 5, 14
PSQI_ELIGIBLE_MIN_EXCLUSIVE = 5


class CriteriaError(ValueError):
    """Conjunto de critérios que não corresponde ao protocolo em vigor (vira 422)."""


def criteria_catalog() -> dict:
    """Catálogo legível dos critérios em vigor — o que a equipe precisa preencher.

    Existe porque não há painel de staff (ADR-096): sem isto, a lista de chaves viveria só no
    código e no formulário de papel, que é exatamente como as duas divergem."""
    return {
        "version": CRITERIA_VERSION,
        "rule": "Elegível se todas as inclusões forem verdadeiras e nenhuma exclusão estiver presente.",
        "inclusion": [{"key": k, "label": v, "derived": k in DERIVED_INCLUSION}
                      for k, v in INCLUSION_CRITERIA.items()],
        "exclusion": [{"key": k, "label": v, "derived": k in DERIVED_EXCLUSION}
                      for k, v in EXCLUSION_CRITERIA.items()],
        "derived_from": {
            "sintomas_elegiveis": (f"gad7_total entre {GAD7_ELIGIBLE_MIN} e {GAD7_ELIGIBLE_MAX} "
                                   f"e/ou psqi_global maior que {PSQI_ELIGIBLE_MIN_EXCLUSIVE}"),
            "d_gad7_grave_ou_risco": ("regra de risco versionada — GAD-7 >= 15, item 9 do PHQ-9 "
                                      "positivo ou relato espontâneo"),
        },
        "note": ("A assinatura do TCLE é inclusão do protocolo, verificada no funil de inscrição "
                 "(registro de consentimento), e não como declaração nesta triagem."),
    }


def validate_declared(inclusion: dict[str, bool], exclusion: dict[str, bool]) -> None:
    """Recusa conjunto incompleto, com chave desconhecida ou com critério derivado declarado."""
    for nome, enviado, esperado, derivados in (
            ("inclusion", inclusion, DECLARED_INCLUSION, DERIVED_INCLUSION),
            ("exclusion", exclusion, DECLARED_EXCLUSION, DERIVED_EXCLUSION)):
        chaves = set(enviado)
        derivadas = chaves & set(derivados)
        if derivadas:
            raise CriteriaError(
                f"{nome}: {', '.join(sorted(derivadas))} é calculado pelo servidor a partir dos "
                "escores e não deve ser declarado.")
        desconhecidas = chaves - set(esperado)
        if desconhecidas:
            raise CriteriaError(
                f"{nome}: critério desconhecido — {', '.join(sorted(desconhecidas))}.")
        faltando = set(esperado) - chaves
        if faltando:
            raise CriteriaError(
                f"{nome}: critério não respondido — {', '.join(sorted(faltando))}.")


def symptoms_eligible(gad7_total: int | None, psqi_global: int | None) -> bool:
    """Faixa sintomática do protocolo: GAD-7 5–14 **e/ou** PSQI > 5."""
    gad = gad7_total is not None and GAD7_ELIGIBLE_MIN <= gad7_total <= GAD7_ELIGIBLE_MAX
    psqi = psqi_global is not None and psqi_global > PSQI_ELIGIBLE_MIN_EXCLUSIVE
    return gad or psqi


def evaluate_eligibility(inclusion: dict[str, bool], exclusion: dict[str, bool]) -> bool:
    """Elegível se todas as inclusões forem verdadeiras e nenhuma exclusão estiver presente.

    Espera o conjunto COMPLETO (declarado + derivado); ``validate_declared`` é quem garante
    isso antes. Conjunto de inclusões vazio é INELEGÍVEL, e não elegível por vacuidade."""
    if not inclusion:
        return False
    return all(bool(v) for v in inclusion.values()) and not any(bool(v) for v in exclusion.values())


def latest_screening(db: Session, participant_id: uuid.UUID) -> Screening | None:
    return db.scalar(select(Screening).where(Screening.participant_id == participant_id)
                     .order_by(Screening.screened_at.desc()))


def has_accepted_consent(db: Session, participant_id: uuid.UUID) -> bool:
    return db.scalar(select(ConsentRecord.id).where(
        ConsentRecord.participant_id == participant_id,
        ConsentRecord.accepted.is_(True),
        ConsentRecord.revoked_at.is_(None))) is not None


def enrollment_blocker(db: Session, participant_id: uuid.UUID) -> str | None:
    """``None`` se apto a alocar; senão, o motivo do bloqueio (para 409). Ordena o funil."""
    sc = latest_screening(db, participant_id)
    if sc is None:
        return "Triagem pendente: registre a triagem antes de alocar."
    if not sc.eligible:
        return "Participante inelegível na triagem."
    if not has_accepted_consent(db, participant_id):
        return "Consentimento (TCLE) pendente: obtenha o aceite antes de alocar."
    return None
