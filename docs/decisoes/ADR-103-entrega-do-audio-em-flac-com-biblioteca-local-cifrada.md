# ADR-103 — Entrega do áudio em FLAC, servida do disco, com biblioteca local cifrada

- **Status:** Aceito
- **Data:** 2026-08-30
- **Decisores:** Mantenedor (Augusto) — escolheu "FLAC + cache no aparelho" entre as opções
  postas — + arquiteto (Claude)
- **Etapas relacionadas:** 2 (áudio como instrumento), 5 (backend), 6 (segurança/LGPD)
- **Contexto de origem:** item **G1** do `docs/ROADMAP.md`, aberto pelo ADR-100 — o único
  item da Fase G marcado como **bloqueador**.
- **Relaciona-se com:** ADR-053 (entrega de áudio sem vazamento), ADR-054 (player e a decisão
  de *não* guardar o áudio), ADR-082 (URL assinada), ADR-100 (parâmetros do estímulo).

## Contexto

O ADR-100 trouxe para o código o estímulo do protocolo aprovado: **20 minutos, 48 kHz,
16 bits, estéreo**. A conta que ninguém tinha feito antes:

```
48 000 amostras/s × 2 canais × 2 bytes × 1 200 s = 230 MB por arquivo
```

Isso quebrava o piloto em três lugares ao mesmo tempo:

1. **No servidor.** `materialize_audio` devolvia `bytes` e o endpoint respondia com o corpo
   inteiro em memória. Dois participantes simultâneos = meio giga de RAM; a instância de
   1 GB do plano de deploy morreria antes do terceiro.
2. **No aparelho.** O ADR-054 carregava o WAV inteiro em memória e o entregava ao player.
   230 MB em memória é morte anunciada em aparelho de entrada — e o piloto não seleciona
   participantes por aparelho.
3. **Na rede do participante.** 20 sessões × 230 MB = **4,6 GB** de dados móveis, pagos por
   quem aceitou colaborar com uma pesquisa. Isso não é um detalhe técnico: é abandono do
   estudo por um motivo que a engenharia criou.

O ADR-054 tinha decidido **não guardar** o áudio no aparelho, e por uma razão que continua
válida: um arquivo em claro no armazenamento é uma rota de **desmascaramento** — uma FFT
sobre ele revela Δf = 3 Hz (ativo) ou Δf = 0 (controle). O mesmo ADR já registrava, como
pendência, "cache com cifra em repouso (se necessário)". O protocolo tornou necessário.

## Decisão

### 1. O artefato servido passa a ser FLAC (sem perdas)

`AUDIO_FORMAT=flac` é o padrão; `wav` continua disponível para depuração e para ambiente
sem `libsndfile`. O estímulo é um par de senoides — material em que a predição linear do
FLAC vai muito bem: medido no sinal do estudo, **14,2% do tamanho do WAV**, ou seja
**230 MB → ~33 MB**. As 20 sessões saem de 4,6 GB para ~33 MB (um download só, ver item 3).

A troca só é legítima porque o FLAC é **sem perdas**: o PCM decodificado é idêntico ao do
WAV, amostra a amostra. Isso não é assumido, é **testado** —
`tests/test_audio_format.py::test_flac_decodifica_para_o_mesmo_pcm_do_wav` renderiza o mesmo
protocolo nos dois formatos e compara os quadros; um teste irmão faz o mesmo para o braço de
controle (Δf = 0), porque um codificador que tratasse canais correlacionados de forma especial
poderia degradar **só um dos braços** — e artefato assimétrico é vazamento de braço.
A decisão inegociável #3 já previa "WAV/FLAC" como empacotamento sem perdas.

### 2. Materializar e servir sem carregar o arquivo na memória

- `render_protocol_to_file` sintetiza em janelas e **escreve direto no arquivo**; o processo
  nunca segura a sessão inteira.
- `RenderedAudio` deixou de carregar `wav_bytes` e passou a ser um **handle** (caminho,
  sha256, tamanho), com `chunks(start, end)` lendo do disco em janelas de 256 KB.
- O endpoint responde com `StreamingResponse` sobre esse gerador, no 200 e no 206.
- **A validação por FFT passou a ler o arquivo gravado**, e não só a síntese em memória. Com
  um codificador no caminho, validar o sinal antes de codificar deixaria de falar sobre o que
  o participante ouve. Falhou a conferência, nada é publicado: a escrita é em `.tmp` e o
  `os.replace` só acontece depois de a FFT aprovar o artefato.

### 3. O aparelho guarda o áudio — cifrado — e revalida em vez de rebaixar

- **Uma entrada por `content_hash`** (a identidade opaca do protocolo), então as 20 sessões
  usam o mesmo arquivo.
- **`If-None-Match` → 304.** A cada sessão o app pergunta se o artefato que tem continua
  vigente. Continua: nada trafega. Mudou: o corpo novo é gravado por cima. Isso também cobre
  a troca de formato ou uma rematerialização no servidor.
- **Cifrado em repouso** (`AudioCache`): cifra de fluxo em modo contador sobre HMAC-SHA256,
  com chave de 32 bytes sorteada na primeira execução e guardada no **Keystore/Keychain**.
  Não é AES por uma razão prática: o app já depende de `crypto` (SHA-256, usado na conferência
  bit-a-bit) e não de uma biblioteca de cifra de bloco; a construção contador+PRF é a mesma
  ideia do CTR, com HMAC no lugar do AES, e é **acessável por deslocamento** — que é o que
  permite ao player pedir faixas sem decifrar o arquivo inteiro.
- **Cifra-então-autentica:** um HMAC sobre o criptograma sela a entrada. Conferir o selo custa
  uma passada de hash; entrada que não confere é **descartada**, não tocada.
- **Fidelidade bit-a-bit onde sempre esteve:** o sha256 do texto claro é calculado **enquanto**
  o corpo chega e conferido contra o `ETag`. Divergiu, nada é publicado e a exceção sobe.
- **Sem rede, a sessão do dia acontece** com a entrada já conferida. Sem rede e sem entrada, o
  erro sobe — fingir que há áudio seria pior.
- **Logout apaga a biblioteca e esquece a chave.**

### 4. O player recebe uma FONTE, não bytes

`AudioPlayerPort.loadBytes(Uint8List)` virou `load(AudioBytesSource)`, com `read(start, end)`
devolvendo um **fluxo**. O `just_audio` pede faixas conforme decodifica e nós as produzimos do
disco, decifrando só o pedaço pedido. `loadBytes` continua existindo como atalho para áudio
curto em memória (o tom da verificação dicótica de fones, ADR-101).

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| **Manter WAV, só transmitir em blocos** | Resolve o servidor e a memória do aparelho, não a rede: 230 MB no primeiro download de cada participante, em 4G. |
| **Baixar a taxa de amostragem** (250/253 Hz cabem em 22 kHz) | Tecnicamente correto e ainda mais barato — mas o protocolo aprovado **diz 48 kHz**. Mudar é **emenda ao CEP**, não refatoração. Fica registrado como opção caso a emenda aconteça por outro motivo. |
| **Sintetizar o estímulo no próprio aparelho** | Quebraria o cegamento de vez: o cliente precisaria conhecer Δf. |
| **Guardar em claro no armazenamento privado do app** | É a rota de desmascaramento que o ADR-054 recusou; o custo de cifrar é pequeno perto disso. |
| **AES via nova dependência** (`pointycastle`) | Ganho de segurança marginal sobre HMAC-CTR neste uso, custo de dependência nova no caminho crítico do áudio. |

## Consequências

**Boas**

- O piloto passa a ser executável em rede móvel: ~33 MB uma vez, por participante.
- O servidor deixa de ter um limite de concorrência ditado pela RAM.
- O que ficava só em memória agora é **conferido a cada uso** (selo) — mais rigor, não menos.
- `If-None-Match` dá, de graça, a detecção de "o artefato mudou no servidor".

**Custos e riscos assumidos**

- **Dependência nova no backend:** `soundfile` (libsndfile). Se faltar, a materialização
  **falha alto** (`EncoderUnavailable`) em vez de cair em silêncio para 230 MB de WAV — a
  falha é do operador, não do participante. A imagem Docker instala `libsndfile1`.
- **O ETag do FLAC depende da versão do libFLAC** (a string de identificação do codificador
  entra no arquivo). Atualizar a biblioteca do sistema muda o `ETag`, e os aparelhos rebaixam
  o áudio uma vez. O PCM decodificado não muda — o estímulo é o mesmo.
- **O áudio agora persiste no aparelho.** Cifrado, com chave no Keystore, apagado no logout —
  mas persiste. Contra quem tem escrita no armazenamento privado **e** leitura do Keystore,
  isso não protege; nesse cenário o aparelho já está comprometido. O alvo declarado é o
  participante curioso e a corrupção acidental.
- **`Cache-Control: private, no-store` continua no ar** e é deliberado: nenhum intermediário
  guarda o áudio. A biblioteca local do app não é um cache HTTP — é armazenamento da aplicação,
  cifrado, com política própria.
- **Os testes de widget novos (`audio_cache_test.dart`) só rodam no CI** — não há SDK Flutter
  no ambiente de desenvolvimento.

## Verificação

- `backend/tests/test_audio_format.py` (8): equivalência PCM FLAC↔WAV nos dois braços, redução
  de tamanho, validação lendo o artefato gravado, artefato parcial nunca publicado, ausência do
  codificador falhando alto, formato inválido recusado, leitura por faixas.
- `backend/tests/test_session_audio.py` (9): DoD do A1 preservado + `If-None-Match` → 304 sem
  corpo, sem vazar braço, e o ETag de um braço **não** revalida o arquivo do outro.
- `backend/tests/test_pilot_protocol.py`: a síntese em janelas continua não mudando um bit —
  agora nos **dois** formatos.
- `app/test/audio_cache_test.dart` (10): o gravado não fica em claro e volta bit-a-bit; faixas
  arbitrárias exatas; ETag divergente não publica; entrada adulterada é descartada; outra chave
  não lê; a segunda sessão **não rebaixa**; artefato trocado substitui; offline usa o guardado;
  logout limpa; problem+json continua virando `ApiException`.
