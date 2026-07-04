# ADR-053 — Entrega de áudio da sessão sem vazamento + fidelidade bit-a-bit

- **Status:** Aceito
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 2 (player-instrumento), 5 (backend)
- **Contexto de origem:** Fatia A1 do ROADMAP (torna a sessão funcional de verdade)
- **Relaciona-se com:** ADR-046 (resolução cega da sessão), ADR-009/012/013 (áudio como instrumento)

## Contexto
A sessão hoje é conduzida por relógio; o participante não recebe o áudio de verdade. A1
adiciona `GET /v1/sessions/{id}/audio`, que transmite o WAV da própria sessão — autenticado,
**bit-a-bit**, **sem vazar o braço**. O protocolo (ativo/sham) já foi resolvido no início da
sessão (ADR-046) e **congelado** em `session.protocol_uuid`; esta rota apenas o serve.

O ROADMAP pedia, no mesmo item, `ETag == content_hash` **e** `sha256(corpo) == content_hash`.
Isso é contraditório com o código atual: `content_hash` é a **identidade OPACA do protocolo**
(no banco/testes, um sha256 de rótulo de 64 chars; na pipeline, um hash de parâmetros de 16
chars) — **não** o hash dos bytes do WAV (que sequer eram serializados). Resolver essa
ambiguidade é o cerne desta decisão.

## Decisão
1. **Separar identidade de integridade.** `content_hash` permanece a identidade opaca do
   protocolo (inalterado). Introduz-se **`audio_sha256`** = `sha256` dos **bytes do WAV
   materializado**, usado como **`ETag`** e como prova de fidelidade bit-a-bit. `ETag` passa a
   ter a semântica HTTP correta (identifica a representação em bytes), não a identidade lógica.
2. **Materialização determinística no servidor**, uma vez por protocolo, com **cache em disco**
   (`backend/.audio_cache/<content_hash>.wav` + sidecar `.sha256`; nome opaco, sem revelar
   condição). A síntese replica a fórmula canônica de `audio-pipeline/binaural_instrument.py`
   (portadora em L, portadora+Δf em R, envelope raised-cosine) em `sessions/audio_render.py`.
   O sham **não** é caso especial: com `beat_hz == 0`, R coincide com L e Δf = 0 surge naturalmente.
3. **Validação por FFT antes de servir.** `render_protocol` valida a atribuição de canais por
   FFT (L na portadora; R na portadora+Δf) e só então serializa. Um teste decodifica o **WAV
   servido** e reconfere os picos (ativo com Δf medido ≈ `beat_hz`; sham com Δf ≈ 0).
4. **Sem re-resolução do braço nesta rota.** A rota carrega `session.protocol_uuid` e serve;
   não chama `resolve_arm`/`condition_for_arm`. Menos superfície = menos risco de vazamento.
5. **Headers neutros e idênticos entre braços:** `Content-Type: audio/wav`, `ETag`,
   `Accept-Ranges: bytes`, `Cache-Control: private, no-store`. Só os **bytes** (opacos) diferem.
6. **Range/retomada:** suporte a um único intervalo `bytes=` → `206` com `Content-Range`;
   faixa insatisfazível → `416`. Erros em problem+json: `401` (sem token), `404` (IDOR — sessão
   não é do participante), `409` (protocolo indisponível na biblioteca).

## Alternativas consideradas
- **Redefinir `content_hash` = sha256 do WAV (64 chars).** Rejeitada agora: quebraria o
  `content_hash` de 16 chars da pipeline e os `protocol_hash` já gravados nas sessões; exigiria
  migração e realinhamento da pipeline. A separação (opção adotada) é menos invasiva e corrige
  a semântica do ETag.
- **Persistir `audio_sha256` em coluna de `audio_protocol`.** Adiada: o valor é **determinístico**
  a partir dos parâmetros do protocolo; um sidecar em disco (“registro”) evita uma migração
  nesta fatia. Gatilho para promover a coluna: materialização *ahead-of-time* por pipeline de
  build e garantia de integridade no banco.
- **Sintetizar/streamar sob demanda sem cache.** Rejeitada: WAV de 20 min ≈ 200 MB; re-sintetizar
  por requisição é caro. Cache materializado + `Range` cobre retomada.
- **Reusar `binaural_instrument.py` por import direto.** Inviável hoje (a pasta `audio-pipeline`
  tem hífen e não é pacote importável do backend). Mantém-se a fórmula espelhada + validação FFT
  como guarda contra deriva; unificar num pacote compartilhado fica como follow-up (fora de A1).

## Consequências
- **Positivas:** sessão funcional de verdade; cegamento preservado (testado: braços opostos →
  mesma forma de headers, nenhum metadado nomeia a condição); fidelidade provada
  (`sha256(corpo) == ETag`); retomada por `Range`; estímulo validado por FFT no próprio artefato
  servido. Suíte: 63 → 70 testes.
- **Custo/tradeoff (visão do analista):**
  - **Deriva de síntese:** a fórmula existe em dois lugares (pipeline e backend). Mitigado por
    validação FFT em ambos; risco residual até a unificação.
  - **`ETag`/bytes diferem entre braços.** É esperado e opaco (análogo ao `content_hash` no
    start), mas significa que **igualdade de tamanho de arquivo** poderia, em tese, ser um canal
    lateral fraco entre ativo e sham. No piloto, ativo e sham têm a **mesma duração/portadora/
    envelope** ⇒ tamanho idêntico; convém manter esse invariante (mesma duração por par) para não
    abrir pista por `Content-Length`. Registrado como invariante de governança.
  - **Cache em disco local** não escala horizontalmente; a migração para nuvem (URLs assinadas,
    sem vazar condição) é a Fase E / ADR-070.
- **Pendências:** invariante “ativo e sham do mesmo par têm duração idêntica”; unificação da
  síntese num pacote compartilhado; decisão futura sobre coluna `audio_sha256`.

## Conformidade
CI verde exige a nova suíte `tests/test_session_audio.py` passando: 200 na própria sessão;
404 por IDOR; 401 sem token; 409 protocolo indisponível; **não-vazamento** (headers de mesma
forma entre braços, sem termos que revelem a condição); **fidelidade** (`sha256(corpo) == ETag`);
**FFT do WAV servido** (ativo com Δf correto, sham Δf = 0); `206`/`416` para `Range`. Nenhum
header/metadado revela ativo/sham/beat; a resolução do braço permanece fora desta rota.
