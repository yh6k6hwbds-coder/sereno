# ADR-050 — Fundação do cliente Flutter (primeira fatia: OTP + consentimento)

- **Status:** Aceito
- **Data:** 2026-07-03
- **Etapas relacionadas:** 3 (UX/identidade), 5 (contrato)
- **Contexto de origem:** 10ª fatia (o repositório deixa de ser só backend)

## Decisão
1. **Organização por feature** (`lib/core`, `lib/services`, `lib/shared`, `lib/features/<fluxo>`),
   espelhando o backend modular.
2. **Dependências mínimas nesta fatia**: `http` (rede) e `flutter_secure_storage` (tokens no
   Keychain/Keystore). Estado por `StatefulWidget` local; navegação por `Navigator`.
3. **Erros de API** traduzidos de **problem+json** para `ApiException` num `ApiClient` fino.
4. **Identidade "Sereno"** (Etapa 3) codificada no tema (paleta noturna, tipografia Fraunces/
   Inter/IBM Plex Mono, a onda de interferência como assinatura). Aviso de escopo **persistente**.
5. **Config por `--dart-define`** (`API_BASE_URL`); nada de segredo embarcado.

## Alternativas consideradas
- **Riverpod + go_router desde já.** Adiado: para duas telas, adiciona complexidade não
  verificável. **Adotar quando o número de telas/estado crescer** (fatias de sessão/diário).
- **google_fonts (fontes via rede).** Adiado: preferir **empacotar** as fontes (offline-first).

## Consequências
- **Positivas:** cliente limpo, testável e alinhado ao contrato; pronto para as próximas telas.
- **Pendências:** empacotar as fontes; introduzir Riverpod + go_router; testes de widget;
  fluxo de refresh de token; telas de sessão/pós-sessão/diário.
- **Nota:** não compilado no ambiente de planejamento (sem SDK Flutter); requer
  `flutter pub get && flutter analyze` localmente.

## Conformidade
O job `app` do CI roda `flutter analyze` + `flutter test` (não bloqueante por ora, até haver
testes de widget). Backend permanece o gate rígido.
