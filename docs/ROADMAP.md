# ROADMAP — Sereno (backlog de fatias verticais)

> Documento vivo. É o backlog que se abre no Claude Code para executar a **próxima
> fatia**. Método fixo (não negociável): **contrato → código → teste (inclui caminhos de
> negação) → CI verde → ADR → próxima**. Simplicidade > complexidade. Escopo travado no
> **piloto de 4 semanas**; itens de expansão ficam em Fase E/F4 e não entram no caminho crítico.
>
> **Desde 2026-07-22 as fases de código (A–E) estão fechadas.** O que resta está na **Fase F** e,
> em sua maioria, **não é código** — é decisão institucional, ética ou operacional. O método acima
> vale para as fatias A–E; itens da Fase F fecham com **decisão registrada**, não com CI verde.

## Como ler
- **Prioridade:** `P0` = caminho crítico para um piloto coletável · `P1` = importante ·
  `P2` = expansão/pós-piloto.
- **Status:** `TODO` · `WIP` · `DONE`.
- **Pronto (DoD):** a fatia só fecha quando esses testes passam no CI e o ADR foi escrito.
- **Inegociáveis:** o que a fatia NÃO pode violar (ver `CLAUDE.md`).

## Estado atual (baseline deste roadmap)

> ### ⛳ Marco (2026-07-22): **todas as fases (A–E) `DONE`. O caminho crítico deixou de ser código.**
> CI do HEAD (`bf92fa9`) com 5/5 jobs verdes; **307 testes de backend a 90% de cobertura**,
> **42 widget tests** (Flutter), 4 migrações Alembic, bateria FFT aprovada. ADRs **041–091**.
>
> **O que falta para o piloto rodar não se resolve escrevendo código** — depende de base legal,
> CEP, DPO e prazos institucionais. O backlog dessas pendências está na **Fase F**, ao fim deste
> documento, organizada **por dono**. Antes de abrir qualquer fatia nova, olhe lá: a maior parte
> do que resta **não é sua para executar, é para cobrar**.

<details>
<summary>Histórico do baseline anterior (2026-07-09)</summary>

> **Marco (2026-07-09): caminho crítico do piloto (Fases A–D) `DONE` e verde.** CI do HEAD
> (`f78db58`) com 5/5 jobs verdes (backend, backend-postgres, `app`/Flutter bloqueante, contracts,
> audio-fft); reprodução local: 169 testes de backend a 85,0% de cobertura, 4 migrações Alembic,
> bateria FFT aprovada em todos os protocolos. **Só resta a Fase E (expansão pós-piloto, P2)** —
> travada por escopo no `CLAUDE.md` (não implementar sem decisão explícita do mantenedor).
> **Higiene de CI (2026-07-09):** actions atualizadas para o runtime Node 24
> (`actions/checkout@v7`, `actions/setup-python@v6`), eliminando o aviso de deprecação do Node 20.

</details>
- **Backend (169 testes verdes):** `problem+json`; banco/migração portáveis (4 migrações);
  auth de staff (argon2+JWT+MFA + **rate limit/denylist de jti — D2/ADR-064**); auth de
  participante (OTP + **entrega por e-mail — D1/ADR-063**); **gestão de staff + MFA enrollment
  (C3/ADR-058)**; consentimento; **triagem/elegibilidade + funil (C2/ADR-057)**; linha de base
  (PSQI+GAD-7); randomização + **alocação oculta** (com gate de inscrição); sessão + telemetria com **resolução cega**;
  **entrega de áudio bit-a-bit (A1/ADR-053)**; **auditoria append-only (C1/ADR-056)**;
  **captura de contato com PII cifrada (C4/ADR-059)**; desfechos (pós-sessão, diário); seguimento
  (PSQI+GAD-7+SUS+cegamento); evento adverso.
- **Stubs restantes:** — (o `recommender` foi ativado ao vivo em E1/ADR-068).
- **`recommendation_log`:** já alimentado pelo endpoint `POST /recommendations` (E1).
- **Flutter (não compilado no ambiente de planejamento):** fluxo do participante completo —
  **auto-login/refresh/logout (B1)** → OTP → consentimento → **Home com CTA de sessão + acesso às
  telas de registro (B2/B4/B5/B6)** → sessão com **áudio real bit-a-bit + telemetria offline (A2)**
  e visualização não reativa → **pós-sessão (B3) encaixado ao fim da sessão**. Telas B2–B6 ligadas
  à navegação. (Testes Flutter escritos, não executados aqui — sem SDK local; o job `app` do CI,
  **bloqueante** em erros, valida.)
- **ADRs:** 041–091 (índice em `docs/decisoes/`).
- **Consentimento (fluxo completo, 2026-07-22):** resumo em linguagem simples (7 tópicos, pt/en) →
  **texto integral do TCLE na tela** (ADR do rascunho em `docs/tcle-rascunho.md`; o asset do app é
  **gerado** do documento que vai ao CEP, e o CI falha se divergirem) → aceite versionado. Versão
  vigente: **`0.1.0-rascunho`** — o sufixo é deliberado enquanto não houver parecer do CEP.
- **Pacote documental LGPD/CEP:** checklist (`lgpd-nit-checklist.md`), **RIPD** 
  (`relatorio-impacto-protecao-dados.md`), **ROPA** (`registro-operacoes-tratamento.md`), retenção
  (`politica-retencao-descarte.md`), incidentes (`plano-resposta-incidentes.md`) e **TCLE**
  (`tcle-rascunho.md`). Todos rascunhos técnicos: decisões de terceiros marcadas `[a confirmar]`.

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

### A2 — Reprodução real + fila de telemetria offline (Flutter) · P0 · `DONE`
> **Código completo (2026-07-04, ADR-054):** download com verificação bit-a-bit (sha256==ETag),
> reprodução via porta `AudioPlayerPort` (just_audio isolado; fonte em memória, sem DSP, sem cache
> em claro), visualização mantida **não reativa**, e fila de telemetria offline (`TelemetrySender`
> + `FileTelemetryQueue`) com reenvio. Testes em `app/test/` (widget + unit).
> **Fechada (2026-07-09):** D5 tornou o job `app` do CI **bloqueante**; o CI do HEAD (`e2f768e`)
> passou verde com `flutter analyze` + `flutter test` — condição de fechamento satisfeita. Não há
> SDK Flutter no ambiente de dev; a validação é o job `app` do CI (verde).
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

### B1 — Persistência de login + refresh de token (Flutter) · P0 · `DONE` (via CI)
> **Código completo (2026-07-05, ADR-055):** auto-login (`AuthGate`), refresh transparente no 401
> (`ApiClient` renova e repete uma vez; refresh inválido → logout) e logout na Home. Testes em
> `app/test/auth_flow_test.dart` (MockClient + store fake). **Decisão:** SEM Riverpod/go_router
> agora (mínimo e testável; refactor de estado fica p/ fatia dedicada). **Validação:** job `app` do
> CI, agora bloqueante (não rodado localmente — sem SDK Flutter aqui).
- **Objetivo:** auto-login se houver token válido; refresh transparente no 401; logout limpa
  o armazenamento seguro. Roteamento inicial decide OTP vs Home conforme sessão.
- **Depende de:** —. **Contrato:** `POST /auth/refresh`.
- **Pronto:** widget/integration tests do fluxo de sessão persistida e de refresh no 401.
- **ADR:** ADR-055. **Sugestão:** adotar **Riverpod + go_router** aqui (ver ADR-050) e
  empacotar as **fontes** da identidade.

### B2 — Tela de linha de base (PSQI + GAD-7) · P0 · `DONE` (via CI)
> **Código completo (2026-07-05, ADR-073):** `BaselineScreen` compõe GAD-7 (`LikertGroup`) + PSQI
> (`PsqiSection`), envia itens brutos via `OutcomesRepository` (escore versionado no servidor),
> trata 409/422, não exibe escore alarmante, enunciados próprios. Base reutilizável (Likert/PSQI/
> repo) testada com MockClient. Validação via job `app` do CI (não rodado localmente).
- **Contrato:** `POST /participants/me/baseline` (feito). **Depende de:** B1.
- **Pronto:** widget tests — validação de faixa no cliente, envio, tratamento de 409/422;
  não exibe escore de forma alarmante (bem-estar).
- **Inegociáveis:** não reproduzir texto verbatim dos instrumentos; linguagem cuidadosa.

### B3 — Tela de pós-sessão · P1 · `DONE` (via CI)
- **Contrato:** `POST /sessions/{id}/survey` (feito). **Depende de:** A2.
> **Concluída (2026-07-05, ADR-073):** `PostSessionSurveyScreen` (itens 0–4 + "repetiria?"), trata 409.

### B4 — Tela de diário de sono · P1 · `DONE` (via CI)
- **Contrato:** `POST /diary` (feito). **Depende de:** B1.
> **Concluída (2026-07-05, ADR-073):** `SleepDiaryScreen` (registro do dia; campos opcionais), trata 409.

### B5 — Tela de seguimento (PSQI+GAD-7+SUS + item de cegamento) · P1 · `DONE` (via CI)
- **Contrato:** `POST /participants/me/followup` (feito). **Depende de:** B1.
- **Inegociável:** o item de cegamento captura só o **palpite**; a UI nunca sugere o braço.
> **Concluída (2026-07-05, ADR-073):** `FollowupScreen` (GAD-7 + PSQI + SUS + palpite). Item de
> cegamento neutro (Grupo A/B/Não sei — rótulos codificados, não revela ativo/sham).

### B6 — Tela de relato de evento adverso · P1 · `DONE` (via CI)
- **Contrato:** `POST /adverse-events` (feito). **Depende de:** B1.
- **Bem-estar:** para gravidade alta, a tela reforça orientação de buscar ajuda (192/CVV 188).
> **Concluída (2026-07-05, ADR-073):** `AdverseEventScreen` (tipo + gravidade + ação); gravidade
> **grave** reforça 192/CVV 188. Smoke tests renderizam as 5 telas; repositório testado (MockClient).

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
> e `confirm` (valida TOTP → ativa). 10 testes. **Pendências:** ~~exigir MFA p/ admin~~ (feito,
> ADR-074: MFA obrigatório p/ staff — login sem 2º fator só emite token de cadastro restrito);
> ~~rotação de senha~~ e ~~lifecycle (listar/desativar)~~ (feitos, ADR-081); convite por e-mail.
> **Lifecycle concluído (2026-07-20, ADR-081):** coluna `staff_user.is_active` (migração
> `c3d4e5f6a7b8`); `GET /v1/staff` (lista papel/MFA/ativo/último login, sem senha/segredo);
> `POST /v1/staff/{id}/deactivate|activate` (admin não se desativa — 409; 404/409 nas negações);
> `POST /v1/staff/me/password` (exige a atual, recusa igual, revoga o token em uso). O **RBAC
> confere `is_active` no banco** a cada requisição e as fronteiras de token (login/mfa-verify/
> refresh) recusam suspenso → o token já emitido para de valer na hora. Autoria preservada
> (suspender ≠ apagar). +11 testes (suíte 213→224, cobertura 89%). **Pendências:** reset de senha
> por admin (depende de e-mail); convite por e-mail. ~~Registro do `last_login_at`~~ feito
> (2026-07-21, ADR-090): gravado no `/auth/mfa/verify` — o único passo que concede acesso pleno;
> senha-sem-MFA e `refresh` **não** contam como login. +2 testes.

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

### C5 — Procedimento de desbloqueio (unblinding) controlado · P1 · `DONE`
> **Concluída (2026-07-04, ADR-060):** `POST /allocation/{id}/unblind-request` (admin
> `unblind:request`) revela a condição de UM participante via chave selada, exige justificativa,
> grava `unblind.performed` **sem** a condição na trilha e marca `unblinded_at`. Único caminho da
> API para a condição. 7 testes. **Pendência:** ~~aprovação por duas pessoas~~ (feita, ADR-075:
> pedido → aprovação por 2º admin distinto; a revelação só ocorre no 2º passo; 12 testes).
- **Objetivo:** `unblind:request` (admin) inicia desbloqueio auditado; a revelação usa a
  **chave selada** e é registrada. Nunca automático, nunca em massa sem justificativa.
- **Contrato:** `POST /v1/allocation/{participant}/unblind-request` + fluxo de aprovação.
- **Pronto:** pedido gera evento de auditoria; revelação exige papel+justificativa; teste
  garante que sem o procedimento nenhum endpoint expõe o braço.
- **ADR:** ADR-060.

### C6 — Exportação pseudonimizada (assíncrona) · P1 · `DONE`
> **Concluída (2026-07-04, ADR-061):** `POST /research/export` (`export:request`) monta o CSV
> pseudonimizado (reusa `build_export_csv`), casos completos, com **braço codificado A/B** (sem
> condição/chave) — decisão do mantenedor; `GET /research/export/{id}` devolve status/arquivo;
> pedido auditado. Job via porta in-memory (RQ+storage em prod). 5 testes.
- **Objetivo:** `POST /research/export` gera pacote pseudonimizado (reusa
  `instruments_scoring.py` export) via job; `GET` do status/arquivo.
- **Contrato:** já esboçado (`/research/export`, `JobAccepted`). **Depende de:** C1.
- **Pronto:** exportação não contém PII nem braço (antes do desbloqueio); job registrado em
  auditoria; teste do conteúdo exportado.
- **ADR:** ADR-061.

### C7 — Pipeline de análise + critérios de progressão (Etapa 7) · P1 · `DONE`
> **Concluída (2026-07-04, ADR-062):** `GET /research/analysis` (`research:read`) devolve relatório
> reprodutível e CEGO (braço A/B): funil, viabilidade (Wilson), SUS, **índice de Bang** por braço,
> exploratórios (GAD-7/PSQI) e **semáforo de progressão** pré-especificado. `nan`→`null`. Nada
> decide eficácia ao vivo. 6 testes.
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
> **Desacoplamento concluído (2026-07-20, ADR-085):** ~~fila assíncrona~~ fechada no essencial —
> porta **`EmailDelivery`** separa enfileirar de enviar: `inline` (padrão, síncrono) ou
> `background` (thread pool; o request retorna na hora, sem esperar o SMTP — tira o bloqueio do
> `request-otp` público e do EA/P0). O desfecho vira **métrica** `emails_total{outcome=sent|failed}`
> (ADR-080), acabando com a perda silenciosa; entrega **nunca propaga**; código nunca em log/métrica.
> +8 testes (suíte 249→257). **Pendências:** adaptador **RQ/Redis** (durabilidade/escala) — a
> "construção"; **bounces**; alerta quando `failed` subir; segredo SMTP em **cofre/KMS** (ops).

### D2 — Rate limiting + denylist de `jti` · P1 · `DONE`
- Limite por IP no `request-otp` e no `login`; revogação de token por `jti` (Redis).
- **Pronto:** testes de limite e de token revogado. **ADR-064.** (Pendência do ADR-043/047.)
> **Concluída (2026-07-04, ADR-064):** rate limit por IP (429, configurável) em `request-otp` e
> `login`; denylist por `jti` com `POST /auth/logout` (revoga access + refresh) e enforcement em
> `current_user`/`refresh`. Portas in-memory (teste) / Redis (prod via `REDIS_URL`). 6 testes.
> **Endurecimento (2026-07-14, ADR-078):** ~~confiança de proxy p/ IP real~~ fechada — resolução
> central `core/client_ip.py` (`CLIENT_IP_HEADER=Fly-Client-IP` na Fly / `TRUSTED_PROXY_HOPS`
> genérico; padrão = peer direto), à prova de spoof; o rate limit passa a valer por cliente real e
> não pela borda; consumida também pelo `ip_address` do consentimento. Suíte 190→200.
> **Endurecimento (2026-07-14, ADR-079):** ~~política de falha do Redis~~ fechada — postura única
> `SECURITY_FAIL_OPEN` (padrão fail-open: Redis fora não derruba login/OTP/auth; `=0` fail-closed
> prioriza defesa), `revoke()` best-effort, degradação com log de aviso sem PII. Suíte 200→206.
> **Pendências:** — (D2 concluída).

### D3 — Docker + compose (Postgres/Redis) + segredos · P0 · `DONE`
- `docker-compose` para ambiente prod-like; migrações no deploy; config por ambiente/cofre.
- **Pronto:** `alembic upgrade` no Postgres real via compose; CI opcional com serviço Postgres.
- **ADR-065.**
> **Concluída (2026-07-04, ADR-065):** `backend/Dockerfile` (slim, não-root, migração no
> entrypoint), `docker-compose.yml` (postgres:16 + redis:7 + backend, healthchecks), `.env.example`
> (segredos por env; `.env` gitignored; chave selada custodiada à parte) e job de CI
> `backend-postgres` (migração no Postgres real). **Não** verificável localmente (sem Docker aqui);
> validado por YAML + CI. **Pendências:** cofre/KMS; job de migração dedicado p/ multi-réplica.

### D4 — Direitos do titular (LGPD) + retenção · P1 · `DONE`
- Exportar/eliminar dados de um participante; política de retenção; registro em auditoria.
- **Pronto:** testes de export/delete respeitando append-only do audit. **ADR-066.**
> **Concluída (2026-07-05, ADR-066):** `GET /participants/{id}/data` (acesso; PII do próprio, sem
> braço) e `POST /participants/{id}/erase` (elimina PII direta, marca `withdrawn`, retém pesquisa
> pseudonimizada, **não apaga a auditoria**). Ambos admin (`user:manage`) e auditados. 5 testes.
> **Pendências:** deleção total (decisão CEP); self-service; expurgo agendado.

### D5 — Observabilidade sem PII + CI endurecido · P1 · `DONE`
- Logs estruturados (sem PII/braço); métricas; tornar o job **Flutter** bloqueante quando
  houver widget tests; cobertura mínima. **ADR-067.**
> **Concluída (2026-07-05, ADR-067):** logs JSON (`core/logging.py`) + middleware que registra
> só método/caminho/status/latência (nunca corpo/PII/braço); CI com cobertura ≥80% (hoje 84,67%) e
> job `app` (Flutter) **bloqueante** (sem `|| true`). 3 testes. **Atenção:** o gate Flutter passa a
> depender dos widget tests de A2 (não rodados localmente) — 1º CI confirma.
> **Endurecimento (2026-07-14, ADR-080):** ~~métricas~~ fechada — `GET /metrics` (Prometheus) via
> `core/metrics.py`, instrumentado no mesmo middleware; `http_requests_total` + `http_request_duration_seconds`
> com rótulo por **template de rota** (baixa cardinalidade, sem PII/braço; 404 → `<unmatched>`);
> guard opcional `METRICS_TOKEN`; `fly.toml` liga `[metrics]` p/ o scraping nativo da Fly. +7 testes
> (suíte 206→213).
> **Prontidão (2026-07-21, ADR-090):** ~~`/ready` real~~ fechada — sonda o **banco** na sessão da
> própria requisição (fora → 503, o roteador para de mandar tráfego) e o **Redis** com o peso do
> ADR-079 (fail-open → `degraded` mas pronto; fail-closed → não pronto). `/health` segue liveness
> puro. Corpo agregado, sem DSN/host/credencial. Junto veio `DB_CONNECT_TIMEOUT_S` (padrão 5s):
> sem ele, banco inalcançável **pendura** a sonda em vez de reprovar. +8 testes.
> **Pendências:** métricas de negócio + alertas (quando o piloto pedir).

---

## FASE E — Expansão (pós-piloto) · P2
Fora do caminho crítico do piloto; preparam integrações futuras (o `CLAUDE.md` já pede
modularidade para isso).

### E1 — Recomendador ao vivo (regras) · P2 · `DONE`
> **Concluída (2026-07-09, ADR-068):** `POST /v1/recommendations` (participante, `recommend:read`)
> liga o motor de regras: recebe contexto autorrelatado, **resolve os sinais de segurança no
> servidor** (evento adverso recente → de-escalona; triagem inelegível → `no_recommendation`),
> devolve **handle neutro** da biblioteca validada e registra tudo em `recommendation_log`
> (`feature_vector` p/ ML futuro; `no_recommendation` gravado com protocolo NULL — migração
> `b2c3d4e5f6a7`). 8 testes (objetivo→banda, guardrails, não-vazamento, negações); suíte 169→177,
> cobertura 87,2%. **Pendências:** ~~captura de aceite/coerência~~ (feita, ADR-069: aceite em
> `POST /recommendations/{id}/accept` + coerência cega em `GET /research/recommendation-coherence`;
> suíte 177→185); ~~vínculo recomendação→sessão para as médias de relaxamento da coerência~~ (feito,
> ADR-069 Complemento: `recommendation_id` opcional no start de sessão + `PostSessionSurvey.relaxation`;
> suíte 185→187); ~~janela temporal do EA~~ e ~~guardrail de tolerabilidade ao vivo (última
> pós-sessão)~~ (feitos, ADR-068 Complemento; suíte 187→190). **Recomendador completo** — só resta
> consolidação offline do `recommendation_log` (fatia E4).
- Ativar o `recommender` (Etapa 6): seleciona **handle neutro/banda** dentro da biblioteca
  validada, registra `feature_vector` em `recommendation_log`. **ML nunca decide ao vivo.**
- **Inegociável:** só regras decidem; ML apenas registra para o futuro. **ADR-068.**

### E2 — Ingestão de vestíveis (adapter) · P2 · `PARCIAL`
- Porta de entrada para FC/sono de wearables via **adaptador** desacoplado. **ADR-084.**
> **Seam concluído (2026-07-20, ADR-084) — escopo MÍNIMO, com sign-off (fora do MVP):**
> `POST /v1/wearables/readings` (participante, `wearable:write`) recebe leituras canônicas de
> FC/sono já normalizadas no device e as encaminha à porta **`WearableSink`** desacoplada
> (`Null` padrão = **descarta**, `Memory` = teste; selecionável por `WEARABLE_SINK`), no mesmo
> padrão de `EmailSender`/`AudioStorage`. Responde **202** (recebido); **sem persistência e sem
> migração** (preparação, não construção). **Não alimenta o recomendador ao vivo** (inegociável
> #5 — teste guarda que ingerir não cria recomendação e o `feature_vector` não ganha campo de
> vestível); auditoria **sem valores de saúde** (só contagem, inegociável #6). +8 testes
> (suíte 241→249, cobertura 89%). **Pendências (construção):** adaptador de persistência (tabela
> + migração + **cifra/separação** do dado sensível), consulta p/ pesquisa (offline/cego),
> mapeadores por provedor (payload cru→canônico) quando um device real for integrado.

### E3 — Cloud storage para áudio · P2 · `PARCIAL`
- Migrar a materialização/entrega de áudio (A1) para armazenamento em nuvem (URLs
  assinadas, sem vazar condição). **ADR-082.**
> **Seam concluído (2026-07-20, ADR-082):** porta de entrega `AudioStorage`
> (`modules/sessions/storage.py`) escolhida por `AUDIO_DELIVERY`. Padrão `inline` = A1
> **inalterado**; `signed-url` faz `GET /sessions/{id}/audio` responder **302** para
> `GET /v1/audio/{content_hash}` — endpoint **público-mas-assinado** (capability = HMAC-SHA256
> sobre `content_hash|exp`, subchave dedicada, TTL curto), sem `Authorization`, como um signed
> URL de nuvem. Chave = `content_hash` **opaco** (não revela braço; já conhecido do cliente);
> mesma resposta **bit-a-bit** (ETag, Range) e headers neutros; 403 genérico p/ assinatura
> inválida/expirada. +10 testes (suíte 224→234, cobertura 89%); A1 segue verde sem mudança.
> **Endurecimento (2026-07-21, ADR-090):** ~~rate limit no endpoint público~~ e ~~rotação da chave
> de assinatura~~ fechados — o freio por IP (`AUDIO_RATE_LIMIT`, 60/min) roda **antes** da
> verificação (limita também a varredura de assinatura) e responde 429 de forma idêntica nos dois
> braços; a chave ativa é a única que assina e as anteriores
> (`AUDIO_URL_SIGNING_KEYS_PREVIOUS`) seguem válidas só p/ verificar, então rotacionar não derruba
> quem está ouvindo. +6 testes.
> **Pendências (a "construção" da E3):** adaptador de storage em nuvem real (presign S3/GCS +
> upload do cache) — encaixa na mesma porta. Enquanto isso, o WAV ainda é servido pelo próprio backend (preparação, não
> offload completo — condizente com "escalabilidade preparada, não construída" do CLAUDE.md).

### E4 — Pipeline de features para ML (offline) · P2 · `DONE`
- Consolidar `recommendation_log`/telemetria para pesquisa de modelos — **sempre offline**,
  sem decisão clínica ao vivo. **ADR-083.**
> **Concluída (2026-07-20, ADR-083):** `GET /v1/research/ml-features` (staff `export:request`)
> achata o `recommendation_log` + telemetria de sessão/pós-sessão num **CSV** — uma linha por
> recomendação (inclui `no_recommendation` dos guardrails e recomendações sem sessão). **Offline**
> (inegociável #5): só consolida o já registrado, **não decide** nem cria recomendação (teste
> guarda a invariância da contagem). **Pseudonimizado** (só `study_code`; índice ordinal, sem hora
> de parede) e **cego** (só braço CODIFICADO A/B; `protocolo_sugerido` = handle neutro de banda;
> nunca ativo/sham). Auditado (`features.exported`, só nº de linhas). Sem migração. +7 testes
> (suíte 234→241, cobertura 89%). **Pendências:** consolidação por job offline (RQ)+storage;
> features derivadas/agregadas; versionar o schema do dataset quando a modelagem começar.

### E5 — i18n / acessibilidade avançada · P2 · `DONE`
> **Fundação concluída (2026-07-09, ADR-070):** delegate de i18n MANUAL (pt-BR padrão + en, sem
> code-gen), ligado ao `MaterialApp`; Home + disclaimer bilíngues; CTA com semântica de botão
> rotulada; `BreathingWave` passa a respeitar **movimento reduzido** (`disableAnimations`) — o
> ROADMAP supunha, erradamente, que já respeitava. 4 widget tests (pt/en, semântica, movimento
> reduzido).
> **Migração concluída (2026-07-09):** TODAS as telas do app migradas — Home, OTP, consentimento,
> preparo de sessão, player, pós-sessão e **B2–B6** (linha de base, diário, seguimento, evento
> adverso), incluindo os componentes compartilhados (`PsqiSection`, prompts GAD-7/SUS/PSQI) e o
> aviso persistente. Cliente **totalmente bilíngue** (pt-BR/en) via delegate manual; strings pt-BR
> idênticas às originais (fallback preserva os testes legados). +4 widget tests en. **Pendências
> (opcionais, fora do MVP):** extrair p/ ARB/`intl` se internacionalizar de fato; auditoria formal
> de contraste (AA) + leitor de tela ponta a ponta.
- Internacionalização e auditoria de acessibilidade (contraste, leitor de tela, movimento
  reduzido). **ADR-070.**

---

## FASE F — O que falta para o piloto rodar (não é código) · P0

> **Por que esta fase existe.** As fases A–E estão fechadas: o sistema coleta, protege, analisa e
> exporta. Mas **o piloto não pode começar a coletar dado real**, e nada disso se resolve abrindo
> uma fatia no Claude Code. Esta seção existe para que o backlog pare de sugerir que o trabalho
> restante é de programação — a maior parte é **de terceiros, para cobrar**, não para executar.
>
> Organizada **por dono**. O `CLAUDE.md` é explícito: LGPD, SaMD/ANVISA e PI exigem NIT + assessoria
> — **sinalizar, não decidir**. Os documentos em `docs/` são o insumo pronto para essas decisões.

### F1 — Bloqueadores institucionais (NIT / assessoria / DPO) · P0 · `TODO`
Nenhum depende de desenvolvimento. **O primeiro bloqueia todos os outros.**

| # | Pendência | Item | Insumo pronto |
|---|---|---|---|
| F1.1 | **Base legal** do tratamento de dado sensível de saúde (Art. 7 / Art. 11) | A2 | RIPD §4, ROPA (base por operação) |
| F1.2 | **Encarregado (DPO)** designado + canal público de atendimento ao titular | G1/D4 | ROPA §1, RIPD §2 |
| F1.3 | **Prazos de retenção** aprovados (proposta: 5 anos pós-encerramento) | E1 | `politica-retencao-descarte.md` §4 |
| F1.4 | **DPAs** com operadores (Fly.io, SMTP, GitHub Pages) + análise do Art. 33 | F2/F3 | ROPA §4 |
| F1.5 | **Adoção formal** do RIPD e do ROPA pelo controlador; decisão sobre risco residual aceitável e eventual consulta prévia à ANPD | G2/G3 | RIPD §10 |
| F1.6 | Enquadramento **SaMD/ANVISA** (confirmar que a copy "ferramenta complementar" afasta o risco) | G6 | postura científica do `CLAUDE.md` |

> ⚠️ **F1.1 é o bloqueador duro:** sem base legal definida **não se coleta dado real**. Tudo o mais
> pode avançar em paralelo, isso não.

### F2 — Aprovação ética (CEP) · P0 · `TODO`
| # | Pendência | Onde |
|---|---|---|
| F2.1 | **Aprovar o TCLE**; preencher `[a preencher]` (título, contatos, CEP, DPO) | `tcle-rascunho.md` §N2 |
| F2.2 | **Detalhes do protocolo clínico** — critérios de inclusão/exclusão, nº de sessões por semana, tempo total. **Não existem em nenhum lugar do repositório**; hoje são `[a confirmar com o protocolo]` no TCLE §4/§5 | `tcle-rascunho.md` §4, §5 |
| F2.3 | **Via digital basta?** — se o registro no app substitui a assinatura, e como a via é entregue | `tcle-rascunho.md` §16, §N2 |
| F2.4 | **Eliminação do dado de pesquisa já coletado** a pedido do titular: permitida, e em que condições | D3, RIPD R-10 |
| F2.5 | **Salvaguardas de recrutamento** contra assimetria de poder: convite por pessoa **sem vínculo de avaliação** com o candidato; desistência que não passe pelo pesquisador | **RIPD R-09** |

> ⚠️ **F2.5 é o maior risco residual do RIPD (Alto) e nenhum código o reduz.** O TCLE §11 já diz que
> recusar não traz prejuízo — necessário, mas não suficiente: o resto é procedimento de convite.

### F3 — Operacional (mantenedor / ops) · P0/P1 · `TODO`
Depende de infraestrutura no ar ou de credencial, não de escrever código.

| # | Pendência | Estado do código |
|---|---|---|
| F3.1 | **Agendar o expurgo de OTP** (cron ou máquina agendada da Fly) | ✅ Mecanismo pronto e testado (ADR-091). **Enquanto ninguém agendar, não roda** — receita em `deploy-fly.md` §3.1 |
| F3.2 | **SMTP real** (sem ele o OTP não é entregue em produção) | ✅ Código pronto (ADR-063/085); falta credencial em cofre |
| F3.3 | **Deploy na Fly** | ✅ `fly.toml` + runbook prontos (ADR-076); depende de cartão |
| F3.4 | Ao aprovar o TCLE: trocar a versão para `1.0.0` em **3 lugares** — `TCLE_CURRENT` (backend), `tcleVersion` (`app/lib/core/config.dart`) e conferir o resumo do app | Testes e seed importam a constante → **uma linha em cada** |
| F3.5 | **Pentest externo** antes de dado real | ⬜ C12 |
| F3.6 | Com **≥2 réplicas**: trocar o health check do `fly.toml` de `/health` para `/ready` | ✅ `/ready` real (ADR-090); com 1 réplica derrubaria a app num soluço do Postgres |

### F4 — Construção pós-piloto (código, **exige sign-off**) · P2 · `TODO`
Fora do MVP por decisão de escopo (`CLAUDE.md`). Todos têm o *seam* pronto — são "construir o que
já está preparado", não redesenhar.

| # | Item | Porta/seam existente |
|---|---|---|
| F4.1 | Adaptador **KMS/Vault** real | `KeyProvider.wrap/unwrap` (ADR-087/088) |
| F4.2 | **Expurgo do dataset** ao fim do prazo | módulo `retention` (ADR-091) — **bloqueado por F1.3** |
| F4.3 | Storage de áudio em **nuvem** (presign S3/GCS) | `AudioStorage` (ADR-082) |
| F4.4 | **Persistência cifrada** de vestíveis | `WearableSink` (ADR-084) |
| F4.5 | Adaptador **RQ/Redis** para e-mail (durabilidade) + bounces | `EmailDelivery` (ADR-085) |
| F4.6 | **Alertas** automáticos sobre métricas (falha de e-mail, acesso anômalo) | `/metrics` (ADR-080) — fecha detecção de RIPD R-03/R-06 |
| F4.7 | Reset de senha por admin + convite por e-mail (staff) | C3 (ADR-081) |
| F4.8 | Exibir o **texto integral** também em inglês, ou restringir o estudo ao pt-BR | `tcle-rascunho.md` §N4.6 |

---

## Ordem sugerida de execução

**Agora (Fase F):** `F1.1 (base legal) → F2.1/F2.2 (TCLE + protocolo, com o CEP) → F1.2 (DPO) →
F1.3 (prazos) → F2.5 (recrutamento) → F3.2/F3.3 (SMTP + deploy) → F3.1 (agendar expurgo) →
F3.4 (versão 1.0.0 do termo)`.

Racional: **F1.1 destrava tudo** (sem base legal não se coleta). F2.1/F2.2 andam em paralelo com o
CEP e alimentam o TCLE. F3 só faz sentido quando houver o que colocar no ar. **F4 não entra sem
sign-off do mantenedor** — é expansão de escopo.

<details>
<summary>Ordem histórica das fatias de código (A–E, todas concluídas)</summary>

`A1 → A2 → B1 → B2 → C1 → C4 → D1 → C2 → B3 → B4 → B5 → B6 → C6 → C7 → D3` — depois o resto
de D e a Fase E conforme necessidade. Racional: primeiro a sessão funcional (A), depois o
mínimo para **coletar com segurança** (login/baseline/auditoria/PII/e-mail), depois os
desfechos e a análise, e por fim o endurecimento de infraestrutura.

</details>

## Definição de Pronto (global, toda fatia)
1. Contrato (`shared-contracts/openapi.yaml`) atualizado **antes** do código e válido.
2. Testes cobrindo sucesso **e** caminhos de negação (401/403/404/409/422 conforme o caso).
3. CI-espelho verde: migração (SQLite) + `pytest`; **FFT**; OpenAPI; (Flutter quando aplicável).
4. Nenhuma decisão inegociável violada (cegamento, fidelidade, PII/LGPD, escopo do piloto).
5. **ADR** criado (formato ADR-041) e índice atualizado.
6. Sem segredo versionado; sem PII/braço em log; “ferramenta complementar” preservado.

> **Vale para as fatias de código (A–E).** Os itens da **Fase F** não fecham com CI verde: fecham
> com **decisão registrada** de quem tem competência para tomá-la (parecer do CEP, designação do
> Encarregado, prazo aprovado, DPA assinado). Ao receber uma dessas, atualize o item aqui, o
> `lgpd-nit-checklist.md` e o documento correspondente — os três precisam contar a mesma história.
