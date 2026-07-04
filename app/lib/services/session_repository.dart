import 'dart:typed_data';
import 'package:crypto/crypto.dart';

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

/// O áudio baixado não bate com o ETag do servidor (corrupção/adulteração): a
/// reprodução bit-a-bit é inegociável, então recusamos tocar.
class AudioIntegrityException implements Exception {
  final String message;
  AudioIntegrityException(this.message);
  @override
  String toString() => message;
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

  /// Baixa o áudio da sessão e VERIFICA a fidelidade bit-a-bit: o sha256 do corpo
  /// deve igualar o ETag do servidor. Divergiu → [AudioIntegrityException] (não toca).
  /// O cliente não conhece o braço: só reproduz os bytes referenciados pela sessão.
  Future<Uint8List> downloadAudio(String sessionId) async {
    final r = await api.getBytes('/sessions/$sessionId/audio', authenticated: true);
    final etag = r.etag?.replaceAll('"', '');
    if (etag != null && etag.isNotEmpty) {
      final digest = sha256.convert(r.bytes).toString();
      if (digest != etag) {
        throw AudioIntegrityException('Falha de integridade do áudio (hash divergente).');
      }
    }
    return r.bytes;
  }
}
