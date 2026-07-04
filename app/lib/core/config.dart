/// Configuração do cliente. A base da API vem por --dart-define em produção.
/// Ex.: flutter run --dart-define=API_BASE_URL=https://api.sereno.example/v1
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000/v1',
);

/// Versão vigente do TCLE (deve casar com o backend).
const String tcleVersion = '1.0.0';

/// Duração padrão da sessão em segundos (metadado neutro — igual nos dois braços).
/// Futuro: receber do protocolo via campo neutro na resposta de início.
const int sessionDurationSeconds = 1200; // 20 min
