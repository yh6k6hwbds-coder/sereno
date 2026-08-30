import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;

import 'config.dart';
import '../services/session_store.dart';

/// Erro da API já interpretado a partir de problem+json (RFC 9457).
class ApiException implements Exception {
  final int status;
  final String title;
  final String? detail;
  ApiException(this.status, this.title, this.detail);
  @override
  String toString() => detail ?? title;
}

/// Resposta binária em FLUXO (ex.: áudio da sessão): o corpo chega em blocos.
///
/// Nada aqui materializa o corpo inteiro: uma sessão do estudo tem 20 min e dezenas de
/// megabytes (230 MB se o servidor estiver em WAV), e o aparelho de um participante não
/// tem por que segurar isso na memória. [status] 304 significa "o que você tem em cache
/// continua valendo" — resposta a um `If-None-Match`.
class StreamedBytes {
  final int status;
  final Stream<List<int>> stream;
  final String? etag;
  final String? contentType;
  final int? contentLength;
  StreamedBytes(this.status, this.stream,
      {this.etag, this.contentType, this.contentLength});
}

/// Cliente HTTP mínimo: injeta o token quando necessário e traduz erros
/// problem+json em [ApiException]. No 401 de uma chamada autenticada, tenta um
/// refresh transparente (uma vez) e repete; se o refresh falhar, encerra a sessão.
class ApiClient {
  final SessionStore store;
  final http.Client _http;
  ApiClient(this.store, {http.Client? client}) : _http = client ?? http.Client();

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body,
      {bool authenticated = false}) async {
    var res = await _doPost(path, body, authenticated);
    if (authenticated && res.statusCode == 401 && await _tryRefresh()) {
      res = await _doPost(path, body, authenticated); // repete com o novo token
    }
    return _handle(res);
  }

  /// GET binário em fluxo (o áudio da sessão). Com [ifNoneMatch], o servidor pode
  /// responder **304** e poupar o download inteiro — é o que evita rebaixar o mesmo
  /// arquivo nas 20 sessões do estudo.
  Future<StreamedBytes> getByteStream(String path,
      {bool authenticated = false, String? ifNoneMatch}) async {
    var res = await _doGetStream(path, authenticated, ifNoneMatch);
    if (authenticated && res.statusCode == 401 && await _tryRefresh()) {
      await res.stream.drain<void>(); // não deixa a conexão do 401 pendurada
      res = await _doGetStream(path, authenticated, ifNoneMatch);
    }
    if (res.statusCode == 304 || (res.statusCode >= 200 && res.statusCode < 300)) {
      return StreamedBytes(res.statusCode, res.stream,
          etag: res.headers['etag'],
          contentType: res.headers['content-type'],
          contentLength: res.contentLength);
    }
    _throwProblem(res.statusCode, _decode(await res.stream.toBytes()));
  }

  Future<http.Response> _doPost(String path, Map<String, dynamic> body, bool authenticated) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    await _maybeAuth(headers, authenticated);
    return _http.post(Uri.parse('$apiBaseUrl$path'), headers: headers, body: jsonEncode(body));
  }

  Future<http.StreamedResponse> _doGetStream(
      String path, bool authenticated, String? ifNoneMatch) async {
    final req = http.Request('GET', Uri.parse('$apiBaseUrl$path'));
    await _maybeAuth(req.headers, authenticated);
    if (ifNoneMatch != null && ifNoneMatch.isNotEmpty) {
      req.headers['If-None-Match'] = '"$ifNoneMatch"';
    }
    return _http.send(req);
  }

  Future<void> _maybeAuth(Map<String, String> headers, bool authenticated) async {
    if (!authenticated) return;
    final token = await store.accessToken();
    if (token != null) headers['Authorization'] = 'Bearer $token';
  }

  /// Tenta renovar o access token com o refresh guardado. Retorna true se renovou.
  /// Refresh ausente/ inválido → encerra a sessão (limpa o armazenamento seguro).
  Future<bool> _tryRefresh() async {
    final refresh = await store.refreshToken();
    if (refresh == null) return false;
    final res = await _http.post(Uri.parse('$apiBaseUrl/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': refresh}));
    if (res.statusCode >= 200 && res.statusCode < 300) {
      final d = jsonDecode(res.body) as Map<String, dynamic>;
      await store.saveTokens(d['access_token'] as String, d['refresh_token'] as String);
      return true;
    }
    await store.clear(); // sessão inválida → logout
    return false;
  }

  Map<String, dynamic> _decode(Uint8List bodyBytes) {
    try {
      return jsonDecode(utf8.decode(bodyBytes)) as Map<String, dynamic>;
    } catch (_) {
      return <String, dynamic>{};
    }
  }

  Map<String, dynamic> _handle(http.Response res) {
    Map<String, dynamic> data = <String, dynamic>{};
    if (res.body.isNotEmpty) {
      try {
        data = jsonDecode(res.body) as Map<String, dynamic>;
      } catch (_) {/* corpo não-JSON */}
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return data;
    _throwProblem(res.statusCode, data);
  }

  Never _throwProblem(int status, Map<String, dynamic> data) {
    throw ApiException(status, (data['title'] ?? 'Erro').toString(), data['detail']?.toString());
  }
}
