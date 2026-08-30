import 'dart:async';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/core/config.dart';
import 'package:sereno/features/session/headphone_check_screen.dart';
import 'package:sereno/features/session/headphone_test_tone.dart';
import 'package:sereno/services/audio_bytes_source.dart';
import 'package:sereno/services/audio_player_port.dart';
import 'package:sereno/services/session_repository.dart';
import 'package:sereno/services/session_store.dart';

/// Verificação DICÓTICA de fones (G4) e ganho travado (G3).
///
/// O que precisa ficar provado: a sessão **não** começa sem passar no teste, errar reinicia
/// o teste, e o que se envia ao servidor descreve a tentativa aceita (sem erro), com o ganho
/// que o app realmente usa.

/// Player falso: registra os bytes tocados e o volume pedido.
class _FakePlayer implements AudioPlayerPort {
  final List<Uint8List> played = [];
  final List<double> volumes = [];
  int playCalls = 0, pauseCalls = 0;
  final Completer<void> _done = Completer<void>();

  @override
  Future<void> load(AudioBytesSource source) async {
    final bytes = <int>[];
    await for (final bloco in source.read(0, source.length)) {
      bytes.addAll(bloco);
    }
    played.add(Uint8List.fromList(bytes));
  }

  @override
  Future<void> loadBytes(Uint8List bytes) => load(MemoryAudioSource(bytes));
  @override
  Future<void> setVolume(double gain) async => volumes.add(gain);
  @override
  Future<void> play() async => playCalls++;
  @override
  Future<void> pause() async => pauseCalls++;
  @override
  Future<void> get onComplete => _done.future;
  @override
  bool get isPlaying => false;
  @override
  Future<void> dispose() async {}
}

/// Repositório falso: guarda o que foi enviado no início da sessão.
class _FakeRepo extends SessionRepository {
  _FakeRepo() : super(ApiClient(SessionStore()), SessionStore());
  HeadphoneCheckResult? lastCheck;
  double? lastGain;
  int startCalls = 0;

  @override
  Future<SessionStart> start({
    required String protocolHandle,
    required HeadphoneCheckResult headphoneCheck,
    required double audioGain,
  }) {
    startCalls++;
    lastCheck = headphoneCheck;
    lastGain = audioGain;
    // Fica pendente de propósito: a tela não navega para o player real (que abriria áudio e
    // rede) e o teste não herda SnackBar/animação em curso. O que interessa — o que foi
    // enviado — já está registrado acima, antes de qualquer await.
    return Completer<SessionStart>().future;
  }
}

/// Sorteio determinístico: devolve os lados na ordem pedida.
class _FakeRandom implements Random {
  final List<bool> lados;
  int _i = 0;
  _FakeRandom(this.lados);
  @override
  bool nextBool() => lados[_i++ % lados.length];
  @override
  double nextDouble() => 0.0;
  @override
  int nextInt(int max) => 0;
}

Future<void> _pump(WidgetTester t, Widget child) async {
  await t.pumpWidget(MaterialApp(home: child));
  await t.pump();
}

void main() {
  testWidgets('sem passar no teste não há botão de iniciar sessão', (t) async {
    await _pump(t, HeadphoneCheckScreen(
        repo: _FakeRepo(), player: _FakePlayer(), random: _FakeRandom(const [true, true])));

    expect(find.text('Iniciar sessão'), findsNothing);
    expect(find.text('Tocar o sinal'), findsOneWidget);
    // As respostas só aparecem depois que o sinal toca.
    expect(find.text('Esquerda'), findsNothing);
  });

  testWidgets('duas respostas certas liberam a sessão e enviam a evidência', (t) async {
    final repo = _FakeRepo();
    final player = _FakePlayer();
    await _pump(t, HeadphoneCheckScreen(
        repo: repo, player: player, random: _FakeRandom(const [true, false])));

    // Rodada 1: sinal na esquerda.
    await t.tap(find.text('Tocar o sinal'));
    await t.pump();
    expect(player.played.length, 1);
    expect(player.volumes.single, audioGain);      // ganho travado (G3)
    await t.tap(find.text('Esquerda'));
    await t.pump();
    expect(find.text('Iniciar sessão'), findsNothing);   // falta uma rodada

    // Rodada 2: sinal na direita.
    await t.tap(find.text('Tocar o próximo sinal'));
    await t.pump();
    await t.tap(find.text('Direita'));
    await t.pump();

    expect(find.text('Iniciar sessão'), findsOneWidget);
    await t.tap(find.text('Iniciar sessão'));
    await t.pump();

    expect(repo.startCalls, 1);
    expect(repo.lastGain, audioGain);
    final json = repo.lastCheck!.toJson();
    expect(json['rounds'], HeadphoneCheckScreen.kRounds);
    expect(json['errors'], 0);
    expect(json['attempts'], 1);
    expect(json['ears'], 'LR');
  });

  testWidgets('errar reinicia o teste e não inicia sessão', (t) async {
    final repo = _FakeRepo();
    await _pump(t, HeadphoneCheckScreen(
        repo: repo, player: _FakePlayer(), random: _FakeRandom(const [true, true, false])));

    await t.tap(find.text('Tocar o sinal'));
    await t.pump();
    await t.tap(find.text('Direita'));          // errado: o sinal estava na esquerda
    await t.pump();

    expect(find.text('Iniciar sessão'), findsNothing);
    expect(find.textContaining('soou na outra orelha'), findsOneWidget);
    expect(find.textContaining('Etapa 0 de 2'), findsOneWidget);   // voltou ao início
    expect(repo.startCalls, 0);

    // Refazendo do zero: duas certas liberam, e o envio registra a 2ª tentativa.
    await t.tap(find.text('Tocar o próximo sinal'));
    await t.pump();
    await t.tap(find.text('Esquerda'));
    await t.pump();
    await t.tap(find.text('Tocar o próximo sinal'));
    await t.pump();
    await t.tap(find.text('Direita'));
    await t.pump();
    await t.tap(find.text('Iniciar sessão'));
    await t.pump();

    final json = repo.lastCheck!.toJson();
    expect(json['errors'], 0);        // a tentativa ACEITA não tem erro
    expect(json['attempts'], 2);      // mas a auditoria sabe que foi preciso refazer
    expect(json['ears'], 'LR');
  });

  testWidgets('o sinal de teste sai em uma orelha só', (t) async {
    // Prova a condição dicótica no próprio sinal: um canal com energia, o outro em silêncio.
    for (final left in [true, false]) {
      final wav = HeadphoneTestTone.forEar(left: left);
      final pcm = wav.buffer.asByteData(44);          // pula o cabeçalho
      var somaL = 0, somaR = 0;
      for (var i = 0; i < 2000; i++) {
        somaL += pcm.getInt16(i * 4, Endian.little).abs();
        somaR += pcm.getInt16(i * 4 + 2, Endian.little).abs();
      }
      expect(left ? somaR : somaL, 0);                // orelha silenciosa
      expect(left ? somaL : somaR, greaterThan(0));   // orelha com o sinal
    }
  });
}
