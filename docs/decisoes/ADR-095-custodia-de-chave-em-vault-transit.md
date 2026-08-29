# ADR-095 — Custódia da chave de PII em Vault Transit (adaptador KMS real)

- **Status:** Aceito
- **Data:** 2026-08-29
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança) e LGPD
- **Contexto de origem:** item **F4.1** do `docs/ROADMAP.md` ("adaptador KMS/Vault real"), item
  **C11** do checklist e do RIPD §8 ("custódia de chave ainda em env/secret"), autorizado pelo
  mantenedor.
- **Relaciona-se com:** ADR-059 (cifra de PII), ADR-087 (porta `KeyProvider` + rotação por id),
  ADR-088 (envelope: DEK por registro), ADR-076 (deploy na Fly).

## Contexto

O ADR-087 criou a porta `KeyProvider` e o ADR-088 o envelope (DEK por registro embrulhada pela
KEK) — os dois desenhados para que a custódia pudesse evoluir **sem tocar em `pii_crypto`**. Faltava
o adaptador. Enquanto ele não existisse, a KEK ficava em variável de ambiente/secret: quem tivesse
acesso ao processo, ao painel de secrets ou a um dump de memória tinha a chave que abre toda a PII
do estudo. É o que o RIPD registra como C11 e o que fez a conclusão técnica ressalvar a custódia.

Escolher o provedor era a parte não óbvia. O deploy previsto é a **Fly.io**, que **não tem KMS** —
oferece secrets, que é a mesma custódia de hoje com outro nome. AWS/GCP KMS resolveriam, mas
acrescentam **mais um operador estrangeiro** ao ROPA e ao DPA (F1.4), decisão que não é técnica.

## Decisão

1. **Adaptador `VaultTransitKeyProvider`** (`core/keyring.py`), contra o **motor Transit do
   HashiCorp Vault**, ativado por `KEY_PROVIDER=vault`. `wrap`/`unwrap` viram chamadas ao cofre: a
   aplicação manda a DEK e recebe o blob, **a KEK nunca sai do Vault**.
2. **Vault, e não KMS de nuvem**, porque: é **auto-hospedável** (pode ficar na mesma residência de
   dados brasileira, inegociável #6), é **OSS** (sem contrato novo para o piloto), e o Transit tem
   exatamente a semântica `wrap`/`unwrap` que a porta já pedia. Se a instituição preferir um KMS de
   nuvem depois, é outro adaptador na mesma porta — o `pii_crypto` não muda.
3. **O AAD vira `context` de *derived key*.** O Transit não tem AAD; tem contexto de derivação. Com
   a chave criada com **`derived=true`**, decifrar com outro contexto falha — que é a garantia que
   o AAD dá aqui (o valor fica preso ao participante **e** ao campo). Provisionamento obrigatório:
   `vault write -f transit/keys/sereno-pii-kek derived=true`. **Sem `derived=true` essa amarração se
   perde** — é o passo de ops que não pode ser esquecido.
4. **Rotação é do Vault.** O ciphertext carrega a versão (`vault:v2:…`) e o decrypt continua
   funcionando após `vault write -f transit/keys/<nome>/rotate`. Por isso o `key_id` gravado no
   token é `vault:<mount>:<chave>` **sem versão** — versão no id engessaria a rotação.
5. **Migração sem big bang.** `unwrap` de um `key_id` que não é do Vault, e `by_id`/`active`
   (formatos v1 e legado), **delegam ao provedor de ambiente**. Registro cifrado antes da adoção
   continua legível; o novo já nasce no cofre. Não há janela de indisponibilidade nem re-cifra de
   tudo de uma vez.
6. **`by_id` de um id do Vault falha explícito.** Pedir "a KEK em bytes" ao cofre é justamente o que
   não se faz — a mensagem diz isso e aponta a migração de tokens v1 para envelope.
7. **Erro é opaco.** Qualquer falha (rede, timeout, HTTP 4xx/5xx, JSON) vira `KeyMissing` contendo
   **só** o tipo da exceção ou o status. O corpo de erro do Vault pode ecoar o contexto, e o token
   de acesso jamais entra em log, exceção ou URL — vai só no cabeçalho `X-Vault-Token`.
8. **`KEY_PROVIDER=vault` sem `VAULT_ADDR`/`VAULT_TOKEN` levanta.** Cair calado para o ambiente
   daria a impressão de custódia em HSM sem que ela exista — pior do que assumir que não há Vault.
9. **O padrão continua sendo o ambiente.** Nada muda para quem não configurar nada: o piloto sobe
   como hoje. Sem `httpx` novo no `requirements` (já era dependência) e sem SDK do Vault.

## Alternativas consideradas

- **AWS KMS / GCP KMS.** Rejeitadas por ora: mais um operador estrangeiro no ROPA/DPA (F1.4) e
  dependência de conta em nuvem — o mesmo obstáculo que travou o deploy na Fly (cartão). Encaixam
  na mesma porta quando/se a instituição decidir.
- **Fly Secrets como "KMS".** Rejeitada: é a custódia atual com outro rótulo — a chave continua
  chegando ao processo como variável. Não fecharia C11.
- **Vault com `hvac` (SDK oficial).** Rejeitada: uma dependência a mais para dois endpoints HTTP;
  `httpx` já está no projeto e o adaptador cabe em ~40 linhas auditáveis.
- **Chave `derived=false` + AAD ignorado.** Rejeitada: perderia a amarração participante+campo que o
  ADR-088 construiu — mover um valor cifrado de um registro para outro voltaria a ser possível.
- **Guard de produção exigindo Vault** (recusar subir com `KEY_PROVIDER=env` em produção).
  Rejeitada: quebraria o deploy já planejado na Fly, onde não há Vault. A pendência fica **declarada**
  no RIPD/checklist, que é onde a decisão de aceitá-la ou não pertence — ao controlador, não ao código.

## Consequências

**Positivas:** C11 deixa de ser "seam pronto, adaptador ausente" e passa a "adaptador pronto,
provisionamento pendente"; a promessa do ADR-059/087 está cumprida em código testado; a migração é
incremental e reversível. **+9 testes** (suíte 342→351).

**Negativas / a vigiar:**
- **Não há Vault no ar.** Isto entrega o *código*; alguém precisa **hospedar e operar** um Vault
  (selar/dessellar, política, renovação de token, backup) — carga operacional real para uma equipe
  pequena. Enquanto isso, o padrão segue `env` e **C11 continua aberto na prática**.
- **Latência e disponibilidade:** cada leitura/escrita de PII passa a depender do cofre (timeout 5 s
  por padrão). Vault fora = PII ilegível (falha explícita, não silenciosa). Isso é a contrapartida
  esperada de custódia externa, mas muda o perfil de disponibilidade do `/ready`.
- **O token do Vault vira o novo segredo crítico** no ambiente. Sem AppRole/renovação automática
  (fora desta fatia), é um token de vida longa — melhor que a KEK em claro, mas não é o fim da
  história.
- `derived=true` é responsabilidade de quem provisiona; se a chave for criada sem isso, o `context`
  é aceito e ignorado, e a amarração some **sem erro visível**. Está no runbook e aqui.

## Verificação

`tests/test_key_custody_vault.py` (9), com um Vault de mentira no transporte do `httpx` (sem rede):
round-trip de PII ponta a ponta com a KEK fora da aplicação; **contexto diferente não decifra**;
dado embrulhado antes da adoção continua legível pelo provedor Vault e o novo já nasce no cofre;
`by_id` de id do Vault falha explícito; Vault fora vira `KeyMissing` **sem** vazar o token; erro HTTP
não ecoa o corpo (só o status); `KEY_PROVIDER=vault` sem endereço/token levanta; o padrão continua
sendo o ambiente; e o token nunca aparece na URL.
