import 'package:flutter/material.dart';

/// Identidade "Sereno" (Etapa 3): noturna e calma. Tons frios; o único quente é
/// reservado a avisos. Tipografia: Fraunces (display), Inter (corpo), IBM Plex
/// Mono (dados) — declaradas por família; os arquivos devem ser empacotados.
class SerenoColors {
  static const night = Color(0xFF101A2B);
  static const petrol = Color(0xFF1B4B5A);
  static const teal = Color(0xFF128394);
  static const tealLight = Color(0xFF5CC7D6);
  static const paper = Color(0xFFF3F6F8);
  static const ink = Color(0xFF1A2632);
  static const muted = Color(0xFF5A6B78);
  static const alert = Color(0xFFE4772E);
  static const border = Color(0xFFE1E7EC);
}

ThemeData buildSerenoTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: SerenoColors.teal,
    primary: SerenoColors.teal,
    secondary: SerenoColors.petrol,
    error: SerenoColors.alert,
    surface: SerenoColors.paper,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: SerenoColors.paper,
    fontFamily: 'Inter',
    textTheme: const TextTheme(
      headlineMedium: TextStyle(fontFamily: 'Fraunces', fontWeight: FontWeight.w600, color: SerenoColors.ink),
      titleLarge: TextStyle(fontFamily: 'Fraunces', fontWeight: FontWeight.w600, color: SerenoColors.ink),
      bodyMedium: TextStyle(color: SerenoColors.ink, height: 1.4),
      labelLarge: TextStyle(fontWeight: FontWeight.w700),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: SerenoColors.border),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: SerenoColors.teal,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
  );
}
