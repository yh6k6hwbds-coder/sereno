# Etapa 4 — Instrumentos digitais e métricas
Fonte: `anexos-docx/Etapa4_Instrumentos_Metricas.docx` · código: `../backend/app/modules/instruments/instruments_scoring.py`.
- PSQI/GAD-7/SUS pontuados, **determinísticos e versionados** (validados contra cálculo manual).
- Adesão (telemetria) e **exportação pseudonimizada** com braço codificado.
- Ficha de **encaminhamento** (motivo, serviço, acolhimento) e contagem no relatório ao CEP.
- **PHQ-9 só por SEGURANÇA** (ADR-102): não é desfecho; entra na triagem e nas avaliações
  intermediárias, e o **item 9** aciona o fluxo de encaminhamento (junto com GAD-7 >= 15).
- Licenciamento dos instrumentos (PSQI = Bertolazi 2011); não reproduzir texto verbatim —
  **vale também para o PHQ-9**: os enunciados no app são próprios até a versão validada entrar.
