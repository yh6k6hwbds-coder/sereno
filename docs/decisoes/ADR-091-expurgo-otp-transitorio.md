# ADR-091 — Expurgo agendado dos desafios de OTP (primeiro pedaço do E2)

- **Status:** Aceito
- **Data:** 2026-07-22
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/LGPD)
- **Contexto de origem:** item **E2** do `docs/lgpd-nit-checklist.md` ("expurgo agendado ao fim do
  prazo") e o risco **R-10** do `docs/relatorio-impacto-protecao-dados.md` (retenção sem controle
  efetivo — residual **Alto**).
- **Relaciona-se com:** `politica-retencao-descarte.md` §4/§6, ADR-063 (OTP), ADR-066 (eliminação a
  pedido), ADR-056/086 (auditoria append-only).

## Contexto

O item E2 estava inteiramente pendente e o RIPD o classificou sem rodeios: enquanto não houver
expurgo automático, **a política de retenção é uma intenção, não um controle**. Mas E2 é um item
composto, e suas partes têm bloqueios diferentes:

- o expurgo do **dataset de pesquisa** depende dos **prazos** do item E1, que são decisão do
  CEP/assessoria (`[a confirmar]` na política) — sem prazo aprovado, não há o que agendar;
- o expurgo dos **transitórios de autenticação** (`otp_challenge`) **não depende de ninguém**: o TTL
  de 5 minutos é parâmetro técnico de autenticação (ADR-063), não prazo de pesquisa. A política já
  fixa a regra ("expurgar expirados/consumidos; proposta diário, nunca > 24 h") e ela não é objeto
  de aprovação ética.

Fazia sentido, portanto, construir a parte que não está bloqueada em vez de esperar o pacote inteiro.

## Decisão

1. **`modules/retention/service.py` · `purge_expired_otp(db, grace_min)`** apaga de `otp_challenge`
   o que **já expirou** há mais de `grace_min` minutos (padrão **60**) e devolve a contagem. Módulo
   próprio (`retention`) porque será a casa dos demais expurgos quando o E1 sair — não um utilitário
   solto dentro de `participant_auth`.
2. **Só se apaga o que já expirou — invariante de segurança da fatia.** Um desafio ainda válido
   carrega o contador `attempts`, que é a defesa contra força bruta de um código de 6 dígitos.
   Apagá-lo cedo **zeraria** o contador e devolveria ao atacante um novo lote de tentativas: o
   expurgo viraria um **oráculo de reset**. O critério é sempre absoluto (`expires_at < now - graça`),
   nunca "os N mais antigos" — que seria sensível a volume e poderia alcançar linha viva.
3. **Carência (`grace_min`, padrão 60)** — não é prazo de retenção, é folga para não competir com uma
   requisição em voo que ainda esteja lendo o desafio recém-expirado. Com o job **diário** da
   política, o tempo de vida máximo de um registro fica em ~24 h, dentro do "nunca > 24 h".
4. **Auditado, mas só a contagem.** `otp.purged` com `actor_type="system"`, `meta={deleted, grace_min}`
   — sem participante, sem `resource_id`, sem hash de código. É o que dá **evidência de que o controle
   rodou** (o que o R-10 cobra) sem criar um novo registro sobre quem entrou e quando: seria irônico
   um controle de minimização virar fonte de rastro de acesso. **Não audita quando não há nada a
   apagar** — um job diário silencioso não deve poluir uma trilha append-only retida por 5 anos.
5. **Entrada agendável: `backend/scripts/purge_otp.py`**, com `--dry-run` e `--grace-min`, saída em
   JSON e **código de saída ≠ 0 em falha** (para o agendador conseguir alertar). Idempotente e seguro
   para rodar com frequência.
6. **Nenhuma mudança de contrato nem de schema:** sem endpoint (não se cria superfície pública para
   uma rotina interna) e sem migração.

## Alternativas consideradas

- **Expurgo oportunista dentro de `POST /request-otp`.** Rejeitada: colocaria um `DELETE` no caminho
  público e, pior, amarraria a limpeza ao tráfego — se ninguém logasse, nada seria expurgado,
  exatamente na situação em que dado velho fica parado por mais tempo.
- **Thread periódica dentro da app** (como o pool de e-mail do ADR-085). Rejeitada **por ora**:
  acrescenta ciclo de vida em processo (e execução duplicada por réplica) para um ganho que um
  agendador externo entrega sem código. Se o piloto rodar sem agendador disponível, é a alternativa
  natural — e a lógica já está isolada no serviço, então seria só chamá-la de outro lugar.
- **Endpoint admin `POST /v1/retention/purge`.** Rejeitada: superfície pública nova, com RBAC e
  rate limit a manter, para algo que ninguém precisa disparar pela rede.
- **Apagar por idade de criação (`created_at`).** Rejeitada: `expires_at` é o campo que define a
  validade; usar outro relógio abriria a chance de alcançar um desafio ainda vivo (ver decisão 2).

## Consequências

**Positivas:** o primeiro expurgo da política existe, é testado e é idempotente; o risco R-10 deixa
de ser "nenhum controle automático" e passa a "controle parcial"; o módulo `retention` fica pronto
para receber os demais expurgos quando o E1 for aprovado. **+10 testes** (suíte 297→307).

**Negativas / a vigiar:**
- **"Agendado" ainda depende de ops.** O *mecanismo* está pronto e testado; **quem** o chama
  periodicamente (cron do host, máquina agendada da Fly) é passo operacional, hoje não configurado —
  o deploy sequer está no ar. **Enquanto ninguém agendar, o expurgo não acontece**, e seria desonesto
  marcar E2 como concluído. Ver `docs/deploy-fly.md`.
- **E2 segue aberto para o dado de pesquisa**, que é a parte pesada e depende do E1. **R-10 permanece
  residual Alto** no RIPD por isso.
- A auditoria ganha ~1 linha/dia quando houver expurgo (365/ano) — desprezível, mas é acúmulo em
  tabela append-only retida por 5 anos.

## Verificação

`tests/test_retention_otp.py` (10): apaga expirado além da carência e respeita a carência;
**nunca apaga desafio válido** (nem com carência 0) e preserva `attempts`; idempotente; apaga
consumido já expirado; audita só a contagem, sem PII/participante; **não audita quando vazio**; não
toca em `participant`; o login segue funcionando após o expurgo; e **código expirado devolve a mesma
resposta** antes e depois do expurgo (401 idêntico) — senão o expurgo viraria oráculo de existência.
Script exercitado ponta a ponta em SQLite (dry-run, execução real, idempotência, `--grace-min 0`).
