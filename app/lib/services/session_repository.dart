import '../core/api_client.dart';
import 'session_store.dart';

/// Dados neutros devolvidos ao iniciar a sessão. Note que NÃO há braço/condição:
/// apenas o id, o handle da banda (idêntico nos dois braços) e o hash do áudio.
class SessionStart {
  final String sessionId;
  final String protocolHandle;
  final String contentHash;
  SessionStart({required this.sessionId, required this.protocolHandle, required this.contentHash});
}

/// Fala com a API de sessão. A resolução ativo/sham é do servidor — o cliente
/// nunca a conhece; apenas reproduz o arquivo referenciado por [contentHash].
class SessionRepository {
  final ApiClient api;
  final SessionStore store;
  SessionRepository(this.api, this.store);

  Future<SessionStart> start({required String protocolHandle, required bool headphonesOk}) async {
    final d = await api.post('/sessions',
        {'protocol_handle': protocolHandle, 'headphones_ok': headphonesOk},
        authenticated: true);
    return SessionStart(
      sessionId: d['session_id'] as String,
      protocolHandle: d['protocol_handle'] as String,
      contentHash: d['content_hash'] as String,
    );
  }

  Future<void> complete(String sessionId,
          {required int effectiveSeconds, required int interruptions}) =>
      api.post('/sessions/$sessionId/complete',
          {'effective_seconds': effectiveSeconds, 'interruptions': interruptions},
          authenticated: true);
}
