import 'dart:math' as math;
import 'dart:typed_data';

/// Sinal de teste da verificação DICÓTICA de fones (G4).
///
/// Gera, em memória, um WAV PCM 16 bits estéreo com um tom em **uma só orelha** e silêncio
/// na outra. O participante diz em qual lado ouviu; errar não libera a sessão. É assim que
/// se verifica a condição dicótica de que o fenômeno binaural depende — a caixa de seleção
/// anterior era declaração, não verificação.
///
/// Por que gerar aqui, e não baixar do servidor:
///   * o teste acontece **antes** de existir sessão (e o app é offline-first);
///   * o sinal é o mesmo nos dois braços e **não carrega informação de condição** — não é o
///     estímulo, então a regra de reprodução bit-a-bit sem DSP (que vale para o estímulo)
///     não é afetada: o estímulo continua vindo pronto do servidor;
///   * evita empacotar um par de arquivos como asset para algo que são vinte linhas de seno.
class HeadphoneTestTone {
  static const int sampleRate = 44100;
  static const double frequencyHz = 440.0;   // fora da faixa do estímulo (250/253 Hz)
  static const double durationS = 1.2;
  static const double fadeS = 0.05;          // evita clique no início/fim
  static const double peakDbfs = -12.0;      // mesmo teto digital do estímulo

  /// WAV com o tom apenas na orelha [left] ? esquerda : direita.
  static Uint8List forEar({required bool left}) {
    final n = (durationS * sampleRate).round();
    final fadeN = (fadeS * sampleRate).round();
    final amp = math.pow(10.0, peakDbfs / 20.0) as double;

    final data = ByteData(n * 4); // 2 canais x 2 bytes
    for (var i = 0; i < n; i++) {
      var env = 1.0;
      if (i < fadeN) {
        env = 0.5 * (1 - math.cos(math.pi * i / (fadeN - 1)));
      } else if (i >= n - fadeN) {
        env = 0.5 * (1 - math.cos(math.pi * (n - 1 - i) / (fadeN - 1)));
      }
      final s = amp * env * math.sin(2 * math.pi * frequencyHz * i / sampleRate);
      final v = (s * 32767).round().clamp(-32768, 32767).toInt();
      data.setInt16(i * 4, left ? v : 0, Endian.little);       // canal L
      data.setInt16(i * 4 + 2, left ? 0 : v, Endian.little);   // canal R
    }
    return _wrapWav(data.buffer.asUint8List());
  }

  /// Cabeçalho WAV canônico (44 bytes) + amostras.
  static Uint8List _wrapWav(Uint8List pcm) {
    const channels = 2, bits = 16;
    final byteRate = sampleRate * channels * bits ~/ 8;
    final header = ByteData(44);
    void ascii(int offset, String s) {
      for (var i = 0; i < s.length; i++) {
        header.setUint8(offset + i, s.codeUnitAt(i));
      }
    }

    ascii(0, 'RIFF');
    header.setUint32(4, 36 + pcm.length, Endian.little);
    ascii(8, 'WAVE');
    ascii(12, 'fmt ');
    header.setUint32(16, 16, Endian.little);          // tamanho do bloco fmt
    header.setUint16(20, 1, Endian.little);           // PCM
    header.setUint16(22, channels, Endian.little);
    header.setUint32(24, sampleRate, Endian.little);
    header.setUint32(28, byteRate, Endian.little);
    header.setUint16(32, channels * bits ~/ 8, Endian.little);
    header.setUint16(34, bits, Endian.little);
    ascii(36, 'data');
    header.setUint32(40, pcm.length, Endian.little);

    final out = Uint8List(44 + pcm.length);
    out.setRange(0, 44, header.buffer.asUint8List());
    out.setRange(44, out.length, pcm);
    return out;
  }
}
