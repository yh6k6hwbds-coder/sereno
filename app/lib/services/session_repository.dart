import '../core/api_client.dart';
import 'audio_bytes_source.dart';
import 'audio_cache.dart';
import 'audio_cache_key.dart';
import 'session_store.dart';

// Quem falava com o repositório para pegar o áudio já importava esta exceção daqui;
// a definição mudou de casa junto com a verificação de integridade (ADR-103).
export 'audio_cache.dart' show AudioIntegrityException;

/// Resultado da verificação DICÓTICA de fones (G4), enviado ao iniciar a sessão.
///
/// `errors` descreve a tentativa ACEITA (sempre 0 — o servidor recusa outra coisa);
/// `attempts` diz quantas tentativas foram necessárias, que é o que interessa à auditoria
/// quando alguém precisa refazer o teste (fone invertido, por exemplo).
class HeadphoneCheckResult {
  static const String version = '1.0.0';
  final int rounds;
  final int errors;
  final int attempts;
  final String ears;      // orelhas sorteadas na tentativa aceita, na ordem (ex.: "LR")
  const HeadphoneCheckResult(
      {required this.rounds, required this.errors, required this.attempts, required this.ears});

  Map<String, dynamic> toJson() => {
        'version': version,
        'rounds': rounds,
        'errors': errors,
        'attempts': attempts,
        'ears': ears,
      };
}

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

  /// Biblioteca local cifrada do áudio. O padrão é a de produção — cujas funções são
  /// preguiçosas, então nada de plataforma é tocado até haver um download de verdade.
  final AudioCache audioCache;

  SessionRepository(this.api, this.store, {AudioCache? audioCache})
      : audioCache = audioCache ?? productionAudioCache();

  Future<SessionStart> start({
    required String protocolHandle,
    required HeadphoneCheckResult headphoneCheck,
    required double audioGain,
  }) async {
    final d = await api.post(
        '/sessions',
        {
          'protocol_handle': protocolHandle,
          'headphone_check': headphoneCheck.toJson(),
          'audio_gain': audioGain,
        },
        authenticated: true);
    return SessionStart(
      sessionId: d['session_id'] as String,
      protocolHandle: d['protocol_handle'] as String,
      contentHash: d['content_hash'] as String,
    );
  }

  /// Encerra a sessão com o registro que o protocolo pede (G10). Os campos opcionais
  /// são omitidos quando nulos: o servidor não sobrescreve com nulo o que já gravou.
  Future<void> complete(String sessionId,
          {required int effectiveSeconds,
          required int interruptions,
          int? pausedSeconds,
          double? gainMean,
          double? gainPeak,
          int? relaxation0to10}) =>
      api.post('/sessions/$sessionId/complete', {
        'effective_seconds': effectiveSeconds,
        'interruptions': interruptions,
        if (pausedSeconds != null) 'paused_seconds': pausedSeconds,
        if (gainMean != null) 'gain_mean': gainMean,
        if (gainPeak != null) 'gain_peak': gainPeak,
        if (relaxation0to10 != null) 'relaxation_0_10': relaxation0to10,
      }, authenticated: true);

  /// Devolve a fonte do áudio da sessão, baixando-o **uma vez por protocolo**.
  ///
  /// As 20 sessões do estudo usam o mesmo arquivo; rebaixá-lo a cada sessão gastaria
  /// centenas de megabytes da rede móvel do participante (ADR-103). Então:
  ///
  ///   1. se há entrada no cache, ela é conferida (selo) e o servidor é consultado com
  ///      `If-None-Match` — **304** significa "continua valendo" e nada trafega;
  ///   2. se o artefato mudou (ou não havia cache), o corpo é gravado cifrado enquanto
  ///      chega, com o sha256 do claro conferido contra o `ETag` — divergiu, não toca;
  ///   3. se a rede falhar e houver entrada conferida, ela serve: o participante não
  ///      perde a sessão do dia por causa de conectividade.
  ///
  /// O cliente segue sem conhecer o braço: [contentHash] é a identidade OPACA do protocolo,
  /// que é também a chave do cache.
  Future<AudioBytesSource> obtainAudio(String sessionId,
      {required String contentHash}) async {
    final guardado = await audioCache.lookup(contentHash);
    StreamedBytes resposta;
    try {
      resposta = await api.getByteStream('/sessions/$sessionId/audio',
          authenticated: true, ifNoneMatch: guardado?.etag);
    } catch (_) {
      if (guardado != null) return guardado.source; // offline: o arquivo conferido serve
      rethrow;
    }
    if (resposta.status == 304 && guardado != null) {
      await resposta.stream.drain<void>();
      return guardado.source;
    }
    return audioCache.store(
      contentHash: contentHash,
      corpo: resposta.stream,
      etag: resposta.etag,
      contentType: resposta.contentType ?? 'audio/flac',
    );
  }
}
