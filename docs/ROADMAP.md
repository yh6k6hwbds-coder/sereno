# ROADMAP — Sereno (backlog de fatias verticais)

> Documento vivo. É o backlog que se abre no Claude Code para executar a **próxima
> fatia**. Método fixo (não negociável): **contrato → código → teste (inclui caminhos de
> negação) → CI verde → ADR → próxima**. Simplicidade > complexidade. Escopo travado no
> **piloto de 4 semanas**; itens de expansão ficam em Fase E e não entram no caminho crítico.

## Como ler
- **Prioridade:** `P0` = caminho crítico para um piloto coletável · `P1` = importante ·
  `P2` = expansão/pós-piloto.
- **Status:** `TODO` · `WIP` · `DONE`.
- **Pronto (DoD):** a fatia só fecha quando esses testes passam no CI e o ADR foi escrito.
- **Inegociáveis:** o que a fatia NÃO pode violar (ver `CLAUDE.md`).

## Estado atual (baseline deste roadmap)
- **Backend (121 testes verdes):** `problem+json`; banco/migração portáveis (3 migrações);
  auth de staff (argon2+JWT+MFA + **rate limit/denylist de jti — D2/ADR-064**); auth de
  participante (OTP + **entrega por e-mail — D1/ADR-063**); **gestão de staff + MFA enrollment
  (C3/ADR-058)**; consentimento; **triagem/elegibilidade + funil (C2/ADR-057)**; linha de base
  (PSQI+GAD-7); randomização + **alocação oculta** (com gate de inscrição); sessão + telemetria com **resolução cega**;
  **entrega de áudio bit-a-bit (A1/ADR-053)**; **auditoria append-only (C1/ADR-056)**;
  **captura de contato com PII cifrada (C4/ADR-059)**; desfechos (pós-sessão, diário); seguimento
  (PSQI+GAD-7+SUS+cegamento); evento adverso.
- **Stubs restantes:** `recommender`.
- **Sem endpoint ainda (tabelas existem):** `recommendation_log`, exportação real.
- **Flutter (não compilado no ambiente de planejamento):** OTP → consentimento → home →
  preparar fones → sessão com **reprodução de áudio real bit-a-bit + fila de telemetria offline
  (A2/ADR-054)** e visualização não reativa. Falta persistência de login e as telas de
  baseline/pós-sessão/diário/seguimento/EA. (Testes Flutter escritos, mas ainda não executados —
  sem SDK local; dependem do job `app` do CI.)
- **ADRs:** 041–052.

---

## FASE A — Tornar a sessão funcional (áudio real) · P0
A sessão hoje é conduzida por relógio; falta o áudio de verdade. Esta fase conecta a
validação por FFT (que já roda no CI) ao que o participante ouve, **sem vazar o braço**.

### A1 — Endpoint de entrega de áudio (backend) · P0 · `DONE`
> **Concluída (2026-07-04, ADR-053):** `GET /v1/sessions/{id}/audio` serve o WAV materializado
> (determinístico, validado por FFT, cache em disco), bit-a-bit, com `ETag=audio_sha256`,
> `Accept-Ranges`/`Range` (206/416) e `Cache-Control: private, no-store`. Erros 401/404(IDOR)/409.
> DoD coberto por `tests/test_session_audio.py` (7 testes). Decisão-chave: separar `audio_sha256`
> (integridade dos bytes) de `content_hash` (identidade opaca) — o ROADMAP se contradizia aqui.
- **Objetivo:** servir o arquivo de áudio da sessão, autenticado, **bit-a-bit**, sem revelar
  o braço. O cliente pede pelo `session_id` (não pelo braço); o servidor resolve o protocolo
  internamente (reusa `resolve_arm`/`resolve_protocol`) e transmite o WAV correspondente.
- **Depende de:** sessão (feita).
- **Contrato:** `GET /v1/sessions/{id}/audio` → `audio/wav` (ou `application/octet-stream`),
  com `ETag: <content_hash>`, `Accept-Ranges: bytes` (suporte a Range para retomada),
  `Cache-Control: private, no-store`. Erros em problem+json (404 se a sessão não é do
  participante; 409 se protocolo indisponível).
- **Geração do arquivo:** determinística via `audio-pipeline/binaural_instrument.py` (offline),
  materializada uma vez por protocolo e **validada por FFT** antes de servir (ver DoD).
- **Pronto (DoD):**
  1. Participante autenticado baixa o áudio da **própria** sessão (200 + `Content-Type` de
     áudio + `ETag == content_hash`).
  2. **IDOR:** baixar áudio de sessão alheia → 404.
  3. **Sem vazamento:** dois participantes em braços opostos recebem respostas de mesma forma
     (mesmos headers/estrutura); o `content_hash`/bytes diferem (opaco), mas nada nos
     **metadados/headers** revela ativo/sham/beat/banda-de-condição.
  4. **Fidelidade:** o SHA-256 do corpo transmitido == `content_hash` do protocolo (bit-a-bit).
  5. **FFT no CI:** o job de áudio valida que o WAV do braço ativo tem pico em `beat_hz` e o
     sham tem Δf=0 (já existe a bateria; estendê-la para o arquivo servido/materializado).
  6. Range request (`bytes=`) retorna 206 com o trecho correto.
- **Inegociáveis:** resolução do braço só no servidor; nenhum header/metadado revela condição;
  reprodução bit-a-bit; síntese offline validada por FFT.
- **ADR:** ADR-053 (entrega de áudio sem vazamento + fidelidade).
- **Riscos/decisões:** onde materializar o WAV (disco local agora; **cloud storage** é Fase E);
  tamanho do arquivo (streaming/Range); cache no cliente sem persistir em claro.

### A2 — Reprodução real + fila de telemetria offline (Flutter) · P0 · `WIP`
> **Código completo (2026-07-04, ADR-054):** download com verificação bit-a-bit (sha256==ETag),
> reprodução via porta `AudioPlayerPort` (just_audio isolado; fonte em memória, sem DSP, sem cache
> em claro), visualização mantida **não reativa**, e fila de telemetria offline (`TelemetrySender`
> + `FileTelemetryQueue`) com reenvio. Testes em `app/test/` (widget + unit). **Falta:** rodar
> `flutter analyze && flutter test` (sem SDK Flutter no ambiente de dev) — validação depende do job
> `app` do CI, hoje não-bloqueante. Fecha de vez quando a fatia **D5** tornar esse job bloqueante.
- **Objetivo:** o player toca o WAV baixado (A1) de forma **gapless/bit-exata**; a telemetria
  (duração efetiva, interrupções) é enfileirada e reenviada se a rede cair.
- **Depende de:** A1.
- **Contrato:** consome `GET /sessions/{id}/audio`; envia `POST /sessions/{id}/complete`.
- **Pronto (DoD):** widget tests — o player inicia após download; pausa/retomada contam
  interrupção; `complete` é chamado com valores corretos; se `complete` falha, fica na fila e
  reenvia. A visualização permanece **não reativa** (teste garante independência do áudio).
- **Inegociáveis:** UI idêntica entre braços; visualização não reativa; sem DSP no cliente.
- **ADR:** ADR-054 (player + fila offline).
- **Libs sugeridas:** `just_audio` (reprodução), `path_provider` (cache), fila simples em disco.

---

## FASE B — Completar a captura do participante (telas) · P0/P1
Reusa endpoints já prontos. Cada tela é uma fatia com widget tests.

### B1 — Persistência de login + refresh de token (Flutter) · P0 · `TODO`
- **Objetivo:** auto-login se houver token válido; refresh transparente no 401; logout limpa
  o armazenamento seguro. Roteamento inicial decide OTP vs Home conforme sessão.
- **Depende de:** —. **Contrato:** `POST /auth/refresh`.
- **Pronto:** widget/integration tests do fluxo de sessão persistida e de refresh no 401.
- **ADR:** ADR-055. **Sugestão:** adotar **Riverpod + go_router** aqui (ver ADR-050) e
  empacotar as **fontes** da identidade.

### B2 — Tela de linha de base (PSQI + GAD-7) · P0 · `TODO`
- **Contrato:** `POST /participants/me/baseline` (feito). **Depende de:** B1.
- **Pronto:** widget tests — validação de faixa no cliente, envio, tratamento de 409/422;
  não exibe escore de forma alarmante (bem-estar).
- **Inegociáveis:** não reproduzir texto verbatim dos instrumentos; linguagem cuidadosa.

### B3 — Tela de pós-sessão · P1 · `TODO`
- **Contrato:** `POST /sessions/{id}/survey` (feito). **Depende de:** A2.

### B4 — Tela de diário de sono · P1 · `TODO`
- **Contrato:** `POST /diary` (feito). **Depende de:** B1.

### B5 — Tela de seguimento (PSQI+GAD-7+SUS + item de cegamento) · P1 · `TODO`
- **Contrato:** `POST /participants/me/followup` (feito). **Depende de:** B1.
- **Inegociável:** o item de cegamento captura só o **palpite**; a UI nunca sugere o braço.

### B6 — Tela de relato de evento adverso · P1 · `TODO`
- **Contrato:** `POST /adverse-events` (feito). **Depende de:** B1.
- **Bem-estar:** para gravidade alta, a tela reforça orientação de buscar ajuda (192/CVV 188).

---

## FASE C — Fluxo de pesquisa e integridade científica · P0/P1
O que o CEP e a análise exigem. Tudo com trilha de auditoria.

### C1 — Log de auditoria append-only (transversal) · P0 · `DONE`
> **Concluída (2026-07-04, ADR-056):** serviço `audit.service` (`record_event`/`list_events`),
> append-only por guard no ORM (`AuditAppendOnlyError`) + GRANT no Postgres (prod); `consent` e
> `allocation` emitem eventos (alocação **sem o braço**); `GET /research/audit` (admin, `audit:read`)
> com paginação keyset. 8 testes. **Parcial por design:** export (C6) e unblind (C5) plugam o hook
> quando existirem.
- **Objetivo:** registrar ações sensíveis (consentimento, alocação, pedido de exportação,
  pedido/execução de desbloqueio) em `audit_log`, **append-only**, sem PII.
- **Depende de:** —. **Contrato:** interno (sem endpoint público) + `GET /research/audit`
  (admin) para leitura.
- **Pronto:** testes provam que cada ação sensível grava um evento; que `UPDATE/DELETE` em
  `audit_log` é barrado (por GRANT no Postgres; em teste, por invariante de serviço).
- **Inegociável:** nunca gravar PII nem o braço em claro no log.
- **ADR:** ADR-056.

### C2 — Triagem/elegibilidade (enrollment) · P0 · `DONE`
- **Objetivo:** `screening` → decide elegibilidade → habilita consentimento → habilita
  alocação. Ordena o funil de inscrição (staff).
- **Contrato:** `POST /v1/screening` (staff `enroll:write`); grava critérios/elegibilidade.
- **Pronto:** elegível vs inelegível; bloqueio de alocação antes de screening+consentimento.
- **ADR:** ADR-057.
> **Concluída (2026-07-04, ADR-057):** `POST /v1/screening` calcula elegibilidade por regra
> versionada (inclusões-todas / exclusão-nenhuma), audita (sem PII), uma por participante (409).
> A alocação passou a exigir triagem elegível + consentimento (`enrollment_blocker` → 409). 13
> testes; testes de alocação/auditoria atualizados p/ semear o funil.

### C3 — Gestão de staff + MFA enrollment (admin) · P1 · `DONE`
- **Contrato:** `POST /v1/staff` (admin `user:manage`), `POST /v1/staff/me/mfa/enroll`
  (gera segredo + URI otpauth). **Depende de:** auth de staff (feito).
- **Pronto:** admin cria pesquisador; enrollment de MFA emite `provisioning_uri`; sem
  auto-registro público.
- **ADR:** ADR-058.
> **Concluída (2026-07-04, ADR-058):** `POST /v1/staff` (admin) cria staff (argon2, e-mail único,
> auditado sem PII); MFA em dois passos — `enroll` (gera segredo + `provisioning_uri`, não ativa)
> e `confirm` (valida TOTP → ativa). 10 testes. **Pendências:** exigir MFA p/ admin; rotação de
> senha; convite por e-mail; lifecycle (listar/desativar).

### C4 — Captura de contato + **cifra de PII** · P0 · `DONE`
> **Concluída (2026-07-04, ADR-059):** `POST /v1/participants/{id}/contact` (staff `enroll:write`)
> grava nome/e-mail cifrados em repouso (AES-256-GCM; AAD amarra ao participante+campo), separados
> do dado de pesquisa; resposta neutra (sem PII); captura auditada sem PII (C1). Chave via
> `PII_ENC_KEY` (env/cofre), nunca versionada. 9 testes. **Pendências:** rotação de chave e KMS
> (prod); decifra é consumida na entrega de OTP (D1).
- **Objetivo:** popular `contact_info` (nome/e-mail) **cifrados em repouso** (envelope/AEAD),
  separados do dado de pesquisa. Pré-requisito para a entrega real de OTP por e-mail.
- **Contrato:** `POST /v1/participants/{id}/contact` (staff) — grava `enc_name`/`enc_email`.
- **Pronto:** dado gravado é ciphertext (teste); chave via KMS/env; decifra só no envio.
- **Inegociável:** PII cifrada/separada; LGPD.
- **ADR:** ADR-059 (cifra de campo/AEAD + custódia de chave).

### C5 — Procedimento de desbloqueio (unblinding) controlado · P1 · `TODO`
- **Objetivo:** `unblind:request` (admin) inicia desbloqueio auditado; a revelação usa a
  **chave selada** e é registrada. Nunca automático, nunca em massa sem justificativa.
- **Contrato:** `POST /v1/allocation/{participant}/unblind-request` + fluxo de aprovação.
- **Pronto:** pedido gera evento de auditoria; revelação exige papel+justificativa; teste
  garante que sem o procedimento nenhum endpoint expõe o braço.
- **ADR:** ADR-060.

### C6 — Exportação pseudonimizada (assíncrona) · P1 · `TODO`
- **Objetivo:** `POST /research/export` gera pacote pseudonimizado (reusa
  `instruments_scoring.py` export) via job; `GET` do status/arquivo.
- **Contrato:** já esboçado (`/research/export`, `JobAccepted`). **Depende de:** C1.
- **Pronto:** exportação não contém PII nem braço (antes do desbloqueio); job registrado em
  auditoria; teste do conteúdo exportado.
- **ADR:** ADR-061.

### C7 — Pipeline de análise + critérios de progressão (Etapa 7) · P1 · `TODO`
- **Objetivo:** rodar `analysis_plan.py` sobre a exportação: viabilidade/adesão/usabilidade,
  **índice de Bang** (cegamento), testes exploratórios, **critérios de progressão CONSORT-pilot**.
- **Depende de:** C6. **Pronto:** relatório reprodutível; índice de Bang a partir do
  `blinding_guess`; nada decide desfecho “ao vivo”.
- **ADR:** ADR-062.

---

## FASE D — Segurança, privacidade e infraestrutura · P0/P1
Endurecimento para dado real e para o CEP.

### D1 — SMTP: entrega real de OTP + notificação de EA · P0 · `DONE`
- Substitui os hooks `deliver_otp`/`notify_team` por envio real (fila + retries). **ADR-063.**
- **Pronto:** teste com fake SMTP; segredo em cofre; sem logar o código em produção.
> **Concluída (2026-07-04, ADR-063):** interface `EmailSender` (SMTP prod c/ retries; Null seguro;
> Console dev; Memory teste). `request-otp` envia o OTP ao e-mail **decifrado de C4** (best-effort,
> sem logar o código); `notify_team` alerta a equipe (sem PII) em EA moderate/severe. 5 testes.
> **Pendências:** fila assíncrona (RQ/ADR-031); segredo SMTP em cofre; bounces.

### D2 — Rate limiting + denylist de `jti` · P1 · `DONE`
- Limite por IP no `request-otp` e no `login`; revogação de token por `jti` (Redis).
- **Pronto:** testes de limite e de token revogado. **ADR-064.** (Pendência do ADR-043/047.)
> **Concluída (2026-07-04, ADR-064):** rate limit por IP (429, configurável) em `request-otp` e
> `login`; denylist por `jti` com `POST /auth/logout` (revoga access + refresh) e enforcement em
> `current_user`/`refresh`. Portas in-memory (teste) / Redis (prod via `REDIS_URL`). 6 testes.
> **Pendências:** confiança de proxy p/ IP real (`X-Forwarded-For`); política de falha do Redis.

### D3 — Docker + compose (Postgres/Redis) + segredos · P0 · `TODO`
- `docker-compose` para ambiente prod-like; migrações no deploy; config por ambiente/cofre.
- **Pronto:** `alembic upgrade` no Postgres real via compose; CI opcional com serviço Postgres.
- **ADR-065.**

### D4 — Direitos do titular (LGPD) + retenção · P1 · `TODO`
- Exportar/eliminar dados de um participante; política de retenção; registro em auditoria.
- **Pronto:** testes de export/delete respeitando append-only do audit. **ADR-066.**

### D5 — Observabilidade sem PII + CI endurecido · P1 · `TODO`
- Logs estruturados (sem PII/braço); métricas; tornar o job **Flutter** bloqueante quando
  houver widget tests; cobertura mínima. **ADR-067.**

---

## FASE E — Expansão (pós-piloto) · P2
Fora do caminho crítico do piloto; preparam integrações futuras (o `CLAUDE.md` já pede
modularidade para isso).

### E1 — Recomendador ao vivo (regras) · P2 · `TODO`
- Ativar o `recommender` (Etapa 6): seleciona **handle neutro/banda** dentro da biblioteca
  validada, registra `feature_vector` em `recommendation_log`. **ML nunca decide ao vivo.**
- **Inegociável:** só regras decidem; ML apenas registra para o futuro. **ADR-068.**

### E2 — Ingestão de vestíveis (adapter) · P2 · `TODO`
- Porta de entrada para FC/sono de wearables via **adaptador** desacoplado. **ADR-069.**

### E3 — Cloud storage para áudio · P2 · `TODO`
- Migrar a materialização/entrega de áudio (A1) para armazenamento em nuvem (URLs
  assinadas, sem vazar condição). **ADR-070.**

### E4 — Pipeline de features para ML (offline) · P2 · `TODO`
- Consolidar `recommendation_log`/telemetria para pesquisa de modelos — **sempre offline**,
  sem decisão clínica ao vivo. **ADR-071.**

### E5 — i18n / acessibilidade avançada · P2 · `TODO`
- Internacionalização e auditoria de acessibilidade (contraste, leitor de tela, movimento
  reduzido — já respeitado na visualização). **ADR-072.**

---

## Ordem sugerida de execução (caminho crítico do piloto)
`A1 → A2 → B1 → B2 → C1 → C4 → D1 → C2 → B3 → B4 → B5 → B6 → C6 → C7 → D3` — depois o resto
de D e a Fase E conforme necessidade. Racional: primeiro a sessão funcional (A), depois o
mínimo para **coletar com segurança** (login/baseline/auditoria/PII/e-mail), depois os
desfechos e a análise, e por fim o endurecimento de infraestrutura.

## Definição de Pronto (global, toda fatia)
1. Contrato (`shared-contracts/openapi.yaml`) atualizado **antes** do código e válido.
2. Testes cobrindo sucesso **e** caminhos de negação (401/403/404/409/422 conforme o caso).
3. CI-espelho verde: migração (SQLite) + `pytest`; **FFT**; OpenAPI; (Flutter quando aplicável).
4. Nenhuma decisão inegociável violada (cegamento, fidelidade, PII/LGPD, escopo do piloto).
5. **ADR** criado (formato ADR-041) e índice atualizado.
6. Sem segredo versionado; sem PII/braço em log; “ferramenta complementar” preservado.
