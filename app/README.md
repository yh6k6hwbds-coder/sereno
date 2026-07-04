# Sereno — cliente Flutter

App multiplataforma (iOS/Android) do piloto. **Ferramenta complementar; não substitui
cuidado profissional.** Leia o `../CLAUDE.md` para as decisões inegociáveis.

## Rodar (localmente, requer Flutter SDK)
```bash
flutter pub get
flutter analyze
flutter run --dart-define=API_BASE_URL=http://SEU_HOST:8000/v1
```

## Estrutura
- `lib/core/` — config, tema (identidade "Sereno"), `api_client` (problem+json → ApiException).
- `lib/services/` — `session_store` (tokens seguros), `participant_repository` (OTP, consentimento).
- `lib/shared/` — widgets (onda-assinatura, aviso persistente).
- `lib/features/<fluxo>/` — telas por fluxo (auth, consent, home).

## Estado atual (1ª fatia)
Fluxo: **OTP** → **consentimento (TCLE)** → **início** → **preparar (fones)** → **sessão** (visualização não reativa ao áudio + telemetria de duração/interrupções, encerrando em `/sessions/{id}/complete`). Próximo: empacotar fontes, Riverpod + go_router, telas de sessão/diário,
testes de widget. Ver `docs/decisoes/ADR-050`.
