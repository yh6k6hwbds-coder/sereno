import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/l10n/app_localizations.dart';
import 'package:sereno/features/home/home_screen.dart';
import 'package:sereno/services/progress_repository.dart';
import 'package:sereno/services/session_store.dart';

/// G9 — a dose de exposição auditiva na Home.
///
/// O protocolo, em "Intensidade e segurança auditiva", promete que "o aplicativo manterá
/// contabilização de dose acumulada e exibirá alerta ao atingir 50% do limite de
/// referência". Duas dessas palavras são do CLIENTE: *exibirá* e *alerta*. O que se prova
/// aqui é que a dose aparece, que o alerta aparece só quando o servidor o aciona, que a
/// ressalva de "estimativa" acompanha o número enquanto não há calibração — e que uma
/// exposição minúscula (a prevista pelo estudo é ~0,17% da referência) não é arredondada
/// para "0%", que leria como "nada foi contabilizado".
///
/// A Home monta o MaterialApp com os delegates `Global*`: sem eles, AppBar e ListTile
/// estouram em pt-BR (armadilha que já custou um CI vermelho no ADR-102).

class _FakeProgress extends ProgressRepository {
  final ProtocolProgress _resposta;
  _FakeProgress(this._resposta) : super(ApiClient(SessionStore()));

  @override
  Future<ProtocolProgress> myProgress() async => _resposta;
}

ProtocolProgress _andamento(HearingExposure? h) => ProtocolProgress(
      status: 'active',
      allocated: true,
      studyWeek: 2,
      sessionsCompleted: 9,
      sessionsPrescribed: 20,
      t2Due: false,
      t2Late: false,
      discontinuedReason: null,
      hearing: h,
    );

HearingExposure _dose({
  bool calibrated = false,
  double weekPct = 0.17,
  double totalPct = 0.17,
  double totalHours = 6.67,
  bool alert = false,
}) =>
    HearingExposure(
      calibrated: calibrated,
      weekPct: weekPct,
      totalPct: totalPct,
      totalHours: totalHours,
      alertAtPct: 50,
      alert: alert,
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
  testWidgets('a dose aparece com a ressalva de que ainda é estimativa', (t) async {
    await t.pumpWidget(_app(HomeScreen(progressRepo: _FakeProgress(_andamento(_dose())))));
    await t.pumpAndSettle();
    expect(find.text('Sua exposição sonora'), findsOneWidget);
    expect(find.textContaining('dose semanal de referência'), findsOneWidget);
    // Sem calibração em acoplador, o número é previsão no nível prescrito — e diz isso.
    expect(find.textContaining('Estimativa no nível previsto'), findsOneWidget);
    // Sem alerta, o texto de alerta não pode aparecer.
    expect(find.textContaining('metade da dose semanal'), findsNothing);
  });

  testWidgets('calibrado, a ressalva muda: o número passa a ser medido', (t) async {
    await t.pumpWidget(_app(
        HomeScreen(progressRepo: _FakeProgress(_andamento(_dose(calibrated: true))))));
    await t.pumpAndSettle();
    expect(find.textContaining('nível calibrado'), findsOneWidget);
    expect(find.textContaining('Estimativa no nível previsto'), findsNothing);
  });

  testWidgets('o alerta dos 50% aparece quando o servidor o aciona', (t) async {
    await t.pumpWidget(_app(HomeScreen(
        progressRepo: _FakeProgress(_andamento(
            _dose(weekPct: 52.4, totalPct: 52.4, totalHours: 21, alert: true))))));
    await t.pumpAndSettle();
    expect(find.textContaining('metade da dose semanal'), findsOneWidget);
    expect(find.textContaining('52,4%'), findsOneWidget);
  });

  testWidgets('exposição minúscula não vira "0%"', (t) async {
    await t.pumpWidget(_app(HomeScreen(
        progressRepo: _FakeProgress(_andamento(_dose(weekPct: 0.03, totalHours: 1.0))))));
    await t.pumpAndSettle();
    expect(find.textContaining('< 0,1%'), findsOneWidget);
    expect(find.textContaining('1h00'), findsOneWidget);
  });

  testWidgets('sem sessão nenhuma, o cartão não aparece', (t) async {
    await t.pumpWidget(_app(HomeScreen(
        progressRepo: _FakeProgress(_andamento(
            _dose(weekPct: 0, totalPct: 0, totalHours: 0))))));
    await t.pumpAndSettle();
    // "0% da referência" para quem nunca ouviu nada é ruído, não informação.
    expect(find.text('Sua exposição sonora'), findsNothing);
    expect(find.text('Iniciar sessão'), findsOneWidget);
  });

  testWidgets('servidor sem G9: a Home segue inteira', (t) async {
    await t.pumpWidget(_app(HomeScreen(progressRepo: _FakeProgress(_andamento(null)))));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    expect(find.text('Sua exposição sonora'), findsNothing);
    expect(find.text('Iniciar sessão'), findsOneWidget);
  });
}
