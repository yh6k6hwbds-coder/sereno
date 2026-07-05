import '../core/api_client.dart';

/// Envia os desfechos do participante à API (linha de base, pós-sessão, diário,
/// seguimento, evento adverso). Mantém a regra fora das telas (testável). Os escores
/// são calculados/versionados NO SERVIDOR — o cliente só envia os itens brutos.
class OutcomesRepository {
  final ApiClient api;
  OutcomesRepository(this.api);

  /// Linha de base: GAD-7 (7 itens 0–3) + PSQI (mapa bruto). Devolve escores versionados.
  Future<Map<String, dynamic>> submitBaseline(
          {required List<int> gad7, required Map<String, dynamic> psqi}) =>
      api.post('/participants/me/baseline',
          {'gad7_items': gad7, 'psqi': psqi}, authenticated: true);

  /// Micro-questionário pós-sessão (itens 0–4 + would_repeat).
  Future<void> submitSurvey(String sessionId,
          {required int feeling, required int relaxation, int? sleptBetter,
          required int liked, required int intensity, required bool wouldRepeat}) =>
      api.post('/sessions/$sessionId/survey', {
        'feeling': feeling, 'relaxation': relaxation, 'slept_better': sleptBetter,
        'liked': liked, 'intensity': intensity, 'would_repeat': wouldRepeat,
      }, authenticated: true);

  /// Diário de sono (um por dia). Campos opcionais; só `diary_date` é obrigatório.
  Future<void> submitDiary(
          {required String date, int? latencyMin, int? awakenings,
          double? durationH, int? quality}) =>
      api.post('/diary', {
        'diary_date': date, 'latency_min': latencyMin, 'awakenings': awakenings,
        'duration_h': durationH, 'quality': quality,
      }, authenticated: true);

  /// Seguimento: GAD-7 + PSQI + SUS (10 itens 1–5) + palpite de cegamento (A/B/nao_sei).
  Future<Map<String, dynamic>> submitFollowup(
          {required List<int> gad7, required Map<String, dynamic> psqi,
          required List<int> sus, required String blindingGuess}) =>
      api.post('/participants/me/followup', {
        'gad7_items': gad7, 'psqi': psqi, 'sus_items': sus, 'blinding_guess': blindingGuess,
      }, authenticated: true);

  /// Relato de evento adverso. `severity` ∈ {mild, moderate, severe}.
  Future<Map<String, dynamic>> reportAdverseEvent(
          {required String type, required String severity, String? sessionId, String? action}) =>
      api.post('/adverse-events', {
        'type': type, 'severity': severity, 'session_id': sessionId, 'action': action,
      }, authenticated: true);
}
