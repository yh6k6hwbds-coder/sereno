import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sereno/core/api_client.dart';
import 'package:sereno/services/session_store.dart';
import 'package:sereno/services/outcomes_repository.dart';
import 'package:sereno/shared/likert_question.dart';

class _Store extends SessionStore {
  @override
  Future<String?> accessToken() async => 'tok';
  @override
  Future<String?> refreshToken() async => null;
}

void main() {
  late http.Request captured;

  OutcomesRepository repoReturning(Map<String, dynamic> body, [int status = 201]) {
    final api = ApiClient(_Store(), client: MockClient((req) async {
      captured = req;
      return http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});
    }));
    return OutcomesRepository(api);
  }

  test('submitBaseline: gad7_items + psqi no endpoint certo (autenticado)', () async {
    await repoReturning({'gad7_total': 10}).submitBaseline(
        gad7: [1, 2, 3, 0, 1, 2, 1], psqi: {'subjective_quality': 1});
    expect(captured.method, 'POST');
    expect(captured.url.path, endsWith('/participants/me/baseline'));
    expect(captured.headers['Authorization'], 'Bearer tok');
    final b = jsonDecode(captured.body) as Map<String, dynamic>;
    expect(b['gad7_items'], [1, 2, 3, 0, 1, 2, 1]);
    expect(b['psqi']['subjective_quality'], 1);
  });

  test('submitSurvey: /sessions/{id}/survey', () async {
    await repoReturning({}).submitSurvey('s1',
        feeling: 3, relaxation: 4, sleptBetter: 2, liked: 4, intensity: 2, wouldRepeat: true);
    expect(captured.url.path, endsWith('/sessions/s1/survey'));
    final b = jsonDecode(captured.body) as Map<String, dynamic>;
    expect(b['would_repeat'], true);
    expect(b['slept_better'], 2);
  });

  test('submitDiary: /diary com a data', () async {
    await repoReturning({}).submitDiary(date: '2026-07-05', latencyMin: 20, quality: 3);
    expect(captured.url.path, endsWith('/diary'));
    final b = jsonDecode(captured.body) as Map<String, dynamic>;
    expect(b['diary_date'], '2026-07-05');
    expect(b['latency_min'], 20);
  });

  test('submitFollowup: gad7/psqi/sus/blinding', () async {
    await repoReturning({'sus_score': 80}).submitFollowup(
        gad7: List.filled(7, 1), psqi: {'x': 1}, sus: List.filled(10, 4), blindingGuess: 'nao_sei');
    expect(captured.url.path, endsWith('/participants/me/followup'));
    final b = jsonDecode(captured.body) as Map<String, dynamic>;
    expect((b['sus_items'] as List).length, 10);
    expect(b['blinding_guess'], 'nao_sei');
  });

  test('reportAdverseEvent: type/severity', () async {
    await repoReturning({'status': 'recorded'})
        .reportAdverseEvent(type: 'headache', severity: 'moderate');
    expect(captured.url.path, endsWith('/adverse-events'));
    final b = jsonDecode(captured.body) as Map<String, dynamic>;
    expect(b['severity'], 'moderate');
  });

  testWidgets('LikertQuestion chama onChanged ao tocar uma opção', (tester) async {
    int? picked;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: LikertQuestion(prompt: 'p', onChanged: (v) => picked = v))));
    await tester.tap(find.text('2'));
    expect(picked, 2);
  });
}
