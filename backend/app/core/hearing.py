"""
core/hearing.py — Dose de exposição auditiva pelo padrão de audição segura (G9).

O protocolo, em "Intensidade e segurança auditiva", promete duas coisas que até aqui não
existiam em lugar nenhum do sistema:

    "A exposição total prevista (…, totalizando aproximadamente 6 horas e 40 minutos)
     situa-se amplamente abaixo da dose semanal de referência do padrão de audição segura,
     equivalente a 80 dB(A) por 40 horas semanais para adultos (OMS; UIT, 2019). O
     aplicativo manterá contabilização de dose acumulada e exibirá alerta ao atingir 50%
     do limite de referência."

**A referência é SEMANAL.** 80 dB(A) por 40 h é uma *permissão de energia sonora por semana*
(1,6 Pa²h no vocabulário da recomendação UIT-T H.870), não um teto de vida inteira. Por isso
a fração que dispara o alerta é a da **janela móvel de 7 dias**: é ela que tem significado
audiológico. A soma do estudo inteiro é informativa — cabe na tela porque o protocolo diz
"dose acumulada" — mas não é o que o alerta observa.

**A troca é de 3 dB** (energia constante): cada 3 dB acima do nível de referência corta o
tempo permitido pela metade. Daí a potência de 10 no expoente ``/10`` e não ``/5`` — usar a
troca de 5 dB (norma ocupacional de alguns países) daria uma dose mais permissiva do que a
que o protocolo cita.

**De ganho digital para dB(A) só a calibração leva.** O ganho que o cliente declara
(``audio_gain``, G3) é adimensional: quanto do fundo de escala do arquivo foi reproduzido.
Quantos dB(A) isso vira depende do transdutor, e sai da calibração em acoplador de orelha —
etapa (i) do protocolo, item F2.7 do roadmap, **ainda não feita**. Enquanto ela não existe,
``AUDIO_CALIBRATED_SPL_DBA`` fica vazia e a dose é calculada no nível **prescrito** pelo
protocolo (60 dB(A)), com ``calibrated=False`` carimbado na resposta: é uma previsão baseada
no que o protocolo promete entregar, não uma medida do que o aparelho entregou. Inventar um
número e apresentá-lo como medido seria pior do que dizer que a medida não existe.
"""
from __future__ import annotations

import math

# Referência de audição segura para adultos (OMS/UIT 2019, Recomendação UIT-T H.870).
REFERENCE_SPL_DBA = 80.0
REFERENCE_HOURS_PER_WEEK = 40.0
# "Troca de 3 dB" é o nome arredondado da regra; a energia dobra exatamente a cada
# 10·log10(2) = 3,0103 dB. Usar 3,00 cravado daria 20,0 h em 83 dB(A) em vez das 20,047 h
# que a conta de energia devolve — diferença irrelevante na tela, mas a constante é o que
# a fórmula lê, e ela deve ser a exata.
EXCHANGE_RATE_DB = 10.0 * math.log10(2.0)
# O protocolo promete o alerta na METADE da referência, não no limite.
ALERT_FRACTION = 0.5
# Nível PRESCRITO pelo protocolo ("calibrado em 60 dB(A)"). Serve de base enquanto a
# calibração em acoplador não fixa o nível real do transdutor.
PROTOCOL_TARGET_SPL_DBA = 60.0
# A janela em que a referência faz sentido: a permissão é por SEMANA.
WINDOW_DAYS = 7


def allowed_hours(spl_dba: float) -> float:
    """Horas por semana permitidas em ``spl_dba``, pela troca de 3 dB.

    Em 80 dB(A) devolve as 40 h da referência; em 60 dB(A), 4000 h — mais do que existe
    numa semana, que é exatamente o ponto do parágrafo do protocolo."""
    return REFERENCE_HOURS_PER_WEEK * 2 ** ((REFERENCE_SPL_DBA - spl_dba) / EXCHANGE_RATE_DB)


def dose_fraction(spl_dba: float, hours: float) -> float:
    """Fração da permissão semanal consumida por ``hours`` horas em ``spl_dba``.

    1,0 = a permissão inteira. Somar frações de níveis diferentes é legítimo: cada uma é
    energia dividida pela mesma permissão."""
    if hours <= 0:
        return 0.0
    return hours / allowed_hours(spl_dba)


def spl_for_gain(gain: float, full_scale_spl_dba: float) -> float:
    """dB(A) de um ganho digital, dado o nível medido em fundo de escala (ganho 1,0).

    Ganho é razão de amplitude, então a conversão é 20·log10 — usar 10·log10 (razão de
    potência) subestimaria o nível pela metade em dB."""
    if gain <= 0:
        return float("-inf")
    return full_scale_spl_dba + 20.0 * math.log10(gain)


def pa2h(spl_dba: float, hours: float) -> float:
    """Energia sonora em Pa²h — a unidade em que a UIT-T H.870 expressa a permissão.

    A permissão semanal do adulto (80 dB(A) por 40 h) vale 1,6 Pa²h. É o mesmo número da
    fração, em outra escala; existe aqui porque é a forma citável num relatório ao CEP."""
    p0_squared = (20e-6) ** 2                     # (20 µPa)², o limiar de referência
    return p0_squared * 10 ** (spl_dba / 10.0) * max(hours, 0.0)


WEEKLY_ALLOWANCE_PA2H = pa2h(REFERENCE_SPL_DBA, REFERENCE_HOURS_PER_WEEK)   # 1,6 Pa²h
