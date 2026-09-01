import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/l10n/app_localizations.dart';
import 'package:sereno/features/home/home_screen.dart';
import 'package:sereno/services/progress_repository.dart';
import 'package:sereno/services/session_store.dart';

/// H5/ADR-114 — a sessão NÃO abre no navegador, e o motivo é fidelidade.
///
/// A reprodução bit-a-bit é decisão inegociável do estímulo (#3) e foi verificada na pilha
/// NATIVA: o ExoPlayer decodifica o FLAC e devolve o mesmo PCM do WAV. Na web o áudio passa
/// pela pilha do navegador — que reamostra para a taxa do `AudioContext` e pode aplicar
/// ganho próprio — e **esse caminho nunca foi validado**. Deixar a sessão rodar ali seria
/// coletar dado de um estímulo que o estudo não consegue afirmar qual é.
///
/// `isWeb` é injetado porque `kIsWeb` é `const` e o widget test não roda em web. Sem a
/// injeção, a trava seria código que nenhum teste alcança — e trava que ninguém testa é
/// trava que desaparece na primeira refatoração.
///
/// A Home monta o MaterialApp com os delegates `Global*`: sem eles, AppBar e ListTile
/// estouram em pt-BR (armadilha que já custou um CI vermelho no ADR-102).

class _FakeProgress extends ProgressRepository {
  final ProtocolProgress _resposta;
  _FakeProgress(this._resposta) : super(ApiClient(SessionStore()));

  @override
  Future<ProtocolProgress> myProgress() async => _resposta;
}

ProtocolProgress _andamento({String status = 'active', String? reason}) => ProtocolProgress(
      status: status,
      allocated: true,
      studyWeek: 2,
      sessionsCompleted: 9,
      sessionsPrescribed: 20,
      t2Due: false,
      t2Late: false,
      discontinuedReason: reason,
    );

Widget _app(Widget home) => MaterialApp(
      locale: const Locale('pt'),
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

void main() {
  testWidgets('no navegador, a Home não oferece sessão — e explica por quê', (t) async {
    await t.pumpWidget(_app(
        HomeScreen(progressRepo: _FakeProgress(_andamento()), isWeb: true)));
    await t.pumpAndSettle();

    expect(find.text('Iniciar sessão'), findsNothing);
    expect(find.text('As sessões rodam no aplicativo'), findsOneWidget);
    // A explicação é do PARTICIPANTE: nada de "bit-a-bit" nem de `AudioContext` na tela.
    expect(find.textContaining('exatamente como foi preparado'), findsOneWidget);
    expect(find.textContaining('A equipe do estudo entrega'), findsOneWidget);
  });

  testWidgets('no app instalado, nada muda — a sessão continua sendo o CTA', (t) async {
    await t.pumpWidget(_app(
        HomeScreen(progressRepo: _FakeProgress(_andamento()), isWeb: false)));
    await t.pumpAndSettle();

    expect(find.text('Iniciar sessão'), findsOneWidget);
    expect(find.text('As sessões rodam no aplicativo'), findsNothing);
  });

  testWidgets('no navegador, o RESTO do estudo continua acessível', (t) async {
    // A trava é da sessão, não do app: diário e questionários não dependem da fidelidade
    // do áudio, e travá-los faria o participante perder coleta por um motivo que não existe.
    await t.pumpWidget(_app(
        HomeScreen(progressRepo: _FakeProgress(_andamento()), isWeb: true)));
    await t.pumpAndSettle();

    // O aviso de escopo fica FORA da lista que rola — está sempre visível.
    expect(find.textContaining('Não substitui'), findsOneWidget);
    expect(find.text('Linha de base'), findsOneWidget);

    // A Home rola e a ListView é preguiçosa: os últimos atalhos só existem depois de
    // chegarem à viewport. O cartão novo empurra a lista para baixo, então procurar por
    // eles sem rolar seria um teste que passa ou falha conforme a altura do texto.
    await t.scrollUntilVisible(find.text('Relatar um problema'), 200,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('Relatar um problema'), findsOneWidget);
  });

  testWidgets('descontinuado no navegador: uma explicação só, e é a que importa', (t) async {
    // Quem saiu do protocolo não deve receber, por cima, uma instrução para instalar o app:
    // seriam dois cartões dizendo "não há sessão" por motivos diferentes, e o relevante
    // para essa pessoa é o primeiro.
    await t.pumpWidget(_app(HomeScreen(
        progressRepo: _FakeProgress(
            _andamento(status: 'discontinued', reason: 'adesao_insuficiente')),
        isWeb: true)));
    await t.pumpAndSettle();

    expect(find.text('Sua participação foi descontinuada'), findsOneWidget);
    expect(find.text('As sessões rodam no aplicativo'), findsNothing);
    expect(find.text('Iniciar sessão'), findsNothing);
  });
}
