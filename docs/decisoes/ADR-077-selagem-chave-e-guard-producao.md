# ADR-077 — Selagem real da chave A/B→condição + guard de config de produção

- Status: Aceito
- Data: 2026-07-09
- Contexto: revisão de segredos/deploy pré-piloto. O ADR-076 já sinalizava duas
  pendências que este ADR resolve. Ambas estavam **vivas** (no `.env` local do caminho
  por túnel e commitadas no `fly.toml`/`.env.example`).

## Problema

1. **A "chave selada" não estava selada (inegociável #2).** O mapa
   `ARM_CONDITION_MAP=A:active,B:sham` — que traduz o braço **codificado A/B** (exportado
   no dataset de pesquisa) em **condição** (ativo/sham) — estava versionado no `fly.toml`
   (`[env]`, nem secret), no `.env.example`, **e** como default hardcoded em
   `sessions/service.py`. Qualquer pessoa com acesso ao repositório decifrava a condição
   de todo participante a partir do braço exportado. O cegamento virava teatro: mesmo
   movendo o mapa para um secret, o default público no código continuaria revelando a
   atribuição.
2. **OTP em log de produção (inegociável #6).** `EMAIL_DEV_CONSOLE=1` no `fly.toml [env]`
   fazia o `ConsoleEmailSender` imprimir o código OTP em texto claro em `fly logs`.

## Decisão

### Selar de verdade + guard de startup (fail-fast)

- Novo `app/core/config.py`: `APP_ENV` distingue dev/produção; `validate_runtime_config()`
  é chamada em `create_app()` e **recusa subir em produção** se:
  - `ARM_CONDITION_MAP` não estiver configurado (a chave selada não pode cair no default
    público), ou
  - `EMAIL_DEV_CONSOLE` estiver ligado (OTP iria para o log).
- **Defesa em profundidade:** `sessions.service._sealed_map()` também recusa o default
  público quando `is_production()` e o mapa está ausente — mesmo que o guard de startup
  seja contornado, nenhuma resolução de condição usa a atribuição conhecida.
- O default `A:active,B:sham` passa a valer **só em dev/teste** (conveniência da suíte, que
  depende dele). Em produção, o valor real é um **sorteio custodiado** (`A:sham,B:active`
  **ou** `A:active,B:sham`), decidido e anotado **offline** pelo custodiante (tipicamente a
  orientadora), setado apenas como secret e aberto no *data lock*.
- Config limpa: `ARM_CONDITION_MAP` e `EMAIL_DEV_CONSOLE` **removidos** do `fly.toml` e do
  `.env.example`; `fly.toml` passa a ligar `APP_ENV=production`. Runbook (`deploy-fly.md`)
  atualizado: a chave selada é secret obrigatório; o OTP-no-console vira atividade **local/dev**.

### SMTP real robusto (destrava o OTP em produção)

- `SmtpEmailSender` passa a suportar **SSL implícito/SMTPS (porta 465)** além de
  **STARTTLS (587)**. `_build_from_env` autodetecta 465 (ou `SMTP_USE_SSL=1`) e não faz
  STARTTLS por cima de uma conexão já cifrada. Sem isso, um provedor em 465 falharia
  silenciosamente (o disparo do OTP é best-effort) e travaria o login do participante.
- Recomendação de provedor grátis p/ N≈40: Gmail com *app password* (587/STARTTLS) — já
  suportado; ou Brevo. Credenciais entram como secrets, nunca versionadas.

## Consequências

- **Positivas:** o cegamento deixa de depender do sigilo do repositório; violações de
  config em produção falham no boot em vez de silenciosamente; o OTP real funciona nos
  dois modos de TLS comuns.
- **Custo:** o smoke-test rápido com OTP-no-log não vale mais na Fly de produção — passa a
  ser feito local/por túnel (dev) ou exige SMTP configurado. Aceito: é o preço de não
  logar segredo em produção.
- **Não muda a API** (`openapi.yaml` intacto): endurecimento interno de config/infra.

## Pendências (fora deste ADR)

- Cofre/KMS de verdade para os secrets (hoje `fly secrets`, aceitável no piloto).
- Fila assíncrona de e-mail (RQ/Redis) e tratamento de bounces (ADR-031).
- Rotação de segredos e backups/retenção do Postgres.
