# ADR-105 — Os critérios de elegibilidade do protocolo, codificados e fechados

- **Status:** Aceito
- **Data:** 2026-08-31
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado
- **Etapas relacionadas:** 5 (backend), 4 (instrumentos)
- **Contexto de origem:** item **G8** do `docs/ROADMAP.md`.
- **Relaciona-se com:** ADR-057 (triagem por regra transparente e versionada), ADR-102 (regra de
  risco e fluxo de encaminhamento), ADR-100 (parâmetros do protocolo aprovado).

## Contexto

O ADR-057 implementou a **meta-regra** da elegibilidade — elegível se todas as inclusões forem
verdadeiras e nenhuma exclusão estiver presente — e deixou as **chaves** em aberto, à espera do
protocolo aprovado. O protocolo chegou (`PROJETO de IC`, 2026-08-29) com 7 critérios de inclusão
e 9 de exclusão, alíneas (a) a (i), todos redigidos como condições verificáveis.

Enquanto as chaves ficaram livres, o servidor aceitava qualquer dicionário. Isso produzia duas
coisas ruins, e a segunda é grave:

1. **Triagens não comparáveis.** Um formulário mandava `{"idade_18_60": true}`, outro
   `{"idade_18": true, "fones": true}`. Nada obrigava consistência, e o CEP pede o conjunto.
2. **Triagem vazia era ELEGÍVEL.** `all([])` é `True` em Python: `evaluate_eligibility({}, {})`
   respondia elegível. Um formulário enviado incompleto — cliente com defeito, campo perdido no
   caminho — **incluía** a pessoa. É o tipo de defeito que não aparece em teste nenhum porque o
   caminho feliz nunca passa por ele.

Havia ainda a faixa sintomática. O protocolo inclui quem tem **GAD-7 entre 5 e 14 e/ou PSQI > 5**;
isso é uma conta sobre escores, não uma caixa a marcar. Deixá-la como declaração significaria
confiar na aritmética de quem preenche o formulário para decidir inclusão.

## Decisão

1. **As chaves passam a ser as do protocolo, e o conjunto é FECHADO.** `INCLUSION_CRITERIA` e
   `EXCLUSION_CRITERIA` em `screening/service.py`, versionados em `CRITERIA_VERSION = "2.0.0"`.
   Critério faltando, desconhecido ou derivado declarado é **422** — a triagem não é gravada.
2. **Critérios DERIVADOS são calculados pelo servidor, nunca declarados:**
   - `sintomas_elegiveis` — GAD-7 entre 5 e 14 e/ou PSQI > 5, a partir de `gad7_total` e do novo
     campo `psqi_global`;
   - `d_gad7_grave_ou_risco` — a alínea (d), que é exatamente a regra de risco já versionada no
     ADR-102 (GAD-7 ≥ 15, item 9 do PHQ-9, relato). A exclusão por segurança deixa de ser um
     campo à parte e passa a ser o critério de exclusão que o protocolo diz que ela é.
3. **`evaluate_eligibility` com inclusões vazias devolve INELEGÍVEL**, e não elegível por
   vacuidade. Defesa em profundidade: mesmo que a validação seja contornada, o fecho é seguro.
4. **A assinatura do TCLE não é uma caixa da triagem.** O protocolo a lista entre as inclusões,
   mas o sistema já a possui como fato (`ConsentRecord`) e a exige no funil
   (`enrollment_blocker`). Duplicá-la como declaração criaria a chance de as duas divergirem — e
   a triagem, no funil, acontece **antes** do consentimento.
5. **`GET /v1/screening/criteria`** publica o catálogo em vigor (chave, rótulo, se é derivado).
   Existe porque não há painel de staff (ADR-096): sem isso, a lista viveria só no código e no
   formulário de papel, que é exatamente como as duas divergem.
6. **A resposta e a auditoria dizem QUAIS critérios barraram** (`unmet_criteria`). "Inelegível"
   sozinho não se explica a quem lê a trilha depois.

## Alternativas consideradas

- **Manter as chaves livres e validar no formulário de papel.** Rejeitada: é o estado que
  produziu o defeito da triagem vazia, e o servidor é o único lugar onde a regra vale para todos.
- **Aceitar chaves faltando como `False`.** Rejeitada: silenciosamente inelegível é tão ruim
  quanto silenciosamente elegível — some a diferença entre "respondeu não" e "não respondeu".
- **Deixar `sintomas_elegiveis` como caixa marcada pelo triador.** Rejeitada: é uma conta sobre
  escores que o servidor já tem. Quem decide a faixa é a regra, não quem preenche.
- **Derivar `tcle_assinado` do `ConsentRecord`.** Rejeitada: no funil a triagem vem antes do
  consentimento, então o campo seria sempre falso na hora em que é avaliado.
- **Guardar os rótulos só no documento do CEP.** Rejeitada: o catálogo em `/screening/criteria`
  é o que permite conferir, sem ler código, que o sistema aplica o protocolo aprovado.

## Consequências

- **Positivas:** a triagem passa a ser o instrumento do protocolo, não um dicionário livre; a
  triagem vazia deixou de incluir ninguém; a faixa sintomática é calculada, não declarada; o CEP
  tem como conferir a lista em vigor por um endpoint.
- **Custo:** o corpo de `POST /v1/screening` cresceu (14 chaves declaráveis + `psqi_global`);
  qualquer cliente que ainda mande as chaves antigas passa a receber 422 — o que é o
  comportamento desejado, mas exige atualizar o formulário de coleta. +8 testes.
- **Sem migração:** `Screening.criteria` já é JSON; o que mudou é o conteúdo (agora também
  guarda os escores que motivaram os derivados).
- **⚠️ A redação dos critérios é resumo, não o texto do protocolo.** Os rótulos do catálogo são
  curtos por serem operacionais; o texto que vale para o CEP é o do projeto e do TCLE.
- **⚠️ `psqi_global` na triagem é um escore informado**, não o PSQI completo respondido no app
  (esse é a linha de base, T0). O triador o obtém do rastreamento; o servidor confia no número,
  como já confiava em `gad7_total`.

## Conformidade

CI verde exige `backend/tests/test_screening.py` (conjunto fechado, 422 para faltando /
desconhecido / derivado declarado, triagem vazia inelegível, faixa sintomática calculada dos
escores, "e/ou" com PSQI sozinho, catálogo com as 9 alíneas, auditoria com `unmet`) e
`backend/tests/test_safety_referral.py` (a alínea (d) acionada pela regra de risco).
