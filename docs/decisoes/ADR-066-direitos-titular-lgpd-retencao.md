# ADR-066 — Direitos do titular (LGPD): acesso/eliminação + retenção

- **Status:** Aceito
- **Data:** 2026-07-05
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança/LGPD)
- **Contexto de origem:** Fatia D4 do ROADMAP
- **Relaciona-se com:** ADR-026/059 (PII), ADR-056 (auditoria append-only), ADR-060 (desbloqueio)

## Contexto
A LGPD dá ao titular direitos de **acesso/portabilidade** e **eliminação**. Faltavam os fluxos —
respeitando duas restrições do estudo: a **auditoria append-only** não pode ser apagada e o
**cegamento** não pode vazar num pedido de acesso.

## Decisão
1. **Acesso/portabilidade** — `GET /v1/participants/{id}/data` (admin `user:manage`): reúne os
   dados do titular (perfil, contato **decifrado** — é o dado dele, consentimento, triagem,
   linha de base, seguimento, diário, eventos adversos, nº de sessões). **NUNCA** inclui o
   braço/condição (alocação é deliberadamente omitida). Auditado (`participant.data_exported`,
   sem PII no log).
2. **Eliminação** — `POST /v1/participants/{id}/erase` (admin): remove a **PII direta**
   (`contact_info` + `otp_challenge`) e marca o participante como **`withdrawn`**. **Retém** os
   dados de pesquisa **pseudonimizados** (exceção de pesquisa da LGPD). **Não apaga** a auditoria
   (append-only) e registra o evento (`participant.erased`, sem PII).
3. **Retenção:** PII direta é eliminável a pedido; o dado de pesquisa pseudonimizado é retido
   para a integridade do estudo/CEP; a auditoria é perene (sem PII).

## Alternativas consideradas
- **Deletar TODOS os registros do participante.** Rejeitada como padrão: quebraria a integridade
  do estudo; a LGPD permite reter dado pseudonimizado para pesquisa. A eliminação **total** (com
  quebra do vínculo pseudônimo) é decisão de **política/CEP** — registrada como pendência.
- **Autoatendimento pelo titular (`/me/data`, `/me/erase`).** Adiada: no piloto, acesso/eliminação
  por **admin** atendendo a um pedido documentado é mais seguro e auditável; self-service depois.
- **Apagar linhas de auditoria do participante.** Impossível (guard append-only) e indesejável — a
  auditoria não contém PII e é a prova de conformidade.

## Consequências
- **Positivas:** o piloto atende pedidos de acesso e eliminação; PII removível; pesquisa e
  auditoria preservadas. Suíte: 142 → 147 testes; prova-se que a eliminação **não** apaga a
  auditoria (append-only respeitado) e que o acesso **não** revela o braço.
- **Custo/tradeoff (visão do analista):**
  - **Eliminação = PII + marcador `withdrawn`**, não deleção total: é a leitura correta da LGPD
    para pesquisa, mas **documentar no TCLE** o que é retido. Deleção total = decisão de CEP.
  - **Export decifra PII** (precisa da `PII_ENC_KEY`): resposta sensível, só admin, auditada,
    sob TLS em produção. Evitar cache/log dessa resposta.
  - **`study_code` (pseudônimo) é retido** e liga o dado de pesquisa; anonimização forte (quebrar
    o vínculo) é passo adicional se exigido.
  - **Sem automação de retenção** (expurgo agendado): política/manual por ora.
- **Pendências:** deleção total sob decisão do CEP; self-service do titular; correção de dados
  (retificação); política de retenção com expurgo agendado; consentimento revogado deve disparar
  o fluxo de eliminação.

## Conformidade
CI verde exige `tests/test_data_rights.py`: a eliminação remove contato+OTP, marca `withdrawn`,
**retém** a linha de base e **preserva** a auditoria (evento pré-existente + `participant.erased`);
a exportação devolve os dados do titular (com PII do próprio) e **não** contém o braço/condição, e
é auditada; negações 401/403 (não-admin)/404.
