# ADR-102 — PHQ-9 de segurança, gatilho de risco e ficha de encaminhamento

- **Status:** Aceito
- **Data:** 2026-08-30
- **Decisores:** Mantenedor (Augusto) — "siga para G5" — + arquiteto (Claude)
- **Etapas relacionadas:** 1 (segurança como desfecho), 4 (instrumentos), 5 (backend), 3 (UX)
- **Contexto de origem:** item **G5** do `docs/ROADMAP.md`, aberto pelo ADR-100 a partir do
  projeto de iniciação científica ("Fluxo de encaminhamento em caso de sofrimento psíquico" e
  "Instrumentos de coleta e desfechos").
- **Relaciona-se com:** ADR-051 (evento adverso), ADR-057 (triagem), ADR-089 (retirada de
  consentimento), ADR-062 (relatório de análise).

## Contexto

O protocolo prevê um instrumento e um procedimento que **não existiam** no sistema.

O instrumento: **PHQ-9 aplicado na triagem e nas avaliações intermediárias, com finalidade de
segurança — não como desfecho**, sendo o **item 9** o rastreio de risco de autoextermínio.

O procedimento: identificado GAD-7 >= 15, item 9 positivo ou relato de sofrimento psíquico, o
candidato **não é incluído** ou, se já incluído, é **retirado do protocolo**, imediatamente
acolhido pela pesquisadora responsável e encaminhado "de forma formal e documentada" ao apoio
psicológico da instituição e, quando indicado, ao CAPS de referência — com o encaminhamento
"registrado em ficha específica, com confirmação de acolhimento, e comunicado ao Comitê de Ética
em Pesquisa no relatório parcial".

Nada disso tinha lugar no sistema: o item 9 não era coletado, o GAD-7 >= 15 aparecia só como uma
caixa de exclusão que alguém marcava à mão, e não havia onde registrar encaminhamento nem
acolhimento. Segurança é **desfecho primário** deste piloto.

## Decisão

1. **`score_phq9`** entra no motor de escores, versionado como os demais, com **item 9 separado
   no resultado** — e não diluído no total. Alguém com total baixo e item 9 positivo precisa do
   mesmo acolhimento; se o gatilho olhasse só o total, esse caso passaria batido.
2. **A regra de risco é uma só, versionada** (`safety/service.py`: `RISK_RULE_VERSION`,
   `GAD7_RISK_CUTOFF = 15`) e vale igual na triagem e no seguimento. Ela devolve os **motivos**
   acionados, não um booleano: a ficha precisa registrar *por que* foi aberta.
3. **A triagem passa a aceitar `phq9_items` e `gad7_total`** e, havendo gatilho, marca
   **inelegível** — mesmo que os critérios preenchidos digam o contrário. Quem decide ali é a
   regra, não quem preencheu o formulário. O motivo fica em `criteria.safety_exclusion`.
4. **Retirar é retirar:** o participante ganha o status **`removed`** e as sessões param de
   fato (403 com mensagem que manda falar com a pesquisadora). É distinto de `withdrawn`
   (retirada de consentimento) e de `completed`; o relato ao CEP conta as três separadamente.
   O dado já coletado permanece — apagá-lo é decisão do titular, não da equipe.
5. **Uma ficha por vez** (`referral`). Um novo gatilho em ficha aberta **acumula o motivo** em
   vez de abrir outra: reabrir a cada questionário transformaria a ficha em fila de duplicatas.
   A ficha é **estruturada, sem texto livre** — narrativa clínica ali seria dado sensível a mais,
   sem necessidade. `POST /v1/referrals/{id}/record` registra o serviço e a confirmação de
   acolhimento; `GET /v1/referrals` lista pseudonimizado (código do estudo, motivos, datas).
6. **A resposta ao participante não traz escore.** Um número de gravidade na tela, sem
   profissional junto, é lido como diagnóstico — e o app é ferramenta complementar. Vai
   **orientação de cuidado sempre** (CVV 188, SAMU 192, emergência), com ou sem gatilho, e,
   havendo gatilho, o aviso de que a equipe entrará em contato e de que as sessões ficam
   pausadas **sem prejuízo**. O escore fica com a equipe.
7. **O aviso à equipe não leva escore nem PII** — só o id da ficha e o gatilho. Um e-mail com o
   total do PHQ-9 espalharia dado de saúde por caixa de entrada.
8. **O relatório de análise ganha o bloco `seguranca`**: eventos adversos graves,
   encaminhamentos (total / em aberto / com acolhimento confirmado) e retirados por segurança.
   É o que o protocolo manda comunicar ao CEP no relatório parcial, em contagens agregadas.

## Alternativas consideradas

- **Tratar o PHQ-9 como mais um desfecho.** Rejeitada: o protocolo é explícito que não é, e
  transformá-lo em desfecho mudaria a análise pré-especificada.
- **Só sinalizar, sem retirar do protocolo.** Rejeitada: o protocolo manda retirar, e continuar
  expondo alguém em risco a um estímulo experimental é o oposto do que a ética do estudo pede.
- **Mostrar o escore ao participante.** Rejeitada: ver a decisão 6.
- **Deixar a ficha como texto livre.** Rejeitada: campos estruturados documentam o que o
  protocolo exige (serviço, data, confirmação) sem criar um depósito de narrativa clínica.
- **Reaproveitar `withdrawn` para a retirada por segurança.** Rejeitada: apagaria a diferença
  entre "o titular retirou o consentimento" e "a equipe interrompeu por segurança" — que é
  exatamente a distinção que o relatório ao CEP precisa fazer.
- **Abrir uma ficha por gatilho.** Rejeitada: duplicaria o trabalho de acolhimento.

## Consequências

- **Positivas:** o gatilho de segurança existe e é o mesmo nos dois pontos de coleta; a retirada
  interrompe a exposição de verdade; o encaminhamento é documentado no formato que o CEP pede; o
  relatório parcial tem os números sem ninguém compilar à mão.
- **Custo:** +1 migração (duas tabelas e um valor de status); a resposta da triagem ganhou dois
  campos (`risk_detected`, `referral_id`); +14 testes de backend, +4 de widget.
- **⚠️ Os enunciados do PHQ-9 no app são PRÓPRIOS**, como já eram os do GAD-7 — a redação
  validada em PT-BR precisa ser licenciada e inserida antes da coleta real (mesma pendência do
  PSQI/GAD-7, item de licenciamento da Etapa 4). Paráfrase muda a psicometria: isto é código de
  pontuação e de fluxo, não o questionário.
- **⚠️ O acolhimento acontece fora do sistema.** O que o sistema faz é parar a exposição,
  documentar e avisar. Quem acolhe é a pesquisadora responsável — e o aviso só sai de fato com
  `TEAM_NOTIFY_EMAIL` configurado (item F3.7). Sem isso, a ficha existe mas ninguém é avisado.
- **A janela T2 continua sendo G6.** A tela e o endpoint existem e são alcançáveis pela Home
  (o participante pode registrar a qualquer momento, o que é uma rede a mais); o que falta é o
  **momento** — lembrete, janela da 2ª semana e a avaliação intermediária de adesão.
- **O CAPS de referência ainda é `[a confirmar]`** no TCLE (campo 12 do formulário do protocolo):
  o enum da ficha já prevê `caps`, mas o serviço concreto é resposta da pesquisadora.

## Conformidade

CI verde exige `backend/tests/test_safety_referral.py` (regra versionada, item 9 com total baixo,
resposta sem escore, retirada que bloqueia sessão, ficha única com motivos acumulados, triagem
inelegível por segurança, RBAC da ficha, contagem no relatório) e
`app/test/safety_check_test.dart` (botão só com tudo respondido, ausência de escore na tela,
aviso de contato/pausa, item de risco presente e contatos antes das perguntas); migração
`b8c9d0e1f2a3`; OpenAPI válido.
