import 'dart:math';
import 'dart:typed_data';

/// Fonte dos bytes de áudio entregues ao player, **por faixa e em fluxo**.
///
/// Existe porque a sessão do estudo tem 20 minutos: em PCM cru são 230 MB e, mesmo em
/// FLAC (ADR-103), dezenas de megabytes. Entregar um `Uint8List` pronto obrigaria o app
/// a segurar o arquivo inteiro na memória; aqui o player pede o pedaço de que precisa e
/// a fonte o produz — do cache cifrado em disco ou da memória, conforme a implementação.
///
/// A fonte é **opaca quanto ao braço**: ela move bytes e não sabe (nem pode saber) se o
/// que carrega é ativo ou controle.
abstract class AudioBytesSource {
  /// Tamanho total do arquivo, em bytes.
  int get length;

  /// Tipo do conteúdo, como declarado pelo servidor (`audio/flac` ou `audio/wav`).
  String get contentType;

  /// Bytes de [start] (inclusive) a [end] (exclusive), em blocos.
  Stream<List<int>> read(int start, int end);

  Future<void> dispose();
}

/// Fonte em memória — para áudios curtos gerados no próprio aparelho (o tom da
/// verificação de fones) e para testes.
class MemoryAudioSource implements AudioBytesSource {
  final Uint8List bytes;
  @override
  final String contentType;
  static const int _bloco = 64 * 1024;

  MemoryAudioSource(this.bytes, {this.contentType = 'audio/wav'});

  @override
  int get length => bytes.length;

  @override
  Stream<List<int>> read(int start, int end) async* {
    final fim = min(end, bytes.length);
    for (var pos = start; pos < fim; pos += _bloco) {
      yield bytes.sublist(pos, min(pos + _bloco, fim));
    }
  }

  @override
  Future<void> dispose() async {}
}
