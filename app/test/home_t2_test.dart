import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/l10n/app_localizations.dart';
import 'package:sereno/features/home/home_screen.dart';
import 'package:sereno/services/progress_repository.dart';
import 'package:sereno/services/session_store.dart';

/// G6 — o convite à avaliação intermediária (T2) e o estado descontinuado na Home.
///
/// O que se prova aqui é o que o protocolo pede do CLIENTE: a "2ª semana" precisa virar um
/// convite na tela (senão é só um parágrafo do protocolo), e a descontinuação precisa
/// aparecer sem oferecer um botão de sessão que o servidor recusaria com 403.
///
/// A Home monta o MaterialApp com os delegates `Global*`: sem eles, AppBar e ListTile
/// estouram em pt-BR (armadilha que já custou um CI vermelho no ADR-102).

class _FakeProgress extends ProgressRepository {
  final ProtocolProgress? _resposta;
  final bool _falha;
  _FakeProgress(this._resposta, {bool falha = false})
      : _falha = falha,
        super(ApiClient(SessionStore()));

  @override
  Future<ProtocolProgress> myProgress() async {
    if (_falha) throw Exception('sem rede');
    return _resposta!;
  }
}

ProtocolProgress _andamento({
  String status = 'active',
  bool t2Due = false,
  bool t2Late = false,
  String? reason,
}) =>
    ProtocolProgress(
      status: status,
      allocated: true,
      studyWeek: 2,
      sessionsCompleted: 9,
      sessionsPrescribed: 20,
      t2Due: t2Due,
      t2Late: t2Late,
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
  testWidgets('sem T2 devida, a Home não convida para nada', (t) async {
    await t.pumpWidget(_app(HomeScreen(progressRepo: _FakeProgress(_andamento()))));
    await t.pumpAndSettle();
    expect(find.text('Acompanhamento da 2ª semana'), findsNothing);
    expect(find.text('Iniciar sessão'), findsOneWidget);
  });

  testWidgets('T2 devida vira convite na Home', (t) async {
    await t.pumpWidget(
        _app(HomeScreen(progressRepo: _FakeProgress(_andamento(t2Due: true)))));
    await t.pumpAndSettle();
    expect(find.text('Acompanhamento da 2ª semana'), findsOneWidget);
    expect(find.textContaining('dois minutos'), findsOneWidget);
    // O convite não substitui a sessão do dia — o participante segue no protocolo.
    expect(find.text('Iniciar sessão'), findsOneWidget);
  });

  testWidgets('fora do prazo, o convite muda de texto mas continua', (t) async {
    await t.pumpWidget(_app(
        HomeScreen(progressRepo: _FakeProgress(_andamento(t2Due: true, t2Late: true)))));
    await t.pumpAndSettle();
    expect(find.textContaining('prazo sugerido passou'), findsOneWidget);
  });

  testWidgets('descontinuado: a Home explica e não oferece sessão', (t) async {
    await t.pumpWidget(_app(HomeScreen(
        progressRepo: _FakeProgress(
            _andamento(status: 'discontinued', reason: 'adesao_insuficiente')))));
    await t.pumpAndSettle();
    expect(find.text('Sua participação foi descontinuada'), findsOneWidget);
    // Oferecer um botão que o servidor recusaria com 403 é pior do que não oferecer.
    expect(find.text('Iniciar sessão'), findsNothing);
    // Os registros continuam acessíveis: descontinuar não apaga a participação (ITT).
    expect(find.text('Linha de base'), findsOneWidget);
    expect(find.textContaining('Não substitui'), findsOneWidget);
  });

  testWidgets('sem rede, a Home segue inteira — só não convida', (t) async {
    await t.pumpWidget(_app(HomeScreen(progressRepo: _FakeProgress(null, falha: true))));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    expect(find.text('Iniciar sessão'), findsOneWidget);
    expect(find.text('Acompanhamento da 2ª semana'), findsNothing);
  });
}
