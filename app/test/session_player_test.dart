import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/core/config.dart';
import 'package:sereno/services/session_store.dart';
import 'package:sereno/services/session_repository.dart';
import 'package:sereno/services/audio_bytes_source.dart';
import 'package:sereno/services/audio_player_port.dart';
import 'package:sereno/services/telemetry_queue.dart';
import 'package:sereno/shared/breathing_wave.dart';
import 'package:sereno/features/session/session_player_screen.dart';

/// Player falso: registra chamadas e permite simular o fim natural do áudio.
class _FakePlayer implements AudioPlayerPort {
  bool loaded = false, playing = false, disposed = false;
  int playCalls = 0, pauseCalls = 0;
  AudioBytesSource? lastSource;
  Uint8List? lastBytes;
  final List<double> volumes = [];
  final Completer<void> _done = Completer<void>();

  @override
  Future<void> load(AudioBytesSource source) async {
    loaded = true;
    lastSource = source;
    final bytes = <int>[];
    await for (final bloco in source.read(0, source.length)) {
      bytes.addAll(bloco);
    }
    lastBytes = Uint8List.fromList(bytes);
  }

  @override
  Future<void> loadBytes(Uint8List bytes) => load(MemoryAudioSource(bytes));

  @override
  Future<void> setVolume(double gain) async => volumes.add(gain);

  @override
  Future<void> play() async {
    playing = true;
    playCalls++;
  }

  @override
  Future<void> pause() async {
    playing = false;
    pauseCalls++;
  }

  @override
  Future<void> get onComplete => _done.future;

  @override
  bool get isPlaying => playing;

  @override
  Future<void> dispose() async => disposed = true;
}

/// Repositório falso: evita rede; controla download e falha de complete.
class _FakeRepo extends SessionRepository {
  _FakeRepo() : super(ApiClient(SessionStore()), SessionStore());
  Uint8List audio = Uint8List.fromList(const [82, 73, 70, 70]); // "RIFF"
  bool failComplete = false;
  int completeCalls = 0;
  int? lastEffective;
  int? lastInterruptions;
  int? lastPaused;
  double? lastGainMean;
  double? lastGainPeak;
  int? lastRelaxation;

  @override
  Future<AudioBytesSource> obtainAudio(String sessionId,
          {required String contentHash}) async =>
      MemoryAudioSource(audio, contentType: 'audio/flac');

  @override
  Future<void> complete(String sessionId,
      {required int effectiveSeconds,
      required int interruptions,
      int? pausedSeconds,
      double? gainMean,
      double? gainPeak,
      int? relaxation0to10}) async {
    completeCalls++;
    lastEffective = effectiveSeconds;
    lastInterruptions = interruptions;
    lastPaused = pausedSeconds;
    lastGainMean = gainMean;
    lastGainPeak = gainPeak;
    lastRelaxation = relaxation0to10;
    if (failComplete) throw Exception('rede');
  }
}

class _MemQueue implements TelemetryQueue {
  final Map<String, PendingComplete> _m = {};
  @override
  Future<void> add(PendingComplete item) async => _m[item.sessionId] = item;
  @override
  Future<List<PendingComplete>> all() async => _m.values.toList();
  @override
  Future<void> removeFor(String sessionId) async => _m.remove(sessionId);
}

final _session = SessionStart(sessionId: 's1', protocolHandle: 'delta', contentHash: 'x');

TelemetrySender _senderFor(_FakeRepo repo, TelemetryQueue q) => TelemetrySender(
      (i) => repo.complete(i.sessionId,
          effectiveSeconds: i.effectiveSeconds,
          interruptions: i.interruptions,
          pausedSeconds: i.pausedSeconds,
          gainMean: i.gainMean,
          gainPeak: i.gainPeak,
          relaxation0to10: i.relaxation0to10),
      q,
    );

Widget _screen(_FakeRepo repo, _FakePlayer player, TelemetrySender sender) => MaterialApp(
      home: SessionPlayerScreen(
          repo: repo, session: _session, player: player, telemetry: sender),
    );

/// Deixa o _prepare() assíncrono terminar (download → load → play → setState).
Future<void> _settleLoad(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump();
  }
}

/// Remove a tela para disparar dispose() (cancela timer e libera animações).
Future<void> _teardown(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
}

void main() {
  testWidgets('baixa o áudio e inicia a reprodução', (tester) async {
    final repo = _FakeRepo();
    final player = _FakePlayer();
    await tester.pumpWidget(_screen(repo, player, _senderFor(repo, _MemQueue())));
    expect(find.text('Preparando o áudio…'), findsOneWidget); // estado de carga
    await _settleLoad(tester);
    expect(player.loaded, isTrue);
    expect(player.isPlaying, isTrue);
    expect(find.text('Em sessão'), findsOneWidget);
    // G3: o ganho é TRAVADO antes de tocar, e a tela não oferece controle de volume.
    expect(player.volumes.single, audioGain);
    expect(find.byType(Slider), findsNothing);
    await _teardown(tester);
  });

  testWidgets('a visualização é NÃO reativa ao áudio (só tempo)', (tester) async {
    final repo = _FakeRepo();
    final player = _FakePlayer();
    await tester.pumpWidget(_screen(repo, player, _senderFor(repo, _MemQueue())));
    await _settleLoad(tester);
    // A onda existe e só recebe 'height' — nenhum parâmetro de áudio/amplitude.
    expect(find.byType(BreathingWave), findsOneWidget);
    expect(tester.widget<BreathingWave>(find.byType(BreathingWave)).height, 180);
    await _teardown(tester);
  });

  testWidgets('encerrar chama complete com duração e interrupções corretas',
      (tester) async {
    final repo = _FakeRepo();
    final player = _FakePlayer();
    await tester.pumpWidget(_screen(repo, player, _senderFor(repo, _MemQueue())));
    await _settleLoad(tester);

    await tester.pump(const Duration(seconds: 1)); // efetivo = 1
    await tester.pump(const Duration(seconds: 1)); // efetivo = 2
    await tester.tap(find.byIcon(Icons.pause_rounded)); // interrupção = 1, pausa
    await tester.pump();
    await tester.pump(const Duration(seconds: 1)); // pausado → efetivo continua 2
    await tester.tap(find.byIcon(Icons.play_arrow_rounded)); // retoma
    await tester.pump();
    await tester.pump(const Duration(seconds: 1)); // efetivo = 3

    await tester.tap(find.byIcon(Icons.stop_rounded));
    await tester.pump();
    await tester.pump();

    expect(repo.completeCalls, 1);
    expect(repo.lastEffective, 3);
    expect(repo.lastInterruptions, 1);
    // G10 — o protocolo pede "interrupções E SUA DURAÇÃO": o segundo em pausa foi contado,
    // e não entrou no tempo efetivo.
    expect(repo.lastPaused, 1);
    // Volume médio e máximo do que foi REPRODUZIDO. O ganho é travado, então coincidem com
    // ele — o valor é medido no player, não copiado da constante.
    expect(repo.lastGainMean, closeTo(audioGain, 1e-9));
    expect(repo.lastGainPeak, audioGain);
    expect(player.pauseCalls, greaterThanOrEqualTo(2)); // pausa manual + pausa no encerrar
    await _teardown(tester);
  });

  testWidgets('o item de relaxamento 0–10 é perguntado e complementa o registro',
      (tester) async {
    // O protocolo lista, por sessão, "resposta a um item único de percepção de relaxamento
    // em escala numérica de 0 a 10". Ele é perguntado DEPOIS de a adesão já ter sido
    // enviada — responder não pode ser condição para a sessão contar.
    final repo = _FakeRepo();
    final player = _FakePlayer();
    await tester.pumpWidget(_screen(repo, player, _senderFor(repo, _MemQueue())));
    await _settleLoad(tester);
    await tester.pump(const Duration(seconds: 1));

    await tester.tap(find.byIcon(Icons.stop_rounded));
    await tester.pump();
    await tester.pump();

    // O diálogo tem animação de entrada; a onda de fundo é infinita, então pumpAndSettle
    // aqui nunca terminaria — avança-se o relógio à mão.
    await tester.pump(const Duration(milliseconds: 400));

    expect(repo.completeCalls, 1);
    expect(repo.lastRelaxation, isNull);          // o primeiro envio não espera a resposta
    expect(find.textContaining('Quão relaxado'), findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, '8'));
    await tester.pump();
    await tester.pump();

    expect(repo.completeCalls, 2);                 // complemento, não substituição
    expect(repo.lastRelaxation, 8);
    expect(repo.lastEffective, 1);                 // o resto do registro vai junto de novo
    await _teardown(tester);
  });

  testWidgets('se complete falha ao encerrar, a telemetria vai para a fila',
      (tester) async {
    final repo = _FakeRepo()..failComplete = true;
    final player = _FakePlayer();
    final queue = _MemQueue();
    await tester.pumpWidget(_screen(repo, player, _senderFor(repo, queue)));
    await _settleLoad(tester);

    await tester.pump(const Duration(seconds: 1)); // efetivo = 1
    await tester.tap(find.byIcon(Icons.stop_rounded));
    await tester.pump();
    await tester.pump();

    final pend = await queue.all();
    expect(pend.length, 1);
    expect(pend.first.sessionId, 's1');
    expect(pend.first.effectiveSeconds, 1);
    await _teardown(tester);
  });
}
