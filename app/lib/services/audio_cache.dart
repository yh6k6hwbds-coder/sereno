import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import 'audio_bytes_source.dart';

/// Biblioteca local do áudio da sessão — **cifrada em repouso**.
///
/// Por que existe (G1/ADR-103): o participante faz 20 sessões com o MESMO arquivo. Baixá-lo
/// a cada sessão custaria centenas de megabytes de rede móvel a alguém que aceitou colaborar
/// com uma pesquisa; o piloto não sobreviveria a isso. Guardar o arquivo, porém, esbarra na
/// razão pela qual o ADR-054 tinha decidido NÃO guardar: um arquivo em claro no aparelho é
/// uma rota de **desmascaramento** — bastaria uma FFT para o participante descobrir se está
/// no braço ativo (delta-f = 3 Hz) ou no controle (delta-f = 0), e o cegamento é inegociável.
///
/// A saída é guardar **cifrado**, com chave que vive no Keystore/Keychain e nunca no arquivo:
///
///   * **Confidencialidade** — cifra de fluxo em modo contador sobre HMAC-SHA256
///     ([_Keystream]). Não é AES por uma razão prática: o app já depende de `crypto` (SHA-256
///     para a conferência bit-a-bit) e não de uma biblioteca de cifra de bloco; a construção
///     contador+PRF é a mesma ideia do CTR, com o HMAC no lugar do AES. É acessável por
///     deslocamento, que é o que permite ao player pedir faixas sem decifrar o arquivo todo.
///   * **Integridade** — cifra-então-autentica: um HMAC sobre o criptograma fecha a entrada.
///     Conferir o selo custa uma passada de SHA-256 (barata) em vez de decifrar tudo.
///   * **Fidelidade bit-a-bit** — o sha256 do texto claro é conferido contra o `ETag` do
///     servidor **enquanto o download acontece**, e volta ao servidor como `If-None-Match`
///     na sessão seguinte: se o artefato mudou, o app rebaixa em vez de tocar o antigo.
///
/// O que isto NÃO promete: resistir a quem tem escrita no armazenamento privado do app E
/// leitura do Keystore (aí o aparelho já está comprometido). O alvo é o participante curioso
/// e a corrupção acidental — não um adversário com o aparelho na mão.
class AudioCache {
  /// Diretório privado do app onde as entradas vivem (resolvido sob demanda).
  final Future<Directory> Function() directory;

  /// Chave mestra de 32 bytes, vinda do armazenamento seguro do sistema.
  final Future<Uint8List> Function() masterKey;

  static const int versaoEntrada = 1;
  static const int blocoLeitura = 256 * 1024;

  AudioCache({required this.directory, required this.masterKey});

  Future<File> _arquivo(String contentHash, String ext) async =>
      File('${(await directory()).path}${Platform.pathSeparator}$contentHash.$ext');

  /// Entrada guardada para [contentHash], **já conferida**, ou `null` se não houver
  /// (ou se o selo não bater — nesse caso a entrada é descartada).
  Future<CachedAudio?> lookup(String contentHash) async {
    final meta = await _arquivo(contentHash, 'json');
    final dados = await _arquivo(contentHash, 'bin');
    if (!await meta.exists() || !await dados.exists()) return null;
    try {
      final m = jsonDecode(await meta.readAsString()) as Map<String, dynamic>;
      if ((m['v'] as num).toInt() != versaoEntrada) {
        throw const FormatException('versão de entrada desconhecida');
      }
      final nonce = base64Decode(m['nonce'] as String);
      final selo = base64Decode(m['tag'] as String);
      final claroSha = m['plain_sha'] as String;
      final tamanho = (m['length'] as num).toInt();
      if (await dados.length() != tamanho) {
        throw const FormatException('tamanho divergente');
      }

      final chaves = await _chaves();
      final calculado = await _selo(chaves.mac, nonce, claroSha, dados);
      if (!_igual(calculado, selo)) throw const FormatException('selo inválido');

      return CachedAudio(
        etag: claroSha,
        source: EncryptedFileSource(
          file: dados,
          keystream: _Keystream(chaves.cifra, nonce),
          length: tamanho,
          contentType: m['content_type'] as String,
        ),
      );
    } catch (_) {
      await evict(contentHash); // entrada ilegível/adulterada não é usada nem mantida
      return null;
    }
  }

  /// Consome [corpo] (o fluxo da resposta), grava cifrado e devolve a fonte pronta.
  ///
  /// O sha256 do texto claro é calculado **durante** a escrita e conferido contra [etag]:
  /// divergiu, nada é publicado e a exceção sobe — o app não toca um estímulo que não é
  /// bit-a-bit o que o servidor mandou.
  Future<AudioBytesSource> store({
    required String contentHash,
    required Stream<List<int>> corpo,
    required String? etag,
    required String contentType,
  }) async {
    final dir = await directory();
    await dir.create(recursive: true);
    final parcial = await _arquivo(contentHash, 'part');
    final dados = await _arquivo(contentHash, 'bin');
    final meta = await _arquivo(contentHash, 'json');
    if (await meta.exists()) await meta.delete(); // entrada velha deixa de valer agora

    final chaves = await _chaves();
    final nonce = _nonce();
    final keystream = _Keystream(chaves.cifra, nonce);

    final acumulador = _DigestSink();
    final claro = sha256.startChunkedConversion(acumulador);
    final saida = parcial.openWrite();
    var total = 0;
    try {
      await for (final bloco in corpo) {
        claro.add(bloco);
        saida.add(keystream.apply(bloco, total));
        total += bloco.length;
      }
      await saida.flush();
    } finally {
      await saida.close();
    }
    claro.close();
    final claroSha = acumulador.value.toString();

    final esperado = etag?.replaceAll('"', '');
    if (esperado != null && esperado.isNotEmpty && esperado != claroSha) {
      await parcial.delete();
      throw AudioIntegrityException(
          'Falha de integridade do áudio (hash divergente do ETag).');
    }

    // O antigo sai antes: renomear sobre um arquivo existente falha em alguns sistemas.
    if (await dados.exists()) await dados.delete();
    await parcial.rename(dados.path);
    final selo = await _selo(chaves.mac, nonce, claroSha, dados);
    // O JSON entra por último: sua existência é o sinal de entrada completa e selada.
    await meta.writeAsString(jsonEncode({
      'v': versaoEntrada,
      'plain_sha': claroSha,
      'length': total,
      'content_type': contentType,
      'nonce': base64Encode(nonce),
      'tag': base64Encode(selo),
    }));

    return EncryptedFileSource(
      file: dados,
      keystream: keystream,
      length: total,
      contentType: contentType,
    );
  }

  /// Remove a entrada (usado quando ela não confere e no descarte de dados do estudo).
  Future<void> evict(String contentHash) async {
    for (final ext in const ['bin', 'json', 'part']) {
      final f = await _arquivo(contentHash, ext);
      if (await f.exists()) await f.delete();
    }
  }

  /// Apaga a biblioteca inteira (logout e retirada de consentimento).
  Future<void> clear() async {
    final dir = await directory();
    if (await dir.exists()) await dir.delete(recursive: true);
  }

  // --- interno -------------------------------------------------------------

  Future<_Chaves> _chaves() async {
    final mestra = await masterKey();
    // Separação de domínio: a chave que cifra nunca é a que autentica.
    return _Chaves(
      cifra: Uint8List.fromList(
          Hmac(sha256, mestra).convert(utf8.encode('sereno/audio/enc')).bytes),
      mac: Uint8List.fromList(
          Hmac(sha256, mestra).convert(utf8.encode('sereno/audio/mac')).bytes),
    );
  }

  /// Selo sobre o CRIPTOGRAMA (cifra-então-autentica), amarrando nonce e hash do claro.
  Future<Uint8List> _selo(
      Uint8List chaveMac, Uint8List nonce, String claroSha, File dados) async {
    final acumulador = _DigestSink();
    final entrada = Hmac(sha256, chaveMac).startChunkedConversion(acumulador);
    entrada.add(nonce);
    entrada.add(utf8.encode(claroSha));
    await for (final bloco in dados.openRead()) {
      entrada.add(bloco);
    }
    entrada.close();
    return Uint8List.fromList(acumulador.value.bytes);
  }

  Uint8List _nonce() {
    final r = Random.secure();
    return Uint8List.fromList(List<int>.generate(16, (_) => r.nextInt(256)));
  }

  static bool _igual(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    var d = 0;
    for (var i = 0; i < a.length; i++) {
      d |= a[i] ^ b[i]; // tempo constante: não vaza onde está a diferença
    }
    return d == 0;
  }
}

class _Chaves {
  final Uint8List cifra;
  final Uint8List mac;
  _Chaves({required this.cifra, required this.mac});
}

/// Entrada do cache já conferida: a fonte pronta e o `ETag` que a identifica no servidor.
class CachedAudio {
  final String etag;
  final AudioBytesSource source;
  CachedAudio({required this.etag, required this.source});

  Future<void> dispose() => source.dispose();
}

/// O áudio recebido não corresponde ao que o servidor declarou (ETag): a reprodução
/// bit-a-bit é inegociável, então recusamos tocar.
class AudioIntegrityException implements Exception {
  final String message;
  AudioIntegrityException(this.message);
  @override
  String toString() => message;
}

/// Fluxo de chave em modo contador sobre HMAC-SHA256.
///
/// Bloco `i` = HMAC(chave, nonce + i em 8 bytes big-endian); o texto é o XOR com esse
/// fluxo. Como o bloco é função só do índice, decifrar a partir de um deslocamento
/// qualquer custa o mesmo — é isso que deixa o player pedir faixas.
class _Keystream {
  static const int _bloco = 32; // saída do SHA-256
  final Hmac _hmac;
  final Uint8List _nonce;

  _Keystream(Uint8List chave, Uint8List nonce)
      : _hmac = Hmac(sha256, chave),
        _nonce = nonce;

  Uint8List apply(List<int> dados, int offset) {
    final saida = Uint8List(dados.length);
    var indice = offset ~/ _bloco;
    var pos = offset % _bloco;
    var chave = _hmac.convert(_contador(indice)).bytes;
    for (var i = 0; i < dados.length; i++) {
      if (pos == _bloco) {
        indice++;
        chave = _hmac.convert(_contador(indice)).bytes;
        pos = 0;
      }
      saida[i] = dados[i] ^ chave[pos++];
    }
    return saida;
  }

  Uint8List _contador(int indice) {
    final b = Uint8List(_nonce.length + 8);
    b.setRange(0, _nonce.length, _nonce);
    var v = indice;
    for (var i = 7; i >= 0; i--) {
      b[_nonce.length + i] = v & 0xff;
      v >>= 8;
    }
    return b;
  }
}

/// Fonte que lê o arquivo cifrado do disco e decifra **só a faixa pedida**.
class EncryptedFileSource implements AudioBytesSource {
  final File file;
  final _Keystream keystream;
  @override
  final int length;
  @override
  final String contentType;

  EncryptedFileSource({
    required this.file,
    required this.keystream,
    required this.length,
    required this.contentType,
  });

  @override
  Stream<List<int>> read(int start, int end) async* {
    final fim = min(end, length);
    if (start >= fim) return;
    final raf = await file.open();
    try {
      await raf.setPosition(start);
      var pos = start;
      while (pos < fim) {
        final pedaco = await raf.read(min(AudioCache.blocoLeitura, fim - pos));
        if (pedaco.isEmpty) return;
        yield keystream.apply(pedaco, pos);
        pos += pedaco.length;
      }
    } finally {
      await raf.close();
    }
  }

  @override
  Future<void> dispose() async {}
}

/// Coletor do digest para hashing incremental (evita ler o arquivo inteiro na memória).
class _DigestSink implements Sink<Digest> {
  late Digest value;
  @override
  void add(Digest data) => value = data;
  @override
  void close() {}
}
