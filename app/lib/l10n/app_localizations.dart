import 'package:flutter/widgets.dart';

/// Internacionalização (E5/ADR-070) — delegate MANUAL, sem code-gen.
///
/// Decisão: um mapa de strings por locale, resolvido por um `LocalizationsDelegate`
/// próprio, em vez do pipeline ARB/intl com geração. Motivo: é mínimo, totalmente
/// testável e não depende de um passo de build (o ambiente de dev não tem SDK Flutter;
/// a validação é o CI). Migrar para ARB/intl é evolução futura, sem quebrar as telas
/// (elas só consomem `AppLocalizations.of(context)`).
///
/// pt-BR é o idioma do piloto (padrão/fallback); `en` prova a internacionalização.
class AppLocalizations {
  final Locale locale;
  const AppLocalizations(this.locale);

  /// Tolerante: sem localização na árvore (ex.: um widget testado isolado), cai no
  /// pt-BR — o idioma padrão do piloto. Nunca lança.
  static AppLocalizations of(BuildContext context) =>
      Localizations.of<AppLocalizations>(context, AppLocalizations) ??
      const AppLocalizations(Locale('pt'));

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  static const List<Locale> supportedLocales = [Locale('pt'), Locale('en')];

  static const Map<String, Map<String, String>> _values = {
    'pt': {
      'greeting': 'Boa noite,',
      'ready': 'tudo pronto',
      'startSession': 'Iniciar sessão',
      'sessionMeta': '~20 min · use fones',
      'records': 'Registros',
      'baseline': 'Linha de base',
      'sleepDiary': 'Diário de sono',
      'followup': 'Seguimento',
      'reportProblem': 'Relatar um problema',
      'logout': 'Sair',
      'disclaimer':
          'Ferramenta complementar. Não substitui avaliação ou tratamento profissional.',
    },
    'en': {
      'greeting': 'Good evening,',
      'ready': "you're all set",
      'startSession': 'Start session',
      'sessionMeta': '~20 min · use headphones',
      'records': 'Records',
      'baseline': 'Baseline',
      'sleepDiary': 'Sleep diary',
      'followup': 'Follow-up',
      'reportProblem': 'Report a problem',
      'logout': 'Log out',
      'disclaimer':
          'Complementary tool. It does not replace professional evaluation or treatment.',
    },
  };

  String _t(String key) =>
      _values[locale.languageCode]?[key] ?? _values['pt']![key] ?? key;

  String get greeting => _t('greeting');
  String get ready => _t('ready');
  String get startSession => _t('startSession');
  String get sessionMeta => _t('sessionMeta');
  String get records => _t('records');
  String get baseline => _t('baseline');
  String get sleepDiary => _t('sleepDiary');
  String get followup => _t('followup');
  String get reportProblem => _t('reportProblem');
  String get logout => _t('logout');
  String get disclaimer => _t('disclaimer');
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) =>
      AppLocalizations.supportedLocales.any((l) => l.languageCode == locale.languageCode);

  @override
  Future<AppLocalizations> load(Locale locale) async => AppLocalizations(locale);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}
