# ADR-088 — Envelope encryption da PII (DEK por registro embrulhada pela KEK)

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança/LGPD)
- **Contexto de origem:** evolução nomeada no ADR-087 ("envelope por registro … é o passo seguinte
  de KMS") — item **C11** do `docs/lgpd-nit-checklist.md`.
- **Relaciona-se com:** ADR-087 (porta `KeyProvider` + rotação por id), ADR-059 (cifra de PII),
  inegociável #6 (PII cifrada e separada).

## Contexto
O ADR-087 deixou a chave de PII atrás de uma porta e habilitou rotação, mas a **KEK cifrava a
PII diretamente** (formato v1). O padrão que os KMS usam — e o que permite a KEK **nunca sair do
HSM** — é o **envelope**: uma chave de dados (DEK) aleatória cifra cada valor, e a KEK apenas
**embrulha/desembrulha** a DEK. Assim a app nunca manuseia a PII com a KEK, e um KMS real faz só
`wrap`/`unwrap` de DEKs (a KEK é opaca à aplicação). Faltava dar esse passo — testável **sem** conta
de nuvem, simulando o wrap/unwrap localmente.

## Decisão
1. **A porta `KeyProvider` ganha `wrap(dek, aad) -> (key_id, blob)` e `unwrap(key_id, blob, aad)
   -> dek`** (`core/keyring.py`). O `blob` é **opaco** ao chamador: o `EnvKeyProvider` o produz
   com AES-GCM(KEK) localmente; um `KmsKeyProvider` o produziria chamando o KMS (a KEK nunca
   exposta). `active()`/`by_id()` seguem para decifrar formatos antigos.
2. **`pii_crypto` passa a cifrar por envelope (formato v2, `0x02`):** DEK aleatória de 32 bytes por
   registro cifra a PII; a KEK embrulha a DEK; o token guarda `id da chave || wrap_blob || nonce ||
   ct`. A **KEK não cifra a PII** — só embrulha DEKs.
3. **AAD em ambas as camadas:** o mesmo AAD (participante+campo) liga tanto a **DEK embrulhada**
   quanto o **ciphertext** da PII — mover/renomear um valor entre linhas/campos falha o GCM.
4. **Compatibilidade retroativa mantida:** tokens **v1** (`0x01`, KEK direto, ADR-087) e **legado**
   (`nonce || ct`) ainda **decifram**. Novo dado é sempre v2. Sem migração de schema (coluna
   binária; formato auto-descritivo pelo 1º byte).
5. **Rotação preservada:** rotacionar a KEK re-embrulha DEKs (a KEK aposentada segue
   desembrulhando o que já existe) — sem re-cifrar a PII.

## Alternativas consideradas
- **Manter KEK cifrando a PII direto (v1).** Rejeitada: não é o modelo de KMS (exigiria a KEK
  manusear a PII) e dificulta a troca por HSM. Mantido só para **decrypt** de dados v1.
- **DEK derivada (KDF) em vez de aleatória.** Rejeitada: DEK aleatória por registro é mais simples
  e não acopla a segurança a um contexto de derivação; o custo (embrulho por registro) é ínfimo.
- **Plugar KMS real agora.** Fora do escopo (infra/credenciais). O envelope + a porta `wrap/unwrap`
  deixam o `KmsKeyProvider` como drop-in.

## Consequências
- **Positivas:** a PII passa a usar o padrão de envelope (DEK por registro), pronto para um KMS que
  só faça `wrap`/`unwrap`; a KEK nunca toca a PII; rotação e compat retroativa preservadas. Suíte
  267 → 273 (+6); cobertura 90%. Sem migração.
- **Custo/tradeoff:** cada token cresce ~pelo `wrap_blob` (≈60 bytes no env) + cabeçalho. A DEK vive
  em memória durante a operação (o Python não zera memória de forma garantida — aceitável no piloto;
  registrado). Desambiguação de formato pelo 1º byte (ver ADR-087) — sem dado legado em produção.
- **Pendências:** o adaptador **KMS/Vault** real (implementa `wrap`/`unwrap` via API) — a
  "construção" que fecha C11; re-cifra em background ao rotacionar; zeroização de DEK se algum dia
  for requisito. **C11 segue 🟡** até o adaptador de KMS existir.

## Conformidade
CI verde exige `tests/test_pii_envelope.py`: formato `0x02` + round-trip; **DEK por registro**
(mesmo texto → tokens distintos); AAD ligando DEK embrulhada e ct (troca de campo/linha falha); a
KEK **não** cifra a PII (desembrulhar dá a DEK, não o texto); token **v1** ainda decifra; rotação da
KEK sob envelope. `tests/test_key_custody.py` atualizado (byte de versão `0x02`; provedor "KMS"
injetado prova que a cifra passa por `wrap`/`unwrap`). `test_contact`/`test_data_rights`/
`test_notifications` seguem verdes. PII cifrada e separada; nada logado (inegociável #6).
