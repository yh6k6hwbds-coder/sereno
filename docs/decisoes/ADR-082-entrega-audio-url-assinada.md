# ADR-082 — Entrega de áudio por URL assinada (porta de storage, sem vazar braço)

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 2 (áudio/instrumento), Fase E (E3 — cloud storage para áudio)
- **Contexto de origem:** ROADMAP E3 — "migrar a materialização/entrega de áudio (A1) para
  armazenamento em nuvem (URLs assinadas, sem vazar condição)".
- **Relaciona-se com:** A1 (materialização/entrega local em disco), inegociável #2 (alocação
  oculta / cegamento), inegociável #3 (áudio bit-a-bit), ADR-080 (métricas por template de rota)

## Contexto
A entrega A1 transmite o WAV **inline** pelo caminho autenticado (`GET /v1/sessions/{id}/audio`),
lendo de um cache em disco local. Isso funciona para o piloto, mas amarra a transferência de
arquivos grandes ao processo da API e não prepara o offload para storage/CDN — a intenção da
E3. O escopo do MVP é **preparar, não construir** (CLAUDE.md): não faz sentido plugar um bucket
S3 real (conta + credenciais + residência) agora. O que falta é o **seam**: uma forma de entregar
o áudio por **URL assinada de curta duração**, na qual um presign de nuvem depois encaixa sem
mexer no cliente nem no router.

## Decisão
1. **Porta de entrega `AudioStorage`** (`modules/sessions/storage.py`), escolhida por
   `AUDIO_DELIVERY`:
   - `inline` (**padrão**): comportamento A1 **inalterado** — o backend transmite os bytes.
   - `signed-url`: `GET /sessions/{id}/audio` responde **302** para uma URL assinada; a
     transferência sai do caminho autenticado.
2. **A chave do objeto é o `content_hash` OPACO** — nunca a condição. É o mesmo hash já
   devolvido ao cliente no start da sessão, então a URL não revela nada novo (inegociável #2).
3. **URL auto-assinada, sem dependência de nuvem** (preparação testável): `GET /v1/audio/{hash}`
   é **público-mas-assinado** — a capability é a assinatura, não há `Authorization` (exatamente
   como um signed URL de nuvem). Assinatura = **HMAC-SHA256** sobre `content_hash|exp` com
   subchave dedicada (derivada de `AUDIO_URL_SIGNING_KEY`, ou do `JWT_SECRET` na falta — nunca a
   chave do JWT em claro). Verificação em **tempo constante**; TTL curto (`AUDIO_URL_TTL_S`, 300 s).
4. **Mesma resposta bit-a-bit** (inegociável #3): o endpoint assinado reusa o mesmo materializador
   e o mesmo helper de streaming do caminho autenticado — `ETag = sha256(corpo)`, `Accept-Ranges`,
   Range (206/416), headers **neutros** e idênticos entre braços.
5. **Erros sem oráculo:** assinatura inválida/ausente/expirada → **403 genérico** (não distingue o
   motivo); hash bem-assinado mas ausente da biblioteca → 404. O `Location` do 302 carrega só
   `content_hash`+`exp`+`sig` (tudo opaco/neutro).
6. **Métricas (ADR-080) preservadas:** a rota entra como template `/audio/{content_hash}` (baixa
   cardinalidade), nunca o hash concreto.

## Alternativas consideradas
- **Plugar S3/boto3 agora.** Rejeitada: exige bucket/credenciais/residência e é "construir", não
  "preparar" (fora do MVP). A porta `AudioStorage` deixa o presign de S3 como troca local a
  `build_signed_path` depois.
- **Devolver a URL em JSON** em vez de 302. Rejeitada: mudaria o contrato do cliente; o 302 é
  transparente (o player segue o redirect) e espelha o comportamento de um CDN/S3.
- **Endpoint assinado autenticado (com JWT).** Rejeitada: contraria a natureza de signed URL
  (capability desacoplada da sessão) e reintroduz o acoplamento que a E3 quer remover. Não há
  regressão de privacidade: a URL só é gerada após o check de IDOR no endpoint da sessão, e os
  bytes-por-hash não revelam identidade nem braço (arquivos idênticos dentro do mesmo braço).
- **Assinar com a própria chave do JWT.** Rejeitada: reúso de chave entre contextos; derivamos uma
  subchave dedicada.

## Consequências
- **Positivas:** seam de entrega por URL assinada pronto e **testável sem nuvem**; A1 inalterado
  por padrão (zero risco para o piloto); cegamento e fidelidade preservados. Suíte 224 → 234 (+10).
- **Custo/tradeoff:** enquanto `AUDIO_DELIVERY=signed-url`, o WAV ainda é **servido pelo próprio
  backend** (o endpoint assinado lê o cache local) — o ganho real de offload só vem quando um
  adaptador de nuvem implementar a porta. É a "preparação" pedida pela E3, não a migração completa.
- **Pendências:** adaptador de storage em nuvem real (presign S3/GCS + upload do cache) — a
  "construção" da E3, quando o piloto/infra pedir; rate limit no endpoint público (hoje o guard é
  assinatura + TTL curto); rotação da chave de assinatura.

## Conformidade
CI verde exige `tests/test_audio_signed_url.py`: com `signed-url`, o endpoint da sessão dá **302**
para `/audio/{hash}` (chave = content_hash opaco, Location neutro); a URL entrega o **mesmo WAV
bit-a-bit** (ETag == sha256) e suporta Range; braços opostos têm a **mesma forma** de resposta sem
termo de condição; assinatura adulterada/ausente/expirada → **403**; hash desconhecido → 404; modo
**inline é o padrão** (sem 302). `test_session_audio.py` (A1) segue **verde sem mudança**. Sem
segredo versionado; sem PII/braço; inegociáveis #2 e #3 preservados.
