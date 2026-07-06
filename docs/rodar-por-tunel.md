# Rodar o app por túnel (sem cartão, dados no Brasil)

Forma **sem provedor de nuvem e sem cartão** de deixar o app acessível num celular:
o backend roda no seu PC (Docker) e um túnel Cloudflare dá uma URL HTTPS pública.
Os dados ficam no seu PC (Brasil). Funciona **enquanto o PC estiver ligado** com o
Docker e o túnel no ar.

```
Celular (qualquer rede)
  → https://<algo>.trycloudflare.com   (túnel Cloudflare)
  → seu PC: Docker localhost:8000       (backend + Postgres)
App web publicado no GitHub Pages: https://yh6k6hwbds-coder.github.io/sereno/
```

## Subir tudo

```bash
# 1) Backend + banco (na pasta sereno/)
docker compose up -d --build
docker compose exec -T backend python scripts/seed_demo.py   # cria o cenário DEMO

# 2a) Túnel — jeito fácil (Windows): sobe o túnel E imprime/copia o link pronto
#     do app (com ?api=). Deixe a janela aberta; Ctrl+C encerra.
#     powershell -ExecutionPolicy Bypass -File scripts\tunel.ps1
# 2b) Manual (baixe cloudflared uma vez: github.com/cloudflare/cloudflared/releases)
cloudflared tunnel --url http://localhost:8000
#   → anote a URL https://<algo>.trycloudflare.com que aparece no log
```

> **CORS:** o backend só aceita a origem do app. Em dev isso já vem liberado por
> `CORS_ALLOW_ORIGIN_REGEX` no `.env` (localhost + o domínio do GitHub Pages).

## Apontar o app para o túnel — SEM recompilar

A URL do `trycloudflare.com` **muda toda vez que o túnel reinicia**. Para não ter
que reconstruir o app a cada mudança, o cliente aceita um override por parâmetro de
URL (só na web, só `https`):

```
https://yh6k6hwbds-coder.github.io/sereno/?api=https://<algo>.trycloudflare.com/v1
```

Abra/salve esse link no celular. Quando o túnel mudar, é só trocar a parte do `?api=`
— **nenhum rebuild, nenhum CI**. Sem o parâmetro, o app usa a URL fixada no último
build (`--dart-define=API_BASE_URL`, definida pela variável `API_BASE_URL` do repo).

## Login (DEMO)

Código de estudo **DEMO**. Como ainda não há SMTP, o OTP sai no log do backend:

```bash
docker compose logs backend --since 2m | grep "código de uso único"
```

## Limitações e caminho durável

- Só no ar com o **PC ligado** + Docker + túnel. Se dormir, o app para.
- URL do túnel é **efêmera**. Para uma URL fixa (sem trocar o `?api=`), use um
  **túnel nomeado** do Cloudflare (conta grátis + um domínio) apontando para
  `localhost:8000`, ou faça o deploy gerenciado (ver `docs/deploy-fly.md`, exige
  cartão) para não depender do seu PC.
- Antes de participantes reais: SMTP para o OTP + aval LGPD (ver ADR-076).
