import 'dart:typed_data';

import 'audio_bytes_source.dart';

/// Porta de reprodução de áudio: isola o app da biblioteca concreta (just_audio).
///
/// Objetivo: testabilidade (fakes em widget test) e troca de implementação sem tocar
/// na tela. A reprodução é **bit-a-bit** — a porta apenas recebe os bytes já baixados
/// e verificados por hash e os toca, SEM DSP/reamostragem/normalização no cliente
/// (decisão inegociável do estímulo).
abstract class AudioPlayerPort {
  /// Carrega uma fonte de áudio (já conferida bit-a-bit) para reprodução.
  ///
  /// Recebe a FONTE, e não os bytes, porque o estímulo do estudo tem 20 min: o player pede
  /// as faixas de que precisa e a fonte as produz — do cache cifrado em disco, no caso da
  /// sessão (ADR-103), ou da memória, no caso do tom curto da verificação de fones.
  Future<void> load(AudioBytesSource source);

  /// Atalho para áudio curto já em memória (tom da verificação de fones, testes).
  Future<void> loadBytes(Uint8List bytes) => load(MemoryAudioSource(bytes));

  /// Fixa o ganho de reprodução (0..1). O app trava este valor e não expõe controle de
  /// volume ao participante — é o "limite imposto por software" do protocolo (G3).
  Future<void> setVolume(double gain);

  Future<void> play();
  Future<void> pause();

  /// Completa quando a reprodução chega ao fim naturalmente (uma vez).
  Future<void> get onComplete;

  bool get isPlaying;

  Future<void> dispose();
}
