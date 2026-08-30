# ADR-101 — Verificação dicótica de fones e teto de volume por software

- **Status:** Aceito
- **Data:** 2026-08-30
- **Decisores:** Mantenedor (Augusto) — "siga para G3 e G4" — + arquiteto (Claude)
- **Etapas relacionadas:** 2 (player como instrumento), 3 (UX), 5 (backend)
- **Contexto de origem:** itens **G3** e **G4** do `docs/ROADMAP.md`, abertos pelo ADR-100 a
  partir do protocolo de iniciação científica ("Posologia e contexto de uso" e "Intensidade e
  segurança auditiva").
- **Relaciona-se com:** ADR-100 (estímulo do protocolo), ADR-054 (player/fidelidade),
  ADR-052 (UI da sessão idêntica nos dois braços).

## Contexto

O protocolo promete duas coisas antes de cada sessão que o sistema não fazia.

**A verificação de fones era uma caixa de seleção.** "Meus fones estéreo estão conectados" é uma
declaração: fone em uma orelha só, cabo invertido, saída em mono ou alto-falante do aparelho
passariam batido — e são exatamente as situações em que a diferença interaural, que é o
estímulo, deixa de existir. O texto do protocolo é explícito: *"o aplicativo executará
verificação obrigatória de fones, na qual o participante identifica em qual orelha o sinal de
teste foi apresentado; a sessão não é liberada em caso de falha"*.

**O volume não tinha teto.** O protocolo prevê intensidade calibrada em 60 dB(A) "com limite
máximo imposto por software e impossibilidade de ultrapassá-lo pelo usuário". Não havia limite
algum: o áudio tocava no volume do aparelho, e a tela não declarava nada sobre nível.

## Decisão

### G4 — a verificação vira teste dicótico

1. **Duas rodadas** (`HeadphoneCheckScreen.kRounds`), cada uma com a orelha **sorteada**: o app
   gera um tom curto em **um só canal**, toca, e o participante responde "esquerda" ou "direita".
2. **Errar reinicia o teste** com novo sorteio — uma rodada certa não fica "guardada". Quem chuta
   acerta uma rodada em duas, mas o teste inteiro só em quatro.
3. **O sinal de teste é gerado no cliente** (`HeadphoneTestTone`, ~20 linhas de seno em memória),
   e não baixado: o teste acontece **antes** de existir sessão, o app é offline-first, e o sinal
   é idêntico nos dois braços — não carrega condição. A regra de reprodução bit-a-bit sem DSP
   continua valendo para o **estímulo**, que segue vindo pronto do servidor.
4. **`headphones_ok` sai do contrato**; entra `headphone_check` (**obrigatório**) com
   `version`, `rounds`, `errors`, `attempts` e `ears`. O servidor recusa (422) verificação com
   erro ou com menos de duas rodadas, e **deriva** `session.headphones_ok` do resultado.
5. **A evidência é gravada por sessão** (`session.headphone_check`, migração `a7b8c9d0e1f2`).
   `errors` descreve a tentativa **aceita** (sempre 0, por construção) e `attempts` diz quantas
   foram necessárias — é isso que a auditoria do estudo vai querer ver quando alguém precisar
   refazer o teste, e o protocolo lista "resultado da verificação de fones" entre os dados de
   registro de cada sessão.

### G3 — teto de volume imposto por software

6. **O app não oferece controle de volume.** Reproduz sempre com um ganho fixo (`audioGain`),
   aplicado pela porta de áudio (`AudioPlayerPort.setVolume`) antes de tocar — tanto no estímulo
   quanto no sinal de teste.
7. **O ganho é declarado ao iniciar a sessão** (`audio_gain`) e **recusado acima do teto do
   servidor** (`AUDIO_MAX_GAIN`, padrão 1.0). O participante não tem como ultrapassá-lo pelo
   aplicativo, e a exposição fica registrada na linha da sessão.
8. **O ganho vem do build** (`--dart-define=AUDIO_GAIN_MILLI=…`, em milésimos porque
   `double.fromEnvironment` não existe em Dart), não do código: quando a calibração em acoplador
   disser qual valor corresponde a 60 dB(A), troca-se o build.

## Alternativas consideradas

- **Manter a caixa de seleção e confiar no participante.** Rejeitada: é a "declaração, não
  verificação" que o próprio protocolo evita, e o custo de verificar é uma tela.
- **Baixar o sinal de teste do servidor.** Rejeitada: exigiria endpoint e sessão para algo que o
  cliente gera em memória, e quebraria o teste offline.
- **Uma rodada só.** Rejeitada: 50% de acerto por acaso não verifica nada.
- **Guardar a rodada certa quando a seguinte erra.** Rejeitada: transformaria o teste em
  "tente até acertar" — o acaso venceria por insistência.
- **Somar os erros de todas as tentativas em `errors`.** Rejeitada: o servidor recusaria a
  sessão de quem simplesmente corrigiu o fone invertido e refez o teste. Refazer é normal; o
  que precisa constar é **quantas** tentativas foram necessárias.
- **Controlar o volume do sistema operacional.** Rejeitada aqui: exige código nativo por
  plataforma e não existe na web. O que o app controla é o **próprio ganho**; o nível absoluto
  depende da calibração (abaixo).

## Consequências

- **Positivas:** a condição dicótica passa a ser verificada, não presumida; cada sessão carrega
  a evidência do teste e o nível com que foi reproduzida; o limite de volume existe e é do
  servidor, não do cliente.
- **Custo:** +1 migração; `SessionIn` mudou (o campo `headphones_ok` saiu) — como ainda não há
  participante em campo, a quebra é limpa; 20 chamadas nos testes passaram a usar um helper
  (`tests/helpers.py`) que deixa a regra explícita na leitura.
- **⚠️ O nível absoluto continua não calibrado.** `AUDIO_MAX_GAIN=1.0` (padrão) não restringe
  nada, e `audioGain=0.8` é um valor de partida, **não** 60 dB(A). O que fecha G3 de verdade é a
  medição em acoplador de orelha (etapa (i) do protocolo), com um par transdutor/aparelho
  definido; até lá o sistema tem o *mecanismo* do limite, não o *valor*.
- **A dose acumulada (G9) continua aberta:** o protocolo também promete contabilizar a exposição
  e avisar em 50% da referência OMS/UIT. O `audio_gain` por sessão é o insumo que faltava.
- **O que o cliente informa é o que o cliente informa.** Nem a verificação nem o ganho podem ser
  provados pelo servidor — o que ele faz é recusar evidência que já indique falha e registrar o
  resto. O ganho real de proteção está contra regressão de build e contra o participante que
  simplesmente não colocou os fones, não contra fraude deliberada.

## Conformidade

CI verde exige: `backend/tests/test_headphone_check_e_volume.py` (recusa de verificação
reprovada e de rodada única, registro da evidência, teto de ganho, regras idênticas nos dois
braços); `app/test/headphone_check_test.dart` (sem passar não há botão de iniciar, errar
reinicia, o envio descreve a tentativa aceita, o sinal sai em uma orelha só); assertiva de ganho
travado em `app/test/session_player_test.dart`; migração `a7b8c9d0e1f2`; OpenAPI válido.
