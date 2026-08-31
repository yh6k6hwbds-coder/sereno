import '../core/api_client.dart';

/// Onde o participante está no protocolo (G6): semana, adesão e a avaliação
/// intermediária (T2) da 2ª semana.
///
/// O servidor é quem sabe o calendário — o marco é a alocação, que o aplicativo não
/// conhece, e a régua de adesão (80% da duração) já é dele. O cliente só pergunta e
/// mostra. Nada aqui depende do braço nem o revela.
class ProtocolProgress {
  final String status;
  final bool allocated;
  final int? studyWeek;
  final int sessionsCompleted;
  final int sessionsPrescribed;
  /// T2 devida: a janela abriu e o participante ainda não respondeu.
  final bool t2Due;
  /// A janela do T2 fechou sem resposta — o convite continua, com outra redação.
  final bool t2Late;
  /// Motivo da descontinuação de protocolo, se houve (`null` = segue no protocolo).
  final String? discontinuedReason;

  const ProtocolProgress({
    required this.status,
    required this.allocated,
    required this.studyWeek,
    required this.sessionsCompleted,
    required this.sessionsPrescribed,
    required this.t2Due,
    required this.t2Late,
    required this.discontinuedReason,
  });

  bool get isDiscontinued => status == 'discontinued';

  factory ProtocolProgress.fromJson(Map<String, dynamic> j) {
    final t2 = j['t2'] as Map<String, dynamic>?;
    final saida = j['discontinuation'] as Map<String, dynamic>?;
    return ProtocolProgress(
      status: j['status'] as String? ?? 'active',
      allocated: j['allocated'] as bool? ?? false,
      studyWeek: j['study_week'] as int?,
      sessionsCompleted: j['sessions_completed'] as int? ?? 0,
      sessionsPrescribed: j['sessions_prescribed'] as int? ?? 0,
      t2Due: t2?['due'] as bool? ?? false,
      t2Late: t2?['late'] as bool? ?? false,
      discontinuedReason: saida?['reason'] as String?,
    );
  }
}

class ProgressRepository {
  final ApiClient api;
  ProgressRepository(this.api);

  Future<ProtocolProgress> myProgress() async =>
      ProtocolProgress.fromJson(await api.get('/participants/me/status', authenticated: true));
}
