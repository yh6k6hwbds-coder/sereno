import '../core/api_client.dart';

/// Dose de exposição auditiva (G9). O protocolo promete "contabilização de dose acumulada"
/// e "alerta ao atingir 50% do limite de referência" (80 dB(A) por 40 h SEMANAIS, OMS/UIT).
///
/// A conta é do servidor — ele tem o histórico de sessões e o nível calibrado; o cliente só
/// exibe. `calibrated == false` significa que a calibração em acoplador de orelha ainda não
/// foi feita e o número é PREVISÃO no nível prescrito, não medida: a tela precisa dizê-lo.
class HearingExposure {
  final bool calibrated;
  /// % da permissão SEMANAL consumida nos últimos 7 dias — é o que o alerta observa.
  final double weekPct;
  /// % acumulada no estudo inteiro, na mesma régua semanal ("dose acumulada").
  final double totalPct;
  final double totalHours;
  final double alertAtPct;
  final bool alert;

  const HearingExposure({
    required this.calibrated,
    required this.weekPct,
    required this.totalPct,
    required this.totalHours,
    required this.alertAtPct,
    required this.alert,
  });

  factory HearingExposure.fromJson(Map<String, dynamic> j) => HearingExposure(
        calibrated: j['calibrated'] as bool? ?? false,
        weekPct: (j['week_pct'] as num?)?.toDouble() ?? 0,
        totalPct: (j['total_pct'] as num?)?.toDouble() ?? 0,
        totalHours: (j['total_hours'] as num?)?.toDouble() ?? 0,
        alertAtPct: (j['alert_at_pct'] as num?)?.toDouble() ?? 50,
        alert: j['alert'] as bool? ?? false,
      );
}

/// Onde o participante está no protocolo (G6): semana, adesão e a avaliação
/// intermediária (T2) da 2ª semana, mais a dose de exposição auditiva (G9).
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
  /// Dose de exposição auditiva. `null` só se o servidor for anterior ao G9.
  final HearingExposure? hearing;

  const ProtocolProgress({
    required this.status,
    required this.allocated,
    required this.studyWeek,
    required this.sessionsCompleted,
    required this.sessionsPrescribed,
    required this.t2Due,
    required this.t2Late,
    required this.discontinuedReason,
    this.hearing,
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
      hearing: j['hearing'] == null
          ? null
          : HearingExposure.fromJson(j['hearing'] as Map<String, dynamic>),
    );
  }
}

class ProgressRepository {
  final ApiClient api;
  ProgressRepository(this.api);

  Future<ProtocolProgress> myProgress() async =>
      ProtocolProgress.fromJson(await api.get('/participants/me/status', authenticated: true));
}
