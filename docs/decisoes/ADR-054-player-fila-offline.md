# ADR-054 — Player real (bit-a-bit) + fila de telemetria offline

- **Status:** Aceito (código completo; testes Flutter ainda não rodados localmente — ver Conformidade)
- **Data:** 2026-07-04
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 2 (player-instrumento), 3 (UX/cegamento)
- **Contexto de origem:** Fatia A2 do ROADMAP (torna a sessão funcional de verdade no cliente)
- **Relaciona-se com:** ADR-053 (entrega de áudio / no-store), ADR-052 (UI de sessão não reativa)

## Contexto
Após A1 (entrega de áudio no backend), o cliente precisa **tocar** o WAV da sessão de forma
bit-a-bit, mantendo o **cegamento** (UI idêntica, visualização não reativa) e sem perder a
**telemetria de adesão** se a rede cair. O player atual era conduzido por relógio, sem áudio.

## Decisão
1. **Libs atrás de portas (isolamento):** `just_audio` e `path_provider` ficam atrás de
   `AudioPlayerPort` e `TelemetryQueue`. Motivos: (a) testabilidade — essas libs usam *platform
   channels* e não rodam em `flutter test`; os widget tests injetam fakes; (b) trocar de
   implementação sem tocar na tela; (c) não acoplar o caminho crítico a uma lib específica.
2. **Fidelidade bit-a-bit:** `downloadAudio` baixa os bytes e **verifica `sha256(corpo) == ETag`**
   (`AudioIntegrityException` se divergir — não toca). A reprodução usa uma fonte **em memória**
   (`StreamAudioSource`), **sem** reamostragem/normalização/DSP no cliente.
3. **Sem cache do áudio em disco (por design):** honra o `Cache-Control: private, no-store` de
   A1 — o áudio vive só em memória durante a sessão e é rebaixado a cada sessão. Persistir em
   disco exigiria cifra em repouso; fica como opção futura (não no piloto).
4. **Visualização não reativa (inegociável):** mantém-se `BreathingWave`, animada só pelo
   relógio; **não recebe nenhum sinal de áudio** (amplitude/frequência). Teste estrutural garante
   que o widget não expõe entrada de áudio — ativo e sham parecem idênticos.
5. **Fila de telemetria offline:** `TelemetrySender.submit` tenta enviar `POST
   /sessions/{id}/complete`; se falhar, **enfileira** (`FileTelemetryQueue`, um JSON por sessão);
   `flush` reenvia o pendente (best-effort) ao abrir a próxima sessão. Telemetria é **neutra**
   (duração efetiva, interrupções) — nunca o braço.
6. **Tela injetável:** `SessionPlayerScreen` recebe `player` e `telemetry` por construtor
   (fakes em teste); a fábrica `.production` monta as implementações reais.

## Alternativas consideradas
- **Chamar `just_audio`/`path_provider` direto na tela.** Rejeitada: widget tests do DoD
  ficariam impossíveis (MissingPluginException) e o acoplamento dificultaria trocar de lib.
- **Tocar via arquivo em disco (`setFilePath`).** Rejeitada: exigiria gravar o áudio
  decifrado/claro em disco, contrariando o `no-store`; a fonte em memória mantém o áudio transitório.
- **Sem fila (telemetria best-effort, como no player anterior).** Rejeitada: perderia adesão em
  quedas de rede — dado primário de viabilidade do piloto.
- **Contar duração pela posição de reprodução do just_audio.** Adiada: exigiria expor a posição
  pela porta; para o piloto, contar segundos efetivos por relógio enquanto toca é suficiente
  (aproximação de adesão, não medida sample-accurate).

## Consequências
- **Positivas:** sessão funcional ponta a ponta no cliente; cegamento preservado (UI idêntica,
  visualização não reativa testada); fidelidade verificada por hash; adesão não se perde offline.
- **Custo/tradeoff (visão do analista):**
  - **Duração efetiva é por relógio**, não pela posição real do áudio; se o dispositivo
    engasgar o áudio, o contador pode divergir levemente do ouvido. Aceitável para adesão.
  - **Sem cache** ⇒ re-download por sessão (custo de rede); ok no piloto (sessão curta, uma por vez).
  - **Deriva de plataforma:** a fonte em memória do `just_audio` assume WAV PCM tocável nativamente
    em iOS/Android; validar em dispositivo real (fora do `flutter test`).
- **Pendências:** cache com cifra em repouso (se necessário); expor posição real para duração
  sample-accurate; configuração nativa de `just_audio` (iOS `Info.plist`/Android) no build.

## Conformidade
Testes em `app/test/`: `telemetry_sender_test.dart` (envio ok não enfileira; falha enfileira;
`flush` reenvia e limpa; mantém na fila se ainda falha; round-trip JSON) e
`session_player_test.dart` (baixa e inicia reprodução; visualização não reativa; encerrar chama
`complete` com duração/interrupções corretas; falha de `complete` vai para a fila). O job `app`
do CI roda `flutter pub get && flutter analyze && flutter test`.
**Ressalva honesta:** estes testes **não foram executados localmente** nesta sessão (sem SDK
Flutter na máquina de desenvolvimento); a verificação real depende do job `app` do CI — que hoje
é **não-bloqueante** (`|| true`). Tornar esse job bloqueante é a fatia **D5**; recomenda-se
priorizá-la agora que há widget tests de verdade.
