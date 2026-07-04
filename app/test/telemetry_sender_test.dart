import 'package:flutter_test/flutter_test.dart';
import 'package:sereno/services/telemetry_queue.dart';

/// Fila em memória (o disco/path_provider não roda em `flutter test`).
class _MemQueue implements TelemetryQueue {
  final Map<String, PendingComplete> _m = {};
  @override
  Future<void> add(PendingComplete item) async => _m[item.sessionId] = item;
  @override
  Future<List<PendingComplete>> all() async => _m.values.toList();
  @override
  Future<void> removeFor(String sessionId) async => _m.remove(sessionId);
}

void main() {
  final item = PendingComplete(sessionId: 's1', effectiveSeconds: 120, interruptions: 2);

  test('submit envia e NÃO enfileira quando a rede está ok', () async {
    final q = _MemQueue();
    var sent = 0;
    final s = TelemetrySender((i) async => sent++, q);
    expect(await s.submit(item), isTrue);
    expect(sent, 1);
    expect(await q.all(), isEmpty);
  });

  test('submit ENFILEIRA quando o envio falha', () async {
    final q = _MemQueue();
    final s = TelemetrySender((i) async => throw Exception('rede'), q);
    expect(await s.submit(item), isFalse);
    final pend = await q.all();
    expect(pend.length, 1);
    expect(pend.first.effectiveSeconds, 120);
    expect(pend.first.interruptions, 2);
  });

  test('flush reenvia e limpa quando a rede volta', () async {
    final q = _MemQueue();
    var fail = true;
    final sent = <String>[];
    final s = TelemetrySender((i) async {
      if (fail) throw Exception('rede');
      sent.add(i.sessionId);
    }, q);
    await s.submit(item); // falha → enfileira
    expect((await q.all()).length, 1);
    fail = false;
    await s.flush(); // agora envia
    expect(sent, ['s1']);
    expect(await q.all(), isEmpty);
  });

  test('flush mantém na fila se ainda falha', () async {
    final q = _MemQueue();
    final s = TelemetrySender((i) async => throw Exception('rede'), q);
    await q.add(item);
    await s.flush();
    expect((await q.all()).length, 1);
  });

  test('PendingComplete faz round-trip JSON', () {
    final back = PendingComplete.fromJson(item.toJson());
    expect(back.sessionId, 's1');
    expect(back.effectiveSeconds, 120);
    expect(back.interruptions, 2);
  });
}
