# ADR-087 — Custódia da chave de PII atrás de porta (KMS-ready) + rotação por id de chave

- **Status:** Aceito
- **Data:** 2026-07-20
- **Decisores:** Mantenedor (Augusto) + arquiteto (Claude)
- **Etapas relacionadas:** 5 (backend/segurança/LGPD)
- **Contexto de origem:** item **C11** do `docs/lgpd-nit-checklist.md` — "custódia de chaves em
  KMS/cofre gerenciado"; e a promessa do ADR-059 ("a custódia evolui para envelope/KMS").
- **Relaciona-se com:** ADR-059 (cifra de PII AES-256-GCM), inegociável #6 (PII cifrada e
  separada, cripto em repouso), ADR-065 (segredos por env/secret no compose).

## Contexto
A PII é cifrada com `PII_ENC_KEY` (AES-256-GCM) lida **direto do ambiente** dentro de
`pii_crypto`. Dois limites para produção: (1) a **custódia** — trocar env por KMS/Vault exigia
mexer no módulo de cripto; (2) **rotação** — a chave era única e o ciphertext não dizia qual chave
o cifrou, então rotacionar significaria re-cifrar tudo de uma vez. O escopo do piloto pede
**preparar, não construir** (CLAUDE.md): não faz sentido plugar um KMS real agora (conta/infra),
mas faz sentido deixar o **seam** pronto e resolver a rotação.

## Decisão
1. **Porta `KeyProvider`** (`core/keyring.py`), separando custódia de uso:
   - `EnvKeyProvider` (**padrão**): a KEK vem de `PII_ENC_KEY`/`PII_ENC_KEY_ID`; lê o ambiente
     **a cada chamada** (rotação sem reiniciar). Custódia atual do piloto — inalterada.
   - Um `KmsKeyProvider` (futuro) implementa a **mesma** porta (`active()`/`by_id()`) buscando/
     desembrulhando a KEK num **KMS/Vault** (a chave não sai do HSM; ou é buscada no boot).
     Encaixa **sem tocar no `pii_crypto`** — é a evolução prometida no ADR-059, agora com seam.
     Injeção via `set_key_provider()` (também usada nos testes).
2. **Ciphertext versionado com id de chave** (`pii_crypto`): novo formato
   `0x01 || len(key_id) || key_id || nonce || ct`. O id viaja no token → dá para **rotacionar**:
   a chave ativa (`PII_ENC_KEY_ID`) cifra o novo; chaves **aposentadas** (`PII_ENC_KEYS`,
   `id:base64,...`) seguem **decifrando** o que já existe. Sem re-cifrar tudo de uma vez.
3. **Compatibilidade retroativa:** tokens no formato antigo (`nonce || ct`, sem byte de versão)
   ainda decifram com a chave ativa. Sem migração de schema (a coluna é binária; o formato é
   auto-descritivo).
4. **Segurança preservada:** o AAD continua ligando o ciphertext a participante+campo; o id de
   chave **não** precisa estar no AAD — apontar para outra chave apenas faz o GCM falhar (tag),
   nunca forja. Nada é logado; chave ausente/ inválida/ desconhecida falha explícito (`KeyMissing`).

## Alternativas consideradas
- **Plugar AWS KMS/Vault agora.** Rejeitada: exige conta/infra e é "construir" (fora do MVP). A
  porta deixa o adaptador como drop-in.
- **Envelope por registro (DEK por linha, embrulhada pela KEK).** Adiada: é o passo seguinte de
  KMS (o KMS embrulha DEKs), mas adiciona overhead por registro e complexidade; a porta + rotação
  por id já entrega o essencial (custódia trocável, rotação sem re-cifrar). Registrado como evolução.
- **Manter chave única sem id.** Rejeitada: impossibilita rotação incremental — um vazamento/
  troca obrigaria re-cifrar tudo num único golpe.
- **Desambiguar legado por comprimento.** Descartada: formatos novo e antigo têm faixas de
  tamanho sobrepostas; o byte de versão é o sinal. Limitação conhecida: um token **antigo** cujo
  nonce comece por `0x01` (~0,4%) seria mal interpretado — **não há dado legado em produção** (o
  formato versionado é o primeiro implantado); se houver dado de demo, re-semear resolve.

## Consequências
- **Positivas:** custódia da chave vira trocável por KMS/Vault sem mexer na cripto; **rotação**
  de chave passa a ser possível de forma incremental; comportamento e testes de PII preservados
  (compat retroativa). Suíte 261 → 267 (+6); cobertura 90%. Sem migração.
- **Custo/tradeoff:** o ciphertext cresce ~poucos bytes (byte de versão + id de chave curto). A
  desambiguação de legado por byte de versão tem a ressalva acima (irrelevante sem dado legado).
- **Pendências:** adaptador **KMS/Vault** real (a "construção" da C11) — implementa a porta;
  envelope por DEK se/quando o KMS pedir; procedimento operacional de rotação (gerar `k2`, mover
  `k1` para `PII_ENC_KEYS`, re-cifrar em background e aposentar `k1`). C11 **segue 🟡** até o
  adaptador de KMS existir — o seam e a rotação estão prontos, a custódia gerenciada não.

## Conformidade
CI verde exige `tests/test_key_custody.py`: round-trip com id embutido; **rotação** (dado velho
decifra via chave aposentada, novo usa a nova); id desconhecido → `KeyMissing`; o provedor
alternativo (simulando KMS) é **drop-in** e a cifra passa por ele; formato **legado** ainda
decifra; sem chave → `KeyMissing`. `test_contact.py`/`test_data_rights.py`/`test_notifications.py`
seguem **verdes sem mudança** (compat). Sem chave em log; PII segue cifrada e separada (inegociável #6).
