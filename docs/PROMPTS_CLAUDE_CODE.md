# PROMPTS_CLAUDE_CODE — Sereno

> Prompts prontos para colar no **Claude Code (VS Code)**. Servem para executar as fatias do
> `docs/ROADMAP.md` com o nosso método. Fluxo por fatia: **contrato → código → teste (com
> caminhos de negação) → CI verde → ADR → fim**. Cole o **§0** no início de cada sessão; depois
> o prompt da fatia (§2) ou use o template (§1).

---

## §0 — Prompt de abertura de sessão (cole primeiro, uma vez por sessão)

```
Você é o arquiteto e engenheiro principal do projeto Sereno (piloto de neuromodulação não
invasiva: Flutter + FastAPI). Aja como COLABORADOR CRÍTICO, não como executor complacente:
não concorde automaticamente, aponte vieses e limitações, proponha melhorias, e prefira
SIMPLICIDADE a complexidade. Trate o app sempre como FERRAMENTA COMPLEMENTAR ao cuidado em
saúde (nunca substitui avaliação/tratamento profissional) e toda recomendação clínica deve
ter base em literatura reconhecida.

Antes de agir, leia: CLAUDE.md (decisões inegociáveis e convenções), docs/ROADMAP.md (backlog),
docs/decisoes/ (ADRs 041–052) e shared-contracts/openapi.yaml (fonte de verdade da API).

Método OBRIGATÓRIO por fatia:
1) Atualize o contrato OpenAPI ANTES de escrever código.
2) Implemente a fatia (código limpo, modular, documentado, tipado; docstrings em PT-BR).
3) Escreva testes cobrindo sucesso E caminhos de negação (401/403/404/409/422 conforme o caso).
4) Rode o CI-espelho e deixe VERDE:
   backend: `cd backend && alembic upgrade head && pytest -q`
   áudio:   `cd audio-pipeline && python binaural_instrument.py`
   contrato:`python -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('shared-contracts/openapi.yaml')))"`
   Flutter (quando aplicável): `cd app && flutter pub get && flutter analyze && flutter test`
5) Escreva um ADR (formato de docs/decisoes/ADR-041) e atualize o índice.
6) Faça commit atômico com mensagem descritiva.

NUNCA viole as decisões inegociáveis: cegamento (o braço nunca vaza por API/UI; resolução só no
servidor; visualização não reativa ao áudio), fidelidade do estímulo (síntese offline validada
por FFT; reprodução bit-a-bit; verificação de fones), PII cifrada/separada + LGPD, e o ESCOPO
travado no piloto de 4 semanas. Se precisar tocar numa decisão inegociável, PARE e me explique
antes, com um ADR justificando.

Confirme que leu esses arquivos e me diga qual fatia vamos executar.
```

---

## §1 — Template de prompt por fatia (preencha o ID)

```
Execute a fatia <ID> do docs/ROADMAP.md (ex.: A1).
Siga o método do §0 (contrato → código → testes com caminhos de negação → CI verde → ADR → commit).
Antes de começar, me mostre em 5–8 linhas: (a) o que vai mudar no contrato, (b) os arquivos que
vai criar/editar, (c) os testes que provam o "Pronto (DoD)" da fatia, (d) qual inegociável a
fatia toca e como você o preserva. Aguarde meu "pode ir" só se houver ambiguidade; caso contrário,
execute e ao final rode o CI-espelho e cole o resultado.
```

---

## §2 — Prompts prontos (caminho crítico do piloto)

### A1 — Endpoint de entrega de áudio
```
Execute a fatia A1 (entrega de áudio) do ROADMAP.
Objetivo: GET /v1/sessions/{id}/audio que transmite o WAV da sessão do participante autenticado,
BIT-A-BIT, sem vazar o braço. O servidor resolve o protocolo internamente (reuse resolve_arm /
sessions.service.resolve_protocol); o cliente pede pelo session_id, nunca pelo braço.
Requisitos:
- Materialize o WAV de cada protocolo de forma determinística com audio-pipeline/binaural_instrument.py
  e valide por FFT antes de servir (ativo: pico em beat_hz; sham: Δf=0).
- Headers: Content-Type de áudio, ETag=content_hash, Accept-Ranges: bytes, Cache-Control: private,
  no-store. Suporte a Range (206). Erros em problem+json.
Testes (DoD): (1) baixa o áudio da própria sessão (200, ETag==content_hash); (2) IDOR: sessão
alheia → 404; (3) sem vazamento: braços opostos → mesma FORMA de resposta/headers, bytes/hash
diferem mas nenhum metadado revela ativo/sham/beat; (4) fidelidade: sha256(corpo)==content_hash;
(5) Range retorna 206 correto; (6) o job de FFT valida o WAV servido.
Inegociáveis: resolução só no servidor; nenhum header revela condição; bit-a-bit; síntese offline
validada por FFT. Atualize o contrato ANTES. Crie ADR-053. Rode o CI-espelho.
Decisões a registrar no ADR: onde materializar o WAV (disco local por ora; cloud é Fase E) e como
o cliente faz cache sem persistir áudio em claro.
```

### A2 — Reprodução real + fila de telemetria offline (Flutter)
```
Execute a fatia A2 (Flutter). O player deve tocar o WAV baixado em A1 de forma bit-exata (sugestão:
just_audio + path_provider para cache), mantendo a VISUALIZAÇÃO NÃO REATIVA ao áudio (só tempo).
Telemetria (duração efetiva, interrupções) enfileirada em disco e reenviada se POST
/sessions/{id}/complete falhar.
Testes de widget (DoD): player inicia após download; pausa/retomada conta interrupção; complete é
chamado com valores corretos; falha de complete → fica na fila e reenvia; teste garante que a
visualização independe do sinal de áudio. Crie ADR-054. Rode flutter analyze && flutter test.
Não use DSP no cliente; não exiba nada do braço.
```

### B1 — Persistência de login + refresh (Flutter)
```
Execute a fatia B1 (Flutter). Implemente auto-login se houver token válido, refresh transparente
no 401 (POST /auth/refresh), e logout que limpa o armazenamento seguro. Adote Riverpod + go_router
nesta fatia (ver ADR-050) e empacote as fontes da identidade (Fraunces/Inter/IBM Plex Mono).
Testes (DoD): sessão persistida abre Home; token expirado dispara refresh e repete a chamada;
refresh inválido volta ao OTP. Crie ADR-055. Rode flutter analyze && flutter test.
```

### B2 — Tela de linha de base (PSQI + GAD-7)
```
Execute a fatia B2 (Flutter). Formulário de baseline consumindo POST /participants/me/baseline
(schema PSQIIn + gad7_items). Validação de faixa no cliente; tratamento de 409 (já registrada) e
422; NÃO exibir escore de forma alarmante; NÃO reproduzir texto verbatim dos instrumentos (use
enunciados próprios/curto). Testes de widget do envio e dos erros. Crie ADR. Rode analyze && test.
```

### C1 — Log de auditoria append-only (transversal)
```
Execute a fatia C1 (backend). Registre ações sensíveis (consentimento, alocação, pedido de
exportação, pedido/execução de desbloqueio) em audit_log, APPEND-ONLY, SEM PII e SEM o braço.
Adicione um serviço de auditoria chamado pelos módulos e um GET /research/audit (admin) para leitura.
Testes (DoD): cada ação sensível grava um evento; tentativa de UPDATE/DELETE em audit_log é barrada
(invariante de serviço no teste; GRANT no Postgres em produção — registre no ADR). Atualize o
contrato. Crie ADR-056. Rode o CI-espelho.
```

### C4 — Captura de contato + cifra de PII
```
Execute a fatia C4 (backend). POST /v1/participants/{id}/contact (staff) grava nome/e-mail
CIFRADOS em repouso em contact_info (AEAD/envelope; chave via env/KMS — nunca versionada),
separados do dado de pesquisa. Decifra só no momento do envio (pré-requisito do OTP por e-mail).
Testes (DoD): o dado gravado é ciphertext (não texto claro); round-trip decifra corretamente;
sem a chave não há leitura. Atualize o contrato. Crie ADR-059 (cifra de campo + custódia de chave).
Inegociáveis: PII cifrada/separada; LGPD. Rode o CI-espelho.
```

### D1 — SMTP: entrega real de OTP + notificação de EA
```
Execute a fatia D1 (backend). Substitua os hooks deliver_otp e notify_team por envio real por
e-mail (com fila e retries), atrás de uma interface (para trocar provedor). Em produção, segredo
em cofre; NUNCA logar o código OTP. Testes (DoD): com um SMTP fake, request-otp dispara envio e a
verificação segue funcionando; notify_team envia alerta em EA moderado/grave. Crie ADR-063.
Rode o CI-espelho.
```

> As demais fatias (B3–B6, C2/C3/C5/C6/C7, D2–D5, Fase E) seguem o mesmo padrão — use o **§1**
> com o ID e os campos do ROADMAP.

---

## §3 — Checklist de fechamento (cole ao terminar a fatia)

```
Antes de considerar a fatia pronta, verifique e me confirme item a item:
[ ] Contrato OpenAPI atualizado ANTES do código e válido.
[ ] Testes cobrem sucesso E os caminhos de negação pertinentes (401/403/404/409/422).
[ ] CI-espelho verde: migração+pytest; FFT; OpenAPI; (Flutter analyze+test quando aplicável).
[ ] Nenhuma decisão inegociável violada (cegamento, fidelidade, PII/LGPD, escopo do piloto).
[ ] ADR criado (formato ADR-041) e índice em docs/decisoes atualizado.
[ ] Sem segredo versionado; sem PII/braço em log; "ferramenta complementar" preservado.
[ ] Commit atômico com mensagem descritiva.
Cole o resumo do que mudou, o resultado do CI e o número do ADR.
```

---

## §4 — Frases úteis (colar quando precisar)

- **Pedir crítica real:** “Antes de implementar, aponte 3 riscos ou fraquezas desta abordagem e
  uma alternativa mais simples. Só então implemente a que você recomendar, justificando.”
- **Forçar contract-first:** “Você tocou a API sem atualizar o openapi.yaml? Corrija o contrato
  primeiro e me mostre o diff.”
- **Cobrar os caminhos de negação:** “Faltam testes de negação. Adicione os casos 401/403/404/409/422
  que se aplicam a esta fatia.”
- **Proteger o cegamento:** “Prove por teste que nenhuma resposta/UI desta fatia revela o braço, e
  que a resolução ativo/sham ocorre só no servidor.”
- **Evitar escopo inflado:** “Isso está além do piloto de 4 semanas? Se sim, mova para a Fase E do
  ROADMAP e faça só o mínimo desta fatia.”
- **Fechar com ADR:** “Escreva o ADR desta fatia no formato do ADR-041 (Contexto → Decisão →
  Alternativas → Consequências → Conformidade) e atualize o índice.”
