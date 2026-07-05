import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/services/session_store.dart';
import 'package:sereno/services/outcomes_repository.dart';
import 'package:sereno/features/baseline/baseline_screen.dart';
import 'package:sereno/features/session/post_session_survey_screen.dart';
import 'package:sereno/features/diary/sleep_diary_screen.dart';
import 'package:sereno/features/followup/followup_screen.dart';
import 'package:sereno/features/adverse/adverse_event_screen.dart';

class _Store extends SessionStore {
  @override
  Future<String?> accessToken() async => 'tok';
  @override
  Future<String?> refreshToken() async => null;
}

OutcomesRepository _repo() => OutcomesRepository(
    ApiClient(_Store(), client: MockClient((r) async => http.Response('{}', 201))));

Future<void> _smoke(WidgetTester tester, Widget screen, String appBarTitle) async {
  await tester.pumpWidget(MaterialApp(home: screen));
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull); // nenhuma exceção ao construir a tela
  expect(find.text(appBarTitle), findsOneWidget);
}

void main() {
  testWidgets('BaselineScreen (B2) renderiza', (t) async {
    await _smoke(t, BaselineScreen(repo: _repo()), 'Como você tem estado');
  });
  testWidgets('PostSessionSurveyScreen (B3) renderiza', (t) async {
    await _smoke(t, PostSessionSurveyScreen(repo: _repo(), sessionId: 's1'), 'Como foi a sessão');
  });
  testWidgets('SleepDiaryScreen (B4) renderiza', (t) async {
    await _smoke(t, SleepDiaryScreen(repo: _repo()), 'Diário de sono');
  });
  testWidgets('FollowupScreen (B5) renderiza', (t) async {
    await _smoke(t, FollowupScreen(repo: _repo()), 'Seguimento');
  });
  testWidgets('AdverseEventScreen (B6) renderiza; grave mostra ajuda', (t) async {
    await _smoke(t, AdverseEventScreen(repo: _repo()), 'Relatar um problema');
    await t.tap(find.text('Grave'));
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
    expect(find.textContaining('192'), findsOneWidget); // reforço de ajuda em gravidade alta
  });
}
