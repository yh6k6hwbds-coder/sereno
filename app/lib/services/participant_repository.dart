import '../core/api_client.dart';
import 'session_store.dart';

/// Orquestra o acesso do participante à API: OTP (login sem senha) e consentimento.
/// Mantém a regra de negócio fora das telas (testável e reutilizável).
class ParticipantRepository {
  final ApiClient api;
  final SessionStore store;
  ParticipantRepository(this.api, this.store);

  /// Solicita um código de uso único (resposta genérica no servidor — sem enumeração).
  Future<void> requestOtp(String studyCode) =>
      api.post('/auth/participant/request-otp', {'study_code': studyCode});

  /// Verifica o OTP; em sucesso, guarda os tokens de participante.
  Future<void> verifyOtp(String studyCode, String code) async {
    final data = await api.post(
        '/auth/participant/verify-otp', {'study_code': studyCode, 'code': code});
    await store.saveTokens(
        data['access_token'] as String, data['refresh_token'] as String);
  }

  /// Registra o consentimento (TCLE) — requer participante autenticado.
  Future<void> recordConsent({required String version, required bool accepted}) =>
      api.post('/participants/me/consent',
          {'tcle_version': version, 'accepted': accepted}, authenticated: true);
}
