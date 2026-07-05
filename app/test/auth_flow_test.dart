import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:sereno/app.dart';
import 'package:sereno/core/api_client.dart';
import 'package:sereno/services/session_store.dart';
import 'package:sereno/services/participant_repository.dart';
import 'package:sereno/features/home/home_screen.dart';
import 'package:sereno/features/auth/otp_screen.dart';

/// Armazenamento em memória (o flutter_secure_storage usa platform channels).
class _FakeStore extends SessionStore {
  String? access;
  String? refresh;
  bool cleared = false;
  _FakeStore({this.access, this.refresh});
  @override
  Future<String?> accessToken() async => access;
  @override
  Future<String?> refreshToken() async => refresh;
  @override
  Future<void> saveTokens(String a, String r) async {
    access = a;
    refresh = r;
  }

  @override
  Future<void> clear() async {
    access = null;
    refresh = null;
    cleared = true;
  }

  @override
  Future<bool> isAuthenticated() async => access != null;
}

void main() {
  test('401 dispara refresh transparente e repete a chamada', () async {
    final store = _FakeStore(access: 'old', refresh: 'r1');
    var protectedCalls = 0;
    final mock = MockClient((req) async {
      if (req.url.path.endsWith('/auth/refresh')) {
        return http.Response(jsonEncode({'access_token': 'new', 'refresh_token': 'r2'}), 200);
      }
      protectedCalls++;
      return req.headers['Authorization'] == 'Bearer old'
          ? http.Response(jsonEncode({'title': 'expirou'}), 401)
          : http.Response(jsonEncode({'ok': true}), 200);
    });
    final api = ApiClient(store, client: mock);

    final r = await api.post('/x', {}, authenticated: true);
    expect(r['ok'], true);
    expect(store.access, 'new'); // token renovado e salvo
    expect(store.refresh, 'r2');
    expect(protectedCalls, 2); // tentou, refrescou, repetiu uma vez
  });

  test('refresh inválido encerra a sessão e propaga o 401', () async {
    final store = _FakeStore(access: 'old', refresh: 'bad');
    final mock = MockClient((req) async {
      if (req.url.path.endsWith('/auth/refresh')) return http.Response('{}', 401);
      return http.Response(jsonEncode({'title': 'expirou'}), 401);
    });
    final api = ApiClient(store, client: mock);

    await expectLater(api.post('/x', {}, authenticated: true), throwsA(isA<ApiException>()));
    expect(store.cleared, true); // logout: armazenamento seguro limpo
  });

  test('sem refresh token não tenta refrescar', () async {
    final store = _FakeStore(access: 'old'); // sem refresh
    var refreshCalled = false;
    final mock = MockClient((req) async {
      if (req.url.path.endsWith('/auth/refresh')) {
        refreshCalled = true;
        return http.Response('{}', 200);
      }
      return http.Response(jsonEncode({'title': 'expirou'}), 401);
    });
    final api = ApiClient(store, client: mock);

    await expectLater(api.post('/x', {}, authenticated: true), throwsA(isA<ApiException>()));
    expect(refreshCalled, false);
  });

  testWidgets('AuthGate: sessão persistida abre a Home', (tester) async {
    final store = _FakeStore(access: 'tok');
    final repo = ParticipantRepository(ApiClient(store), store);
    await tester.pumpWidget(MaterialApp(home: AuthGate(store: store, repo: repo)));
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);
  });

  testWidgets('AuthGate: sem sessão abre o login (OTP)', (tester) async {
    final store = _FakeStore(); // não autenticado
    final repo = ParticipantRepository(ApiClient(store), store);
    await tester.pumpWidget(MaterialApp(home: AuthGate(store: store, repo: repo)));
    await tester.pumpAndSettle();
    expect(find.byType(OtpScreen), findsOneWidget);
  });
}
