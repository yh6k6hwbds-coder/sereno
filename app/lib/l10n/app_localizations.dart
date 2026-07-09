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
/// As strings pt-BR são idênticas às originais das telas — assim widgets testados sem
/// localização na árvore seguem passando pelo fallback pt-BR.
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
      // Comuns
      'connectionError': 'Falha de conexão. Tente novamente.',
      // Home
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
      // Login/OTP
      'otpRequestPrompt': 'Entre com o seu código de estudo para receber um código de acesso.',
      'otpVerifyPrompt': 'Digite o código de 6 dígitos enviado ao seu e-mail.',
      'otpStudyCodeLabel': 'Código de estudo',
      'otpCodeLabel': 'Código',
      'otpSendCode': 'Enviar código',
      'otpEnter': 'Entrar',
      'otpBack': 'Voltar',
      'otpSent': 'Se o código de estudo existir, enviamos um código ao seu e-mail.',
      // Preparar sessão (fones)
      'prepSession': 'Preparar sessão',
      'useStereoHeadphones': 'Use fones estéreo',
      'headphoneBody': 'As sessões usam áudio em dois canais. Conecte fones com fio, ajuste um '
          'volume confortável e prefira um ambiente tranquilo.',
      'headphonesConnected': 'Meus fones estéreo estão conectados',
      // Consentimento
      'consentTitle': 'Termo de Consentimento',
      'consentReadSummary': 'Leia o resumo em linguagem simples:',
      'consentRead': 'Li e entendi as informações',
      'consentAgree': 'Concordo em participar',
      'consentLgpd': 'Autorizo o uso dos meus dados conforme a LGPD',
      'consentContinue': 'Concordar e continuar',
      'consentWithdraw': 'Você pode retirar o consentimento quando quiser.',
    },
    'en': {
      'connectionError': 'Connection failed. Please try again.',
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
      'otpRequestPrompt': 'Enter your study code to receive an access code.',
      'otpVerifyPrompt': 'Enter the 6-digit code sent to your e-mail.',
      'otpStudyCodeLabel': 'Study code',
      'otpCodeLabel': 'Code',
      'otpSendCode': 'Send code',
      'otpEnter': 'Enter',
      'otpBack': 'Back',
      'otpSent': 'If the study code exists, we sent a code to your e-mail.',
      'prepSession': 'Prepare session',
      'useStereoHeadphones': 'Use stereo headphones',
      'headphoneBody': 'Sessions use two-channel audio. Connect wired headphones, set a '
          'comfortable volume and prefer a quiet environment.',
      'headphonesConnected': 'My stereo headphones are connected',
      'consentTitle': 'Consent Form',
      'consentReadSummary': 'Read the plain-language summary:',
      'consentRead': 'I have read and understood the information',
      'consentAgree': 'I agree to participate',
      'consentLgpd': 'I authorize the use of my data under the LGPD',
      'consentContinue': 'Agree and continue',
      'consentWithdraw': 'You can withdraw your consent at any time.',
    },
  };

  static const Map<String, List<String>> _consentSummary = {
    'pt': [
      'O estudo avalia um app de sessões de áudio (frequências binaurais) para relaxamento e sono.',
      'Você fará questionários e sessões de ~20 min, com fones, por 4 semanas.',
      'Os riscos são mínimos; você pode interromper e registrar qualquer desconforto.',
      'Seus dados são tratados de forma confidencial e pseudonimizada (LGPD).',
      'A participação é voluntária; você pode sair a qualquer momento, sem prejuízo.',
    ],
    'en': [
      'The study evaluates an app of audio sessions (binaural beats) for relaxation and sleep.',
      'You will complete questionnaires and ~20-min sessions, with headphones, over 4 weeks.',
      'Risks are minimal; you may stop and report any discomfort.',
      'Your data is handled confidentially and pseudonymized (LGPD).',
      'Participation is voluntary; you may leave at any time, without penalty.',
    ],
  };

  String _t(String key) =>
      _values[locale.languageCode]?[key] ?? _values['pt']![key] ?? key;

  // Comuns
  String get connectionError => _t('connectionError');
  // Home
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
  // Login/OTP
  String get otpRequestPrompt => _t('otpRequestPrompt');
  String get otpVerifyPrompt => _t('otpVerifyPrompt');
  String get otpStudyCodeLabel => _t('otpStudyCodeLabel');
  String get otpCodeLabel => _t('otpCodeLabel');
  String get otpSendCode => _t('otpSendCode');
  String get otpEnter => _t('otpEnter');
  String get otpBack => _t('otpBack');
  String get otpSent => _t('otpSent');
  // Preparar sessão
  String get prepSession => _t('prepSession');
  String get useStereoHeadphones => _t('useStereoHeadphones');
  String get headphoneBody => _t('headphoneBody');
  String get headphonesConnected => _t('headphonesConnected');
  // Consentimento
  String get consentTitle => _t('consentTitle');
  String get consentReadSummary => _t('consentReadSummary');
  String get consentRead => _t('consentRead');
  String get consentAgree => _t('consentAgree');
  String get consentLgpd => _t('consentLgpd');
  String get consentContinue => _t('consentContinue');
  String get consentWithdraw => _t('consentWithdraw');
  List<String> get consentSummary =>
      _consentSummary[locale.languageCode] ?? _consentSummary['pt']!;
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
