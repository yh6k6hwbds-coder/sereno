import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/services/audio_cache.dart';
import 'package:sereno/services/session_repository.dart';
import 'package:sereno/services/session_store.dart';

/// Biblioteca local do áudio (G1/ADR-103).
///
/// O que precisa ficar provado, porque é o que sustenta a decisão:
///   1. o arquivo guardado **não** está em claro — um participante que abrisse o
///      armazenamento do app não descobre por FFT em que braço está;
///   2. o que volta do cache é **bit-a-bit** o que o servidor mandou, e faixas arbitrárias
///      voltam certas (é assim que o player consome sem carregar tudo na memória);
///   3. entrada adulterada **não é tocada** — é descartada;
///   4. a segunda sessão do mesmo protocolo **não baixa de novo** (`If-None-Match` → 304);
///   5. sem rede, a sessão do dia acontece com o que já está conferido no aparelho.

/// Armazenamento em memória (o flutter_secure_storage usa platform channels).
class _FakeStore extends SessionStore {
  @override
  Future<String?> accessToken() async => 'token';
  @override
  Future<String?> refreshToken() async => null;
  @override
  Future<bool> isAuthenticated() async => true;
}

Uint8List _chave(int semente) =>
    Uint8List.fromList(List<int>.generate(32, (i) => (i * 7 + semente) & 0xff));

AudioCache _cache(Directory dir, {int semente = 1}) => AudioCache(
      directory: () async => dir,
      masterKey: () async => _chave(semente),
    );

/// Corpo com estrutura reconhecível: se vazasse em claro, apareceria no arquivo.
Uint8List _corpo([int n = 200000]) =>
    Uint8List.fromList(List<int>.generate(n, (i) => (i * 31 + 11) & 0xff));

Future<Uint8List> _tudo(Stream<List<int>> s) async {
  final b = <int>[];
  await for (final bloco in s) {
    b.addAll(bloco);
  }
  return Uint8List.fromList(b);
}

void main() {
  late Directory dir;

  setUp(() => dir = Directory.systemTemp.createTempSync('sereno_audio'));
  tearDown(() {
    if (dir.existsSync()) dir.deleteSync(recursive: true);
  });

  test('o que é gravado não fica em claro e volta bit-a-bit', () async {
    final cache = _cache(dir);
    final claro = _corpo();
    final sha = sha256.convert(claro).toString();

    final fonte = await cache.store(
        contentHash: 'h1',
        corpo: Stream.value(claro),
        etag: '"$sha"',
        contentType: 'audio/flac');

    expect(fonte.length, claro.length);
    expect(fonte.contentType, 'audio/flac');
    expect(await _tudo(fonte.read(0, fonte.length)), claro);

    // O arquivo no disco é outro conteúdo: nem o começo do estímulo aparece nele.
    final bruto = File('${dir.path}${Platform.pathSeparator}h1.bin').readAsBytesSync();
    expect(bruto.length, claro.length);
    expect(bruto.sublist(0, 64), isNot(equals(claro.sublist(0, 64))));
  });

  test('faixas arbitrárias voltam exatas (é assim que o player consome)', () async {
    final cache = _cache(dir);
    final claro = _corpo(100000);
    await cache.store(
        contentHash: 'h2',
        corpo: Stream.value(claro),
        etag: null,
        contentType: 'audio/flac');

    final guardado = await cache.lookup('h2');
    expect(guardado, isNotNull);
    final fonte = guardado!.source;
    expect(await _tudo(fonte.read(0, 10)), claro.sublist(0, 10));
    // Faixas que não caem em múltiplos do bloco da cifra (32 bytes) são as que pegam
    // erro de deslocamento no fluxo de chave.
    expect(await _tudo(fonte.read(37, 1301)), claro.sublist(37, 1301));
    expect(await _tudo(fonte.read(claro.length - 5, claro.length)),
        claro.sublist(claro.length - 5));
    expect(await _tudo(fonte.read(claro.length, claro.length + 100)), isEmpty);
  });

  test('ETag divergente: nada é publicado e o app não toca', () async {
    final cache = _cache(dir);
    await expectLater(
      cache.store(
          contentHash: 'h3',
          corpo: Stream.value(_corpo(1000)),
          etag: '"${'0' * 64}"',
          contentType: 'audio/flac'),
      throwsA(isA<AudioIntegrityException>()),
    );
    expect(await cache.lookup('h3'), isNull);
    expect(File('${dir.path}${Platform.pathSeparator}h3.bin').existsSync(), isFalse);
    expect(File('${dir.path}${Platform.pathSeparator}h3.part').existsSync(), isFalse);
  });

  test('entrada adulterada é descartada, não tocada', () async {
    final cache = _cache(dir);
    await cache.store(
        contentHash: 'h4',
        corpo: Stream.value(_corpo(5000)),
        etag: null,
        contentType: 'audio/flac');

    final arquivo = File('${dir.path}${Platform.pathSeparator}h4.bin');
    final bytes = arquivo.readAsBytesSync();
    bytes[10] = bytes[10] ^ 0xff; // um bit trocado basta
    arquivo.writeAsBytesSync(bytes);

    expect(await cache.lookup('h4'), isNull);
    expect(arquivo.existsSync(), isFalse); // e some do disco
  });

  test('outra chave não lê a biblioteca (a chave mora no Keystore)', () async {
    await _cache(dir, semente: 1).store(
        contentHash: 'h5',
        corpo: Stream.value(_corpo(5000)),
        etag: null,
        contentType: 'audio/flac');
    expect(await _cache(dir, semente: 2).lookup('h5'), isNull);
  });

  test('cache vazio devolve nulo', () async {
    expect(await _cache(dir).lookup('inexistente'), isNull);
  });

  // ------------------------------------------------------------------ ponta a ponta
  test('a segunda sessão do mesmo protocolo não rebaixa o áudio', () async {
    final claro = _corpo(50000);
    final etag = '"${sha256.convert(claro).toString()}"';
    var downloads = 0;
    var revalidacoes = 0;

    final mock = MockClient((req) async {
      if (req.headers['If-None-Match'] == etag) {
        revalidacoes++;
        return http.Response.bytes(const [], 304, headers: {'etag': etag});
      }
      downloads++;
      return http.Response.bytes(claro, 200,
          headers: {'etag': etag, 'content-type': 'audio/flac'});
    });

    final store = _FakeStore();
    final repo = SessionRepository(ApiClient(store, client: mock), store,
        audioCache: _cache(dir));

    final primeira = await repo.obtainAudio('s1', contentHash: 'hx');
    expect(await _tudo(primeira.read(0, primeira.length)), claro);
    expect(downloads, 1);

    final segunda = await repo.obtainAudio('s2', contentHash: 'hx');
    expect(await _tudo(segunda.read(0, segunda.length)), claro);
    expect(downloads, 1, reason: 'o corpo não pode trafegar de novo');
    expect(revalidacoes, 1);
  });

  test('artefato trocado no servidor substitui o guardado', () async {
    final velho = _corpo(20000);
    final novo = _corpo(24000);
    final etagNovo = '"${sha256.convert(novo).toString()}"';

    final cache = _cache(dir);
    await cache.store(
        contentHash: 'hy',
        corpo: Stream.value(velho),
        etag: null,
        contentType: 'audio/flac');

    final store = _FakeStore();
    final repo = SessionRepository(
        ApiClient(store,
            client: MockClient((req) async => http.Response.bytes(novo, 200,
                headers: {'etag': etagNovo, 'content-type': 'audio/flac'}))),
        store,
        audioCache: cache);

    final fonte = await repo.obtainAudio('s3', contentHash: 'hy');
    expect(await _tudo(fonte.read(0, fonte.length)), novo);
    expect((await cache.lookup('hy'))!.etag, etagNovo.replaceAll('"', ''));
  });

  test('sem rede, a sessão acontece com o que já está conferido', () async {
    final claro = _corpo(30000);
    final cache = _cache(dir);
    await cache.store(
        contentHash: 'hz',
        corpo: Stream.value(claro),
        etag: null,
        contentType: 'audio/flac');

    final store = _FakeStore();
    final semRede =
        MockClient((req) async => throw http.ClientException('rede indisponível'));
    final repo =
        SessionRepository(ApiClient(store, client: semRede), store, audioCache: cache);

    final fonte = await repo.obtainAudio('s4', contentHash: 'hz');
    expect(await _tudo(fonte.read(0, fonte.length)), claro);

    // ...mas sem cache o erro sobe: não há o que tocar, e fingir seria pior.
    await expectLater(repo.obtainAudio('s5', contentHash: 'nao-tenho'), throwsA(anything));
  });

  test('a biblioteca inteira sai no logout', () async {
    final cache = _cache(dir);
    await cache.store(
        contentHash: 'hw',
        corpo: Stream.value(_corpo(1000)),
        etag: null,
        contentType: 'audio/flac');
    await cache.clear();
    expect(dir.existsSync(), isFalse);
    expect(await cache.lookup('hw'), isNull);
  });

  test('o problem+json do servidor continua virando ApiException', () async {
    final store = _FakeStore();
    final mock = MockClient((req) async => http.Response(
        jsonEncode({'title': 'Sessão não encontrada', 'detail': 'inexistente'}), 404,
        headers: {'content-type': 'application/problem+json'}));
    final repo =
        SessionRepository(ApiClient(store, client: mock), store, audioCache: _cache(dir));
    await expectLater(
        repo.obtainAudio('s6', contentHash: 'hq'), throwsA(isA<ApiException>()));
  });
}
