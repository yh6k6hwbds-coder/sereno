import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Guarda os tokens do participante de forma segura (Keychain/Keystore).
class SessionStore {
  static const _access = 'sereno.access';
  static const _refresh = 'sereno.refresh';
  final FlutterSecureStorage _s = const FlutterSecureStorage();

  Future<void> saveTokens(String access, String refresh) async {
    await _s.write(key: _access, value: access);
    await _s.write(key: _refresh, value: refresh);
  }

  Future<String?> accessToken() => _s.read(key: _access);
  Future<String?> refreshToken() => _s.read(key: _refresh);
  Future<bool> isAuthenticated() async => (await accessToken()) != null;
  Future<void> clear() => _s.deleteAll();
}
