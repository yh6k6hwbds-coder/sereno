import 'dart:typed_data';

/// Porta de reprodução de áudio: isola o app da biblioteca concreta (just_audio).
///
/// Objetivo: testabilidade (fakes em widget test) e troca de implementação sem tocar
/// na tela. A reprodução é **bit-a-bit** — a porta apenas recebe os bytes já baixados
/// e verificados por hash e os toca, SEM DSP/reamostragem/normalização no cliente
/// (decisão inegociável do estímulo).
abstract class AudioPlayerPort {
  /// Carrega os bytes do WAV (já verificados por sha256) para reprodução.
  Future<void> loadBytes(Uint8List bytes);

  Future<void> play();
  Future<void> pause();

  /// Completa quando a reprodução chega ao fim naturalmente (uma vez).
  Future<void> get onComplete;

  bool get isPlaying;

  Future<void> dispose();
}
