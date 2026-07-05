import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sereno/features/home/home_screen.dart';

void main() {
  testWidgets('Home lista os registros e navega para a linha de base', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // As telas de registro (B2/B4/B5/B6) estão acessíveis a partir da Home.
    expect(find.text('Iniciar sessão'), findsOneWidget);
    expect(find.text('Linha de base'), findsOneWidget);
    expect(find.text('Diário de sono'), findsOneWidget);
    expect(find.text('Seguimento'), findsOneWidget);
    expect(find.text('Relatar um problema'), findsOneWidget);

    await tester.tap(find.text('Linha de base'));
    await tester.pumpAndSettle();
    expect(find.text('Como você tem estado'), findsOneWidget); // AppBar da BaselineScreen
  });
}
