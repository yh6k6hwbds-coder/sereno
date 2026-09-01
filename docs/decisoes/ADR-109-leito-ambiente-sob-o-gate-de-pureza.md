# ADR-109 — Leito ambiente: o que o protocolo promete, sem afrouxar o gate de pureza

- **Status:** Aceito — com **um número a ratificar** (o nível do leito; ver "Pendências")
- **Data:** 2026-09-01
- **Decisores:** Arquiteto (Claude), a partir do protocolo aprovado
- **Etapas relacionadas:** 2 (player/instrumento), 5 (backend)
- **Contexto de origem:** item **G2** do `docs/ROADMAP.md` — o último item de código da Fase G,
  registrado até aqui como "exige decisão do mantenedor".
- **Relaciona-se com:** ADR-100 (estímulo do protocolo aprovado e o gate por FFT),
  ADR-103 (entrega em FLAC, materialização em janelas), ADR-101 (teto de volume e calibração).

## Contexto

O protocolo, em **"Parâmetros comuns aos dois braços"**, promete:

> "(...) trilha de fundo ambiental de **baixa intensidade**, **idêntica em conteúdo, duração e
> nível**, sobre a qual os tons são superpostos"

e, no mesmo parágrafo, **recusa** o mascaramento por ruído rosa, com base metanalítica.

Nada disso existia no software: o estímulo era só o par de senoides. E o roadmap registrava G2
como um impasse — o gate por FFT exige **pureza espectral ≤ −60 dB**, e um leito somado ao sinal
reprovaria a bateria. O item estava escrito como escolha binária: **ou o leito sai do protocolo,
ou o gate ganha uma exceção** nomeada e justificada no dossiê.

O impasse era falso, e a razão está na palavra "espúria". O piso de −60 dB mede **energia que
ninguém pediu** — distorção da síntese, harmônicos, sujeira numérica. O leito ambiente é o
oposto disso: é **conteúdo prescrito**. Medi-lo como impureza reprovaria o arquivo por conter
exatamente aquilo que o protocolo manda que ele contenha.

## Decisão

**O gate não ganha exceção: ganha um alvo mais preciso e quatro itens novos.**

**(1) A pureza espectral passa a ser medida no estímulo ISOLADO.** `synthesize_segment` ganhou
`with_bed=False`, que devolve só os tons — e é essa janela que vai à FFT de pureza. O piso de
−60 dB continua valendo sobre exatamente o que ele sempre mediu; não foi afrouxado em nada. O
que **chega à orelha** (tons + leito) continua alimentando o teto de pico e a equalização de
energia entre braços, porque esses dois itens são sobre o arquivo entregue.

**(2) Quatro itens NOVOS provam o que o leito tem de ser** — e são mais exigentes que o item que
não se aplicava:

| item | o que prova | de onde vem |
|---|---|---|
| leito diótico (L == R) | a mesma coluna nos dois canais, sem diferença interaural | um leito com Δf seria um batimento que ninguém prescreveu |
| nível do leito | está no nível declarado | "de baixa intensidade" |
| leito fora da banda do estímulo | ≤ −60 dB de energia em [230, 273] Hz | é o que torna **verificável** a recusa ao mascaramento |
| leito idêntico entre braços | ativo e sham recebem o leito **bit a bit** igual | "idêntica em conteúdo, duração e nível" |

O terceiro é o que transforma a frase do protocolo em afirmação testável: o leito não põe energia
onde o estímulo está — medido, hoje, em −179 dB.

**(3) Quatro decisões de engenharia sustentam a frase do protocolo:**

- **É tonal, não ruído.** Quatro parciais entre 55 e 137,5 Hz, muito abaixo da banda do estímulo
  (250/253 Hz). Um leito de banda larga seria mascaramento por outro nome — o que o protocolo
  recusa.
- **É diótico.** Sem diferença interaural, "idêntico nos dois braços" passa a ser verdade **por
  construção**, não por cuidado de quem renderiza. O leito não vê `beat_hz`.
- **É fórmula fechada, sem gerador aleatório.** O servidor materializa 20 min em janelas de 10 s
  (ADR-103); um leito por ruído filtrado exigiria a FFT do sinal inteiro — 920 MB em float64.
  Sendo função de `t`, o leito sai bit a bit igual em janelas ou de uma vez só.
- **Não se paga com clipping.** A amplitude dos tons cede exatamente a folga que o **pico** do
  leito ocupa (cota superior em forma fechada). O teto digital é do arquivo **entregue** — é
  contra ele que a calibração em acoplador (F2.7) é feita, e ele não pode escorregar.

**(4) A recuperação do leito nos testes é por subtração** (`mistura − tons`), não por comparar o
leito sintetizado consigo mesmo. Comparar a fórmula com ela mesma seria tautologia; a subtração
pega um leito que passasse a depender do braço lá na frente. É também por isso que `with_bed=False`
existe além de `bed_level_dbr=None`: o primeiro mantém a amplitude reduzida (a subtração devolve o
leito limpo), o segundo devolve os tons no teto cheio — que é o caminho "protocolo sem leito".

**(5) Leito é coluna de protocolo, não constante de código.** `audio_protocol.bed_level_dbr`,
anulável (os protocolos curtos de demo não têm leito, e a ausência é informação: um zero diria
"leito no mesmo nível do estímulo") e com `CHECK < 0` — um leito **acima** do estímulo deixaria de
ser "de baixa intensidade" e viraria mascaramento. Mudar o leito de um protocolo já auditado é
**versão nova** (`content_hash` novo), nunca `UPDATE`: o hash que um cliente já viu não pode
passar a apontar para outro áudio. A biblioteca do estudo foi para **v1.1.0**.

**(6) `resolve_protocol` passou a desempatar pela versão mais nova** (`created_at` decrescente).
Uma base semeada antes desta mudança guarda as duas versões da mesma banda e condição; sem
critério, quem escolhia era a ordem que o banco devolvesse, e parte dos participantes ouviria o
estímulo **sem leito** — sem que nada acusasse. O desempate é por `created_at`, e não pela string
da versão, que poria "1.10.0" antes de "1.9.0". E o `--check` do seeder passou a **listar** as
versões antigas que sobraram: apagar continua sendo decisão humana, porque uma linha antiga pode
ter sessões apontando para ela.

## Consequências

- O piloto passa a tocar o que o protocolo descreve. Antes desta ADR, o arquivo entregue
  **contradizia** o projeto submetido ao CEP em um parágrafo dos "parâmetros comuns aos dois
  braços".
- O gate ficou **mais** exigente, não menos: quatro itens onde havia zero, e o piso de pureza
  intacto sobre o mesmo alvo de sempre.
- O pico do arquivo cai de −12,00 para −12,15 dBFS: os tons cedem a folga do leito. É a cota
  **superior** do pico (todas as parciais e LFOs em fase), então é conservadora por construção.
- Quem já rodou `seed_protocols.py` precisa rodar de novo (v1.1.0 é linha nova) e conferir o
  `--check`. Sem `--materialize`, a primeira requisição de áudio pós-deploy paga a síntese.
- **`--materialize` passou a funcionar**: a flag era documentada no cabeçalho desde o ADR-103 e
  nunca chegava a `main` — `_materialize()` jamais era chamado.
- A duplicação da fórmula entre `audio-pipeline/` (fonte de verdade científica, validada por FFT
  no CI) e `backend/` (materializador do servidor) cresceu junto com o leito. Continua amarrada
  por teste que compara as duas sínteses **amostra a amostra**.

## Pendências

**O NÍVEL do leito (−30 dBr) é escolha desta implementação, não número do protocolo**, que diz
apenas "baixa intensidade". −30 dB abaixo do estímulo é audível como presença e fica muito longe
de mascarar. Mas é **um parâmetro do que o participante ouve**: precisa de ratificação do
mantenedor e de declaração ao CEP, como a janela de 7 dias do T2 (ADR-106). Está nomeado em um
lugar só de cada lado (`BED_LEVEL_DBR`), e há teste que amarra os dois.

O **timbre** (parciais, ganhos, LFOs) tem a mesma natureza: soa como um bordão grave e estável, e
mudá-lo é emenda de protocolo, não ajuste de código.

## Alternativas consideradas

**Tirar o leito do protocolo.** Era metade do impasse original. Rejeitada: seria emenda de
protocolo para resolver um problema de engenharia que não existia — o gate media o alvo errado,
não o leito.

**Dar ao gate uma exceção nomeada.** A outra metade. Rejeitada: uma exceção valeria para qualquer
energia espúria na banda, inclusive a que o piso existe para pegar. O que se fez foi o contrário —
apontar a medida para o estímulo isolado e **acrescentar** itens.

**Ruído rosa filtrado, em nível baixo.** Rejeitada duas vezes: o protocolo recusa mascaramento por
ruído rosa explicitamente e com base metanalítica; e ruído filtrado exigiria a FFT do sinal
inteiro, incompatível com a materialização em janelas (ADR-103).

**Leito com semente aleatória por protocolo.** Rejeitada: qualquer semente derivada do braço — ou
que alguém viesse a derivar — viraria pista de cegamento; e o leito deixaria de ser reproduzível
em janelas. A fórmula fechada dá as duas garantias de graça.
