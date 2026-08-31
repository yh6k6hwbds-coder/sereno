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
| 055 | Persistência de login + refresh transparente no 401 + logout (cliente) **[novo]** |
| 056 | Log de auditoria append-only (guard ORM + GRANT; leitura admin `audit:read`) **[novo]** |
| 057 | Triagem/elegibilidade (regra versionada) + gate do funil de alocação **[novo]** |
| 058 | Gestão de staff (admin) + cadastro de MFA em dois passos (enroll→confirm) **[novo]** |
| 059 | Cifra de PII em repouso (AES-256-GCM/AEAD, AAD por participante+campo; chave em env) **[novo]** |
| 060 | Desbloqueio controlado (admin+justificativa, chave selada, auditado sem a condição) **[novo]** |
| 061 | Exportação pseudonimizada (casos completos; braço codificado A/B, sem condição; job/porta) **[novo]** |
| 062 | Pipeline de análise (relatório cego: Bang, viabilidade, exploratórios) + semáforo de progressão **[novo]** |
| 063 | Entrega de e-mail (interface): OTP por e-mail (decifra C4) + alerta de EA, best-effort **[novo]** |
| 064 | Rate limiting por IP (429) + denylist de token por `jti` (logout/revogação) **[novo]** |
| 065 | Docker + compose (Postgres/Redis) + segredos por env; migração no deploy; CI Postgres **[novo]** |
| 066 | Direitos do titular LGPD (acesso/eliminação de PII; retém pesquisa + auditoria) **[novo]** |
| 067 | Observabilidade (logs JSON sem PII/braço) + CI endurecido (cobertura ≥80%, Flutter bloqueante) **[novo]** |
| 068 | Recomendador por regras ao vivo: `POST /recommendations` (handle neutro), sinais de segurança no servidor, registro + `feature_vector` **[novo]** |
| 069 | Fecho do loop do recomendador: aceite (`POST /recommendations/{id}/accept`) + coerência cega (`GET /research/recommendation-coherence`) **[novo]** |
| 070 | i18n (delegate manual pt-BR/en) + acessibilidade (semântica de botão, movimento reduzido) — fundação na Home **[novo]** |
| 073 | Telas de captura de desfechos (B2–B6): componentes Likert/PSQI reutilizáveis + OutcomesRepository **[novo]** |
| 074 | MFA obrigatório para staff: login sem 2º fator dá só token de cadastro restrito (sem escopo) **[novo]** |
| 075 | Desbloqueio em duas pessoas: pedido (não revela) → aprovação por 2º admin distinto (revela) **[novo]** |
| 076 | Deploy do backend na Fly.io (região gru/São Paulo) + residência de dados no Brasil **[novo]** |
| 077 | Selagem real da chave A/B→condição + guard de config de produção (fail-fast) **[inegociável]** |
| 078 | IP real do cliente atrás de proxy (`CLIENT_IP_HEADER`/`TRUSTED_PROXY_HOPS`): rate limit por cliente, não pela borda **[novo]** |
| 079 | Política de falha do Redis (rate limit/denylist): fail-open por padrão, configurável (`SECURITY_FAIL_OPEN`) **[novo]** |
| 080 | Métricas Prometheus (`GET /metrics`) sem PII/braço, rótulo por template de rota (baixa cardinalidade); guard `METRICS_TOKEN` **[novo]** |
| 081 | Lifecycle de staff: `is_active` (desativar suspende o token já emitido; RBAC confere no banco), listar time, rotação da própria senha **[novo]** |
| 082 | Entrega de áudio por URL assinada (porta `AudioStorage`; chave = content_hash opaco; HMAC + TTL; A1 inline por padrão) **[novo]** |
| 083 | Pipeline de features p/ ML **offline e cego**: consolida `recommendation_log`+telemetria em CSV pseudonimizado; ML não decide ao vivo **[novo]** |
| 084 | Ingestão de vestíveis: **seam** desacoplado (porta `WearableSink` Null/Memory; sem device, sem persistência); não alimenta a decisão ao vivo **[novo]** |
| 085 | Entrega de e-mail desacoplada do request (porta `EmailDelivery` inline/background) + métrica de desfecho (`emails_total`); fecha a fila do D1 **[novo]** |
| 086 | Auditoria append-only reforçada **no banco** (trigger aborta UPDATE/DELETE, mesmo do dono; REVOKE como extra); não só no ORM — fecha C8 **[novo]** |
| 087 | Custódia da chave de PII atrás de porta `KeyProvider` (KMS-ready) + rotação por id de chave no ciphertext; env por padrão **[novo]** |
| 088 | Envelope encryption da PII: DEK por registro embrulhada pela KEK (porta `wrap`/`unwrap`); KEK nunca cifra a PII — padrão real de KMS **[novo]** |
| 089 | Retirada de consentimento self-service (titular): `revoked_at` + status `withdrawn` + bloqueia novas sessões; retirar ≠ eliminar — fecha B3 **[novo]** |
| 090 | Endurecimento operacional: rate limit no endpoint público de áudio (antes da verificação), rotação da chave de assinatura, `/ready` real (DB+Redis, com timeout) e `last_login_at` gravado **[novo]** |
| 091 | Expurgo dos desafios de OTP (1º pedaço do E2): só apaga o **já expirado** (apagar vivo zeraria `attempts`); auditado só na contagem; script agendável **[novo]** |
| 092 | Entrega de e-mail **durável** (fila RQ/Redis + worker) e **bounce** separado de falha transitória (`emails_total{outcome=bounced}`); 5xx não é reintentado; corpo do OTP com TTL curto no Redis **[novo]** |
| 093 | **Alertas automáticos** em processo (falha de e-mail, rajada de 401, 5xx em série, volume atípico em `/research`): janela + cooldown, sem PII no aviso, laço de realimentação quebrado — fecha detecção de R-03/R-06 **[novo]** |
| 094 | **Convite e redefinição de senha de staff** por token de uso único (só hash no banco): o admin destrava, **não** escolhe a senha nem vê o token; redefinir **não** desliga o MFA **[novo]** |
| 095 | Custódia da chave de PII em **Vault Transit** (`KEY_PROVIDER=vault`): a KEK não sai do cofre, AAD vira `context` de *derived key*, dado antigo segue legível pelo env — fecha C11 no código **[novo]** |
| 096 | **Tela de definir senha de staff** no app web, alcançável só por `?token=` (rota antes do AuthGate; não existe no mobile); token sai da barra de endereço — fecha a ponta que faltava do ADR-094 **[novo]** |
| 097 | **Piloto só em pt-BR:** `supportedLocales` fica só com `pt` (o TCLE existe só em português — ninguém consente por interface traduzida sem documento correspondente); tradução `en` preservada em `translatedLocales` **[novo]** |

| 098 | **Fase F fecha com documento de cobrança por dono:** NIT, pesquisadora e CEP recebem cada um um pedido com perguntas objetivas, opções mapeadas e **folha de resposta** — descrever a pendência não a fazia andar. Registra também o achado do `prescribed=20` na taxa de adesão **[novo]** |

| 099 | **Versão do TCLE verificada no CI** (`scripts/tcle_version.py --check`): backend e app declaravam-na em linguagens diferentes e nada checava que concordam — divergir só apareceria como 409 na cara do participante. Trocar vira um comando; F3.4 não era "uma linha em cada" **[novo]** |

| 100 | **O estímulo passa a ser o do protocolo aprovado:** 250 Hz / 253 Hz (Δf = 3 Hz, delta), 20 min, 48 kHz, rampas 30 s/60 s; controle = mesmo protocolo com `beat_hz = 0`; taxa e rampas viram colunas; equalização de energia entra no gate; adesão exige 80% da duração **[novo]** |

| 101 | **Verificação DICÓTICA de fones** (o participante identifica a orelha; errar reinicia o teste) no lugar da caixa de seleção, com a evidência gravada por sessão; e **teto de volume por software** — ganho travado no app, declarado ao iniciar e recusado acima de `AUDIO_MAX_GAIN` **[novo]** |

| 102 | **PHQ-9 de segurança** (não é desfecho; item 9 separado no resultado), **regra de risco versionada** (GAD-7 >= 15 / item 9 / relato) valendo igual na triagem e no seguimento, **retirada do protocolo** que para a sessão de fato, **ficha de encaminhamento** com confirmação de acolhimento e contagem no relatório ao CEP. Resposta ao participante **sem escore**, com orientação sempre **[novo]** |

| 103 | **Entrega do áudio em FLAC** (sem perdas: mesmo PCM do WAV, 14% do tamanho — 230 MB viram ~33 MB), **servida do disco em janelas** (nem materializar nem transmitir carrega a sessão na memória) e **biblioteca local cifrada** no aparelho, revalidada por `If-None-Match`: as 20 sessões baixam o arquivo uma vez, sem deixar o estímulo em claro onde uma FFT revelaria o braço **[novo]** |

| 104 | **Blocos permutados de tamanho VARIÁVEL (4 e 6)**, como o protocolo especifica: com bloco fixo e conhecido, a última posição de cada bloco é dedutível das anteriores — previsão de alocação, que é o que a randomização em blocos deveria impedir. O tamanho sai da mesma semente (reprodutibilidade intacta); `ALLOCATION_BLOCK_SIZE` é recusada em voz alta **[novo]** |

| 105 | **Critérios de elegibilidade do protocolo codificados e FECHADOS** (7 inclusões, 9 exclusões (a)–(i)): chave faltando/desconhecida é 422, faixa sintomática (GAD-7 5–14 e/ou PSQI > 5) e a alínea (d) são **derivadas dos escores**, e a triagem vazia deixou de ser elegível — `all([])` respondia `True`. Catálogo em `GET /screening/criteria` **[novo]** |

| 106 | **A avaliação intermediária (T2) vira um momento e a descontinuação vira um registro:** janela abrindo ao fim da 2ª semana com convite na Home, status `discontinued` que **para a sessão e mantém o ITT**, os três critérios do protocolo (pedido, evento adverso, adesão < 50%) e uma varredura que alcança quem parou de abrir o app. Dose e régua de adesão passam a viver em `core/protocol.py` **[novo]** |

Para novas decisões, criar `ADR-041-titulo.md` com: contexto, decisão, alternativas, consequências.
