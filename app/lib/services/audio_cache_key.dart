import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path_provider/path_provider.dart';

import 'audio_cache.dart';

/// Chave mestra da biblioteca de áudio cifrada, no Keychain/Keystore.
///
/// Fica separada do [AudioCache] porque é um canal de plataforma: os testes injetam
/// uma chave fixa e um diretório temporário, sem precisar de aparelho. É sorteada na
/// primeira vez e nunca sai do armazenamento seguro — apagá-la (logout) torna as
/// entradas do cache ilegíveis, que é exatamente o efeito desejado.
class AudioCacheKey {
  static const _chave = 'sereno.audio.key';
  final FlutterSecureStorage _s = const FlutterSecureStorage();

  Future<Uint8List> obtain() async {
    final guardada = await _s.read(key: _chave);
    if (guardada != null && guardada.isNotEmpty) {
      final bytes = base64Decode(guardada);
      if (bytes.length == 32) return bytes;
    }
    final r = Random.secure();
    final nova = Uint8List.fromList(List<int>.generate(32, (_) => r.nextInt(256)));
    await _s.write(key: _chave, value: base64Encode(nova));
    return nova;
  }

  Future<void> forget() => _s.delete(key: _chave);
}

/// Cache de áudio pronto para o aparelho: diretório privado do app + chave do Keystore.
AudioCache productionAudioCache() {
  final chaves = AudioCacheKey();
  return AudioCache(
    directory: () async {
      final base = await getApplicationSupportDirectory();
      return Directory('${base.path}${Platform.pathSeparator}audio');
    },
    masterKey: chaves.obtain,
  );
}
