/// Configuração do cliente. A base da API é fixada em build por --dart-define
/// (ex.: flutter build --dart-define=API_BASE_URL=https://api.sereno.example/v1).
const String _compiledApiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000/v1',
);

/// Base da API em uso. Na **web**, aceita um override em runtime pelo parâmetro
/// de URL `?api=<https-url>` — assim o app publicado pode ser apontado para outro
/// backend (ex.: um túnel novo) **sem recompilar**: basta abrir o link com o
/// parâmetro. Só aceita `https` (evita mixed-content e aponta apenas para destinos
/// seguros). No mobile/desktop, `Uri.base` não traz o parâmetro e cai no valor de
/// build. Ver docs/rodar-por-tunel.md.
String get apiBaseUrl {
  final override = Uri.base.queryParameters['api'];
  if (override != null && override.startsWith('https://')) {
    return override.endsWith('/')
        ? override.substring(0, override.length - 1)
        : override;
  }
  return _compiledApiBaseUrl;
}

/// Versão vigente do TCLE (deve casar com o backend).
const String tcleVersion = '1.0.0';

/// Duração padrão da sessão em segundos (metadado neutro — igual nos dois braços).
/// Futuro: receber do protocolo via campo neutro na resposta de início.
const int sessionDurationSeconds = 1200; // 20 min
