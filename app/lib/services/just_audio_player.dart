import 'dart:async';
import 'dart:typed_data';
import 'package:just_audio/just_audio.dart';

import 'audio_player_port.dart';

/// Implementação de [AudioPlayerPort] com just_audio. Reproduz os bytes do WAV como
/// fonte em memória, SEM transcodificação/reamostragem/DSP — fidelidade bit-a-bit.
/// Usada apenas em dispositivo (os widget tests injetam um fake).
class JustAudioPlayer implements AudioPlayerPort {
  final AudioPlayer _player = AudioPlayer();
  final Completer<void> _done = Completer<void>();

  JustAudioPlayer() {
    _player.playerStateStream.listen((s) {
      if (s.processingState == ProcessingState.completed && !_done.isCompleted) {
        _done.complete();
      }
    });
  }

  @override
  Future<void> loadBytes(Uint8List bytes) =>
      _player.setAudioSource(_BytesAudioSource(bytes));

  @override
  Future<void> play() => _player.play();

  @override
  Future<void> pause() => _player.pause();

  @override
  Future<void> get onComplete => _done.future;

  @override
  bool get isPlaying => _player.playing;

  @override
  Future<void> dispose() => _player.dispose();
}

/// Fonte de áudio a partir de bytes em memória (suporta Range; bit-a-bit).
class _BytesAudioSource extends StreamAudioSource {
  final Uint8List _bytes;
  _BytesAudioSource(this._bytes);

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    start ??= 0;
    end ??= _bytes.length;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: end - start,
      offset: start,
      stream: Stream.value(_bytes.sublist(start, end)),
      contentType: 'audio/wav',
    );
  }
}
