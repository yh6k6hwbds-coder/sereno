import 'dart:async';
import 'package:just_audio/just_audio.dart';

import 'audio_bytes_source.dart';
import 'audio_player_port.dart';

/// Implementação de [AudioPlayerPort] com just_audio. Toca o que a fonte entrega, SEM
/// transcodificação/reamostragem/DSP — fidelidade bit-a-bit. O FLAC é decodificado pelo
/// próprio sistema (ExoPlayer/AVFoundation) e devolve o MESMO PCM do WAV (ADR-103).
/// Usada apenas em dispositivo (os widget tests injetam um fake).
// `extends` (e não `implements`): assim herda o atalho `loadBytes`, que a porta já
// define em termos de `load`.
class JustAudioPlayer extends AudioPlayerPort {
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
  Future<void> load(AudioBytesSource source) =>
      _player.setAudioSource(_PortAudioSource(source));

  @override
  Future<void> setVolume(double gain) =>
      _player.setVolume(gain.clamp(0.0, 1.0).toDouble());

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

/// Adapta a porta [AudioBytesSource] ao contrato de fonte do just_audio.
///
/// O just_audio pede faixas (`start`/`end`) conforme decodifica; repassamos o pedido
/// como FLUXO, então nem o player nem nós materializamos o arquivo inteiro.
class _PortAudioSource extends StreamAudioSource {
  final AudioBytesSource _fonte;
  _PortAudioSource(this._fonte);

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    start ??= 0;
    end ??= _fonte.length;
    return StreamAudioResponse(
      sourceLength: _fonte.length,
      contentLength: end - start,
      offset: start,
      stream: _fonte.read(start, end),
      contentType: _fonte.contentType,
    );
  }
}
