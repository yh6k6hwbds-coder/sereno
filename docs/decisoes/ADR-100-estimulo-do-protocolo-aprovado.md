# ADR-100 — O estímulo passa a ser o do protocolo aprovado (250/253 Hz, 3 Hz, 20 min)

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) — "aplique as frequências binaurais seguindo a metodologia" — + arquiteto (Claude)
- **Etapas relacionadas:** 1 (requisitos), 2 (player como instrumento), 4 (métricas/adesão)
- **Contexto de origem:** projeto de iniciação científica, seção **Protocolo de intervenção**
  (`PROJETO de IC - Augusto André.docx`), que pela primeira vez especifica os parâmetros do
  estímulo por inteiro.
- **Relaciona-se com:** ADR-046 (resolução cega da sessão), ADR-053 (entrega sem vazamento),
  ADR-054 (player/fidelidade), ADR-068 (recomendador), ADR-098 (achado do `prescribed=20`).

## Contexto

Até aqui a biblioteca de estímulos era de **referência**, não de estudo: três protocolos de
**30 segundos** com portadora de 200 Hz (alpha-10, theta-6, delta-2), que existiam para provar que
a síntese e a validação por FFT funcionavam. Nenhum deles é o que o participante vai ouvir, e a
tabela `audio_protocol` nasce **vazia** na migração inicial — em produção não havia estímulo algum.

O protocolo aprovado fixa tudo o que faltava:

> tom portador puro de 250 Hz na orelha esquerda e 253 Hz na direita (diferença interaural de
> **3 Hz**, faixa delta); controle com 250 Hz idêntico nas duas orelhas, **energia acústica
> equalizada**; 20 minutos por sessão, 5 sessões semanais, 4 semanas; 48 kHz, 16 bits, sem
> compressão com perdas; rampa de entrada de 30 s e de saída de 60 s; 60 dB(A) calibrados com
> limite imposto por software.

São números de **pesquisa**, não de engenharia: cada um tem justificativa no projeto
(JIRAKITTAYAKORN; WONGSAWAT, 2018, para o par 250 Hz/3 Hz) e mudá-los é emenda de protocolo.

## Decisão

1. **`PILOT_LIBRARY` é a biblioteca do estudo** (`audio-pipeline/binaural_instrument.py`): um único
   protocolo `delta-3` v1.0.0 — 250 Hz, Δf 3 Hz, 1200 s, 48 kHz, 16 bits, rampas 30 s/60 s. A antiga
   `REFERENCE_LIBRARY` continua existindo, rebaixada a **biblioteca de desenvolvimento** (30 s),
   explicitamente marcada como "nenhum participante ouve isto".
2. **O controle não é um arquivo à parte:** é o mesmo protocolo com `beat_hz = 0`. Ativo e sham
   saem da mesma fórmula, com o mesmo envelope e o mesmo teto — a única diferença é o canal direito.
3. **Rampas assimétricas e taxa de amostragem viram parâmetros do protocolo**, colunas de
   `audio_protocol` (`sample_rate`, `fade_in_s`, `fade_out_s`; migração `f6a7b8c9d0e1`). Estavam em
   constantes do módulo de render, e isso tinha duas consequências ruins: a linha do banco **não
   determinava o artefato** (auditoria incompleta) e trocar uma constante mudaria em silêncio o
   áudio de um protocolo já validado. Linhas existentes recebem 44,1 kHz e 3 s/3 s — nada muda.
4. **Equalização de energia entre os braços vira item do gate de CI**
   (`validate_arm_energy_match`): o RMS de cada canal, em regime permanente, tem de coincidir entre
   ativo e sham dentro de 0,05 dB. É consequência da fórmula, mas passa a ser **verificada**: se um
   braço soar mais alto que o outro, o participante ganha uma pista audível e o cegamento cai.
5. **Síntese e validação por trechos.** 20 min a 48 kHz são ~57,6 M amostras por canal: em float64
   estéreo, ~920 MB. A pipeline valida os trechos que importam (regime permanente, início e fim) e o
   backend materializa em janelas de 10 s. O resultado é **bit-a-bit** idêntico ao do sinal inteiro
   — há teste que compara os dois caminhos.
6. **`scripts/seed_protocols.py` carrega a biblioteca em produção**, idempotente, recusando semear
   um protocolo que não passe na FFT. O `content_hash` é **aleatório** (32 bytes), não derivado dos
   parâmetros: o protocolo é público, então um hash determinístico permitiria a qualquer pessoa
   recalcular os dois valores e descobrir o braço a partir do que o cliente recebeu. O `seed_demo`
   passou a espelhar o estudo (delta, 250/253 Hz, 30 s) para exercitar o mesmo caminho.
7. **O handle do estudo é `delta`.** O aplicativo enviava `alpha` por padrão — sobra do tempo em que
   a banda era escolhida. Nesta fase o protocolo é **fixo**: sem personalização, sem escolha do
   participante, sem recomendador ao vivo (o app nunca chamou `/recommendations`, e continua sem).
8. **Adesão passa a exigir 80% da duração.** O protocolo define sessão concluída como a que rodou
   pelo menos 80% do tempo prescrito; o backend marcava `completed = True` em **qualquer**
   encerramento. Como adesão é **desfecho primário**, isso inflaria o resultado: quem abriu o áudio
   por dois minutos contava igual a quem ouviu os vinte. A régua é do servidor, usa a duração do
   protocolo **congelado na sessão** e responde `counts_for_adherence` (idêntico nos dois braços).

## Alternativas consideradas

- **Manter a biblioteca de 3 bandas e escolher a faixa por participante.** Rejeitada: o próprio
  protocolo desativa a personalização nesta fase, justamente para não introduzir heterogeneidade
  dentro do braço experimental. Manter a escolha aberta convidaria a usá-la.
- **Deixar taxa e rampas como constantes do módulo.** Rejeitada: ver decisão 3 — a linha do banco
  precisa determinar o artefato inteiro para a auditoria valer.
- **`content_hash` determinístico (hash dos parâmetros ou de um rótulo).** Rejeitada: seria opaco só
  para quem não leu o projeto. É o valor que vai ao cliente.
- **Renderizar o sinal inteiro em memória.** Rejeitada: ~920 MB por materialização derruba a
  instância e não escala com a duração.
- **Contar adesão por sessão iniciada.** Rejeitada: mede abertura de app, não exposição.

## Consequências

- **Positivas:** o estímulo que roda é o que está no protocolo submetido; o gate de CI valida o
  estímulo **do estudo** (e não um substituto de 30 s); a auditoria fecha (a linha do banco descreve
  o arquivo por inteiro); a adesão passa a medir o que o protocolo diz que mede.
- **Custo:** +1 migração; `render_protocol` ganhou parâmetros; a resposta de encerramento mudou de
  `{"status": "completed"}` para `{"status": "recorded", …, "counts_for_adherence": …}` (contrato
  atualizado antes do código).
- **⚠️ Pendência dura — tamanho do arquivo.** 20 min a 48 kHz, 16 bits, estéreo = **230 MB por
  arquivo** em WAV. O backend hoje lê o corpo inteiro na memória a cada requisição e o cliente
  guarda os bytes em memória (ADR-054, sem cache em disco por design): nesse formato o piloto **não
  roda**. O conteúdo está certo; o **invólucro** precisa de decisão do mantenedor — a recomendação é
  **FLAC** (sem perdas, permitido pelo `CLAUDE.md` e pelo protocolo, decodificação bit-a-bit, e um
  tom puro comprime muito), o que implica uma dependência de codificação no backend. Alternativas:
  transmitir por Range direto do disco (muda A1/E3) ou reduzir a taxa de amostragem (**emenda de
  protocolo**). Nada disso foi decidido aqui.
- **⚠️ Pendência — leito ambiente.** O protocolo promete "trilha de fundo ambiental de baixa
  intensidade, idêntica em conteúdo, duração e nível" nos dois braços, e **rejeita** mascaramento por
  ruído rosa. Hoje o instrumento sintetiza tons puros e o gate exige **pureza espectral** (energia
  fora do fundamental ≤ −60 dB) — um leito reprovaria a bateria como está. Ou o leito sai do
  protocolo, ou entra como sinal determinístico e a verificação de pureza vira razão tom/leito.
- **⚠️ Pendência — 60 dB(A).** O arquivo carrega um teto **digital** (−12 dBFS). O nível absoluto
  depende do transdutor e do aparelho: a calibração em acoplador de orelha (etapa (i) do protocolo)
  é que amarra dBFS a dB(A), e o "limite imposto por software" ainda não existe no cliente.
- **A verificação de fones continua sendo uma caixa de seleção.** O protocolo exige teste dicótico
  (o participante identifica em qual orelha soou o sinal). Sem ele, `headphones_ok` é declaração,
  não verificação — e a condição dicótica é pré-requisito do fenômeno.

## Conformidade

CI verde exige: bateria FFT sobre a `PILOT_LIBRARY` (ativo, sham e equalização de energia) e sobre a
biblioteca de desenvolvimento; `audio-pipeline/tests/test_pilot_protocol.py` (parâmetros, dose,
equivalência trecho↔sinal inteiro, rampas assimétricas);
`backend/tests/test_pilot_protocol.py` (parâmetros do seeder, opacidade do `content_hash`, síntese em
blocos bit-a-bit, régua de 80% e resposta neutra); migração `f6a7b8c9d0e1` aplicada; OpenAPI válido.
