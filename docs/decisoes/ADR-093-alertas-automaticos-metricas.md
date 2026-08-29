# ADR-093 — Alertas automáticos sobre sintomas operacionais (detecção de R-03/R-06)

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança) e LGPD
- **Contexto de origem:** item **F4.6** do `docs/ROADMAP.md`, autorizado pelo mantenedor; e a
  recomendação **7** do `docs/relatorio-impacto-protecao-dados.md` ("alertas automáticos — fecha
  detecção de R-03/R-06").
- **Relaciona-se com:** ADR-080 (métricas), ADR-085/092 (entrega de e-mail), ADR-067 (log JSON),
  ADR-056/086 (auditoria append-only), `plano-resposta-incidentes.md`.

## Contexto

O sistema já **registrava** o suficiente: log JSON por requisição (ADR-067), `emails_total` por
desfecho (ADR-085/092), auditoria append-only (ADR-086). O que faltava era alguém **olhar**. No
piloto não há Prometheus na frente do `/metrics`, não há plantão e a equipe é pequena — então, na
prática, todo controle de detecção dependia de uma pessoa abrir o log por conta própria.

Isso deixa dois riscos do RIPD com detecção vazia:

- **R-06 (evento adverso não percebido a tempo).** O aviso de EA moderado/grave sai **por e-mail**.
  Se a entrega falha, ninguém percebe: o participante relatou, o sistema registrou, a equipe não
  soube. O contador existia; o aviso sobre o contador, não.
- **R-03 (acesso indevido por insider).** RBAC, MFA e auditoria **previnem e registram**, mas
  ninguém é avisado quando alguém lê muito mais dado de pesquisa que o normal. A trilha só ajuda
  quem já foi olhar.

## Decisão

1. **`core/alerts.py`: detector em processo, sem infraestrutura nova.** `record(regra)` conta o
   sintoma numa **janela fixa**; ao cruzar o limiar, dispara. Sem Prometheus, sem Alertmanager, sem
   mais um serviço no ROPA — o piloto não sustentaria essa cauda operacional.
2. **Quatro regras**, com limiares calibrados para o tráfego baixo do piloto e todos ajustáveis por
   ambiente (`ALERT_<REGRA>_{THRESHOLD,WINDOW_S,COOLDOWN_S}`):
   | Regra | Sintoma | Padrão | Fecha |
   |---|---|---|---|
   | `email_failure` | entrega de e-mail falhou/bounce | 3 em 15 min | **R-06** |
   | `auth_failure` | rajada de 401 | 25 em 5 min | força bruta |
   | `server_error` | 5xx em série | 10 em 5 min | disponibilidade |
   | `research_access` | volume de leitura em `/research`/`/audit` | 200 em 1 h | **R-03** |
3. **O canal é o e-mail da equipe (`TEAM_NOTIFY_EMAIL`) + log estruturado + métrica
   `alerts_total{rule}`.** Sem destino configurado, o log é o canal — o detector nunca deixa de
   contar por falta de e-mail.
4. **O alerta não identifica ninguém.** Corpo = regra, contagem, janela, cooldown e **o que fazer**.
   Nada de participante, ator, endereço, código ou braço. No caso do `research_access`, o aviso diz
   explicitamente para procurar **quem** na auditoria: é lá que essa pergunta se responde, com
   controle de acesso próprio. Um alerta que já dissesse o nome espalharia dado de acesso por
   e-mail, fora de qualquer trilha.
5. **Cooldown por regra** (30 min a 2 h): dispara uma vez e cala, mesmo com o sintoma continuando.
   Alerta repetido é alerta ignorado — e, no caso do e-mail, seria também amplificação de falha.
6. **Quebra explícita do laço de realimentação.** `EmailMessage.alert=True` marca o e-mail de
   alerta; falha ao entregá-lo **não** alimenta `email_failure`. Sem isso, SMTP fora geraria
   alerta → que falha → que gera alerta, até o cooldown (ou até estourar a fila).
7. **Best-effort absoluto.** `record()` engole qualquer exceção e o disparo acontece **depois** de
   soltar o lock. Nenhuma requisição pode falhar, atrasar ou vazar exceção por causa de um aviso.
8. **Alimentado pela mesma informação de baixa cardinalidade da métrica** (template de rota +
   status), no middleware que já existia. Nada de caminho concreto, corpo ou identidade.
9. **Sem contrato novo, sem schema novo, sem endpoint novo.**

## Alternativas consideradas

- **Prometheus + Alertmanager** (o caminho canônico). Rejeitada **para o piloto**: exige serviço
  novo no ar, retenção de série temporal e mais um operador — para uma instância única e uma equipe
  de duas pessoas. O `/metrics` continua exposto: quando houver Prometheus, estas regras viram
  `alerting_rules` e o módulo pode sair.
- **Alertar com identificação do ator no corpo** (quem exportou, qual participante). Rejeitada: põe
  dado de acesso e possivelmente PII num canal sem controle, fora da auditoria — trocaria detecção
  por um vazamento novo.
- **Contadores no Redis** (visão agregada entre réplicas). Rejeitada por ora: o `fly.toml` roda **1
  instância**, então a contagem em memória é exata hoje. A troca é local a `record()`.
- **Alerta por webhook (Slack/Telegram).** Rejeitada: mais um terceiro no ROPA/DPA para um destino
  que a equipe não usa; o e-mail da equipe já existe e já é o canal do evento adverso.
- **Persistir alertas numa tabela.** Rejeitada: criaria um novo repositório de dados operacionais
  para consultar — a métrica e o log já dão a evidência de que o controle rodou.

## Consequências

**Positivas:** R-03 e R-06 ganham **detecção**, não só prevenção e registro; a falha de e-mail deixa
de ser silenciosa mesmo sem ninguém olhando o `/metrics`; o plano de resposta a incidentes passa a
ter um gatilho automático em vez de depender de percepção humana. **+11 testes** (suíte 317→328).

**Negativas / a vigiar:**
- **Contagem por processo.** Com réplicas, cada uma alerta pela sua fatia e os limiares ficam
  efetivamente multiplicados. Rever ao passar de 1 instância (é o mesmo alerta do `/ready` no F3.6).
- **Limiares são chute inicial.** Foram calibrados no escuro (o piloto ainda não coletou tráfego
  real). `research_access` em particular pode disparar num dia legítimo de análise — por isso o
  texto do aviso já diz que pode ser trabalho normal. Ajustar por ambiente nas primeiras semanas,
  sem mexer em código.
- **Alerta ainda depende de e-mail funcionando** para chegar longe do servidor. Quando o próprio
  e-mail é o problema, resta o log — declarado, não escondido.
- Um `TEAM_NOTIFY_EMAIL` mal configurado transforma alerta em bounce; o `email_failure` cobre isso,
  mas o primeiro aviso pode se perder.

## Verificação

`tests/test_alerts.py` (11): dispara no limiar e não antes; cooldown corta a tempestade (20
sintomas → 1 aviso); janela fixa não soma ocorrência velha; falha de e-mail alimenta o detector;
**o alerta que falha não se realimenta** (exatamente 1 disparo); o corpo não traz endereço, código
nem domínio do participante; sem destino, conta e não envia; `ALERTS_ENABLED=0` desliga e regra
desconhecida é no-op; `record` engole exceção do disparo; o middleware mapeia 5xx→`server_error`,
401→`auth_failure`, leitura de `/research` e `/audit`→`research_access` e ignora 404/health; e um
401 real pela API alimenta o detector ponta a ponta.
