# Registro de Decisões Arquiteturais (ADR)

Log das decisões técnicas das Etapas 1–7. Reverter qualquer uma exige nova entrada
e aviso ao mantenedor (ver `CLAUDE.md`). As marcadas **[inegociável]** quebram o CI se violadas.

| ID | Decisão |
|---|---|
| 001 | Monólito modular em vez de microserviços |
| 002 | Flutter/Dart no cliente |
| 003 | Python/FastAPI no backend |
| 004 | PostgreSQL + SQLAlchemy/Alembic |
| 005 | Cliente offline-first com sincronização |
| 006 | Recomendador por regras (não ML) **[inegociável]** |
| 007 | Sham ativo + alocação oculta **[inegociável]** |
| 008 | GAD-7 (autorrelato) no lugar da HAM-A |
| 009 | Síntese determinística + validação por FFT **[inegociável]** |
| 010 | Conhecimento clínico separado do mecanismo; humano no loop |
| 011 | Camada LLM/RAG educativa deferida (fora do MVP) |
| 012 | Síntese offline validada + reprodução bit-a-bit **[inegociável]** |
| 013 | Áudio sem perdas; proibir codecs com perdas e DSP **[inegociável]** |
| 014 | Sham = placebo ativo com Δf = 0 (casado) **[inegociável]** |
| 015 | Ocultação de alocação por handle opaco **[inegociável]** |
| 016 | Fones com fio recomendados; Bluetooth avisado/registrado |
| 017 | Teto de volume + calibração no 1º uso |
| 018 | Identidade "noturna calma"; acento quente só para avisos |
| 019 | Tela de sessão em tema escuro e minimalista |
| 020 | Visualização ambiente NÃO reativa ao áudio **[inegociável]** |
| 021 | Tipografia monoespaçada para dados |
| 022 | Navegação inferior + um único CTA por tela |
| 023 | Nome "Sereno" provisório (validar marca/INPI) |
| 024 | PostgreSQL com integridade no banco + migrações |
| 025 | PKs UUID + timestamptz |
| 026 | PII cifrada e separada; pesquisa pseudonimizada **[inegociável]** |
| 027 | Braço codificado + chave A/B selada à parte **[inegociável]** |
| 028 | argon2id + JWT (access/refresh) + MFA (staff) |
| 029 | Erros em problem+json (RFC 9457) + idempotência |
| 030 | Auditoria append-only |
| 031 | Processamento assíncrono com Redis + worker |
| 032 | Recomendador por regras (reafirmação) |
| 033 | Seleção restrita à biblioteca validada (invariante) **[inegociável]** |
| 034 | Guardrails avaliados antes das regras |
| 035 | Registro completo + `feature_vector`; ML nunca decide ao vivo |
| 036 | Conjunto de regras versionado (`ruleset_version`) |
| 037 | Enquadramento CONSORT-piloto; primários de viabilidade |
| 038 | Cegamento por índice de Bang (validado); James por ferramenta validada |
| 039 | Critérios de progressão pré-especificados (semáforo) |
| 040 | Exploratórios como geradores de hipótese (α=5%, sem correção de multiplicidade) |
| 041 | Estrutura do repositório e fronteiras de módulo |
| 042 | Modelos e migração portáveis (Postgres prod, SQLite testes) **[novo]** |
| 043 | Autenticação de staff (argon2id + JWT + MFA TOTP) **[novo]** |
| 044 | Linha de base (PSQI+GAD-7): bruto + escore versionado **[novo]** |
| 045 | Randomização em blocos e alocação oculta **[novo]** |
| 046 | Sessão e resolução cega do áudio (ativo/sham) **[novo]** |
| 047 | Autenticação de participante por e-mail + OTP (sem senha) **[novo]** |
| 048 | Telemetria de desfechos: pós-sessão e diário de sono **[novo]** |
| 049 | Seguimento (PSQI+GAD-7+SUS+cegamento) e bruto reprodutível **[novo]** |
| 050 | Fundação do cliente Flutter (OTP + consentimento) **[novo]** |
| 051 | Relato de evento adverso com sinalização de atenção **[novo]** |
| 052 | UI de sessão idêntica e visualização não reativa (cegamento) **[novo]** |
| 053 | Entrega de áudio da sessão sem vazamento + fidelidade bit-a-bit (`audio_sha256` = ETag) **[novo]** |
| 054 | Player bit-a-bit (portas p/ just_audio) + fila de telemetria offline **[novo]** |
| 056 | Log de auditoria append-only (guard ORM + GRANT; leitura admin `audit:read`) **[novo]** |
| 059 | Cifra de PII em repouso (AES-256-GCM/AEAD, AAD por participante+campo; chave em env) **[novo]** |

Para novas decisões, criar `ADR-041-titulo.md` com: contexto, decisão, alternativas, consequências.
