import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

/// Encerramento de sessão pendente de envio (telemetria de adesão). É neutro quanto
/// ao braço: só duração efetiva e interrupções.
class PendingComplete {
  final String sessionId;
  final int effectiveSeconds;
  final int interruptions;
  PendingComplete({
    required this.sessionId,
    required this.effectiveSeconds,
    required this.interruptions,
  });

  Map<String, dynamic> toJson() => {
        'session_id': sessionId,
        'effective_seconds': effectiveSeconds,
        'interruptions': interruptions,
      };

  factory PendingComplete.fromJson(Map<String, dynamic> j) => PendingComplete(
        sessionId: j['session_id'] as String,
        effectiveSeconds: j['effective_seconds'] as int,
        interruptions: j['interruptions'] as int,
      );
}

/// Fila persistente da telemetria. Interface para permitir um fake em teste (a
/// implementação em disco usa path_provider, que não roda em `flutter test`).
abstract class TelemetryQueue {
  Future<void> add(PendingComplete item);
  Future<List<PendingComplete>> all();
  Future<void> removeFor(String sessionId);
}

/// Implementação em disco: um arquivo JSON por sessão no diretório de documentos.
/// Simples e suficiente para o piloto (a sessão é única por vez).
class FileTelemetryQueue implements TelemetryQueue {
  Future<Directory> _dir() async {
    final base = await getApplicationDocumentsDirectory();
    final d = Directory('${base.path}/telemetry_queue');
    if (!await d.exists()) await d.create(recursive: true);
    return d;
  }

  @override
  Future<void> add(PendingComplete item) async {
    final d = await _dir();
    await File('${d.path}/${item.sessionId}.json')
        .writeAsString(jsonEncode(item.toJson()));
  }

  @override
  Future<List<PendingComplete>> all() async {
    final d = await _dir();
    final out = <PendingComplete>[];
    for (final e in d.listSync()) {
      if (e is File && e.path.endsWith('.json')) {
        out.add(PendingComplete.fromJson(
            jsonDecode(await e.readAsString()) as Map<String, dynamic>));
      }
    }
    return out;
  }

  @override
  Future<void> removeFor(String sessionId) async {
    final d = await _dir();
    final f = File('${d.path}/$sessionId.json');
    if (await f.exists()) await f.delete();
  }
}

/// Envia o encerramento; se a rede falhar, ENFILEIRA para reenvio posterior.
/// Desacoplado do repositório por um callback [send] (facilita teste e troca).
typedef CompleteSender = Future<void> Function(PendingComplete item);

class TelemetrySender {
  final CompleteSender send;
  final TelemetryQueue queue;
  TelemetrySender(this.send, this.queue);

  /// Tenta enviar agora; em falha, guarda na fila. Retorna true se enviou.
  Future<bool> submit(PendingComplete item) async {
    try {
      await send(item);
      return true;
    } catch (_) {
      await queue.add(item);
      return false;
    }
  }

  /// Reenvia (best-effort) tudo que está na fila; remove os que forem aceitos.
  Future<void> flush() async {
    for (final item in await queue.all()) {
      try {
        await send(item);
        await queue.removeFor(item.sessionId);
      } catch (_) {/* mantém na fila para a próxima tentativa */}
    }
  }
}
