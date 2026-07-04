import 'dart:convert';
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

/// Cliente HTTP mínimo: injeta o token quando necessário e traduz erros
/// problem+json em [ApiException]. Mantém a superfície pequena e testável.
class ApiClient {
  final SessionStore store;
  final http.Client _http;
  ApiClient(this.store, {http.Client? client}) : _http = client ?? http.Client();

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body,
      {bool authenticated = false}) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (authenticated) {
      final token = await store.accessToken();
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }
    final res = await _http.post(Uri.parse('$apiBaseUrl$path'),
        headers: headers, body: jsonEncode(body));
    return _handle(res);
  }

  Map<String, dynamic> _handle(http.Response res) {
    Map<String, dynamic> data = <String, dynamic>{};
    if (res.body.isNotEmpty) {
      try {
        data = jsonDecode(res.body) as Map<String, dynamic>;
      } catch (_) {/* corpo não-JSON */}
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return data;
    throw ApiException(res.statusCode,
        (data['title'] ?? 'Erro').toString(), data['detail']?.toString());
  }
}
