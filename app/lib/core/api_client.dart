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

/// Resposta binária (ex.: áudio da sessão): bytes do corpo + ETag (integridade).
class BytesResponse {
  final Uint8List bytes;
  final String? etag;
  BytesResponse(this.bytes, this.etag);
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

  /// GET binário: baixa bytes (ex.: WAV da sessão) e devolve corpo + ETag.
  Future<BytesResponse> getBytes(String path, {bool authenticated = false}) async {
    var res = await _doGet(path, authenticated);
    if (authenticated && res.statusCode == 401 && await _tryRefresh()) {
      res = await _doGet(path, authenticated);
    }
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return BytesResponse(res.bodyBytes, res.headers['etag']);
    }
    _throwProblem(res.statusCode, _decode(res.bodyBytes));
  }

  Future<http.Response> _doPost(String path, Map<String, dynamic> body, bool authenticated) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    await _maybeAuth(headers, authenticated);
    return _http.post(Uri.parse('$apiBaseUrl$path'), headers: headers, body: jsonEncode(body));
  }

  Future<http.Response> _doGet(String path, bool authenticated) async {
    final headers = <String, String>{};
    await _maybeAuth(headers, authenticated);
    return _http.get(Uri.parse('$apiBaseUrl$path'), headers: headers);
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
