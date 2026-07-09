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
      // Comuns (ações)
      'back': 'Voltar',
      'send': 'Enviar',
      'yes': 'Sim',
      'no': 'Não',
      // Player de sessão
      'playerLoadError': 'Não foi possível carregar o áudio. Verifique a conexão e tente novamente.',
      'playerPreparing': 'Preparando o áudio…',
      'playerPaused': 'Pausado',
      'playerInSession': 'Em sessão',
      'playerDoneTitle': 'Sessão concluída',
      'playerDoneAuto': 'Sessão finalizada. Como foi para você?',
      'playerDoneManual': 'Sessão encerrada. Registramos o tempo efetivo.',
      'playerAnswerQuick': 'Responder rápido',
      'playerBackHome': 'Voltar ao início',
      'playerBreathe': 'Feche os olhos e respire com calma.',
      // Pós-sessão
      'surveyTitle': 'Como foi a sessão',
      'surveyFeeling': 'Como você se sente agora? (0 muito mal – 4 muito bem)',
      'surveyRelaxation': 'Quão relaxado(a) você está? (0 nada – 4 muito)',
      'surveySleptBetter': 'Se foi à noite, acha que dormiu melhor? (opcional)',
      'surveyLiked': 'O quanto gostou desta sessão? (0 nada – 4 muito)',
      'surveyIntensity': 'Como percebeu a intensidade do áudio? (0 fraca – 4 forte)',
      'surveyWouldRepeat': 'Repetiria esta sessão?',
      'surveyThanks': 'Obrigado pelo retorno!',
      'surveyAlready': 'Você já respondeu esta sessão.',
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
      'back': 'Back',
      'send': 'Send',
      'yes': 'Yes',
      'no': 'No',
      'playerLoadError': 'Could not load the audio. Check your connection and try again.',
      'playerPreparing': 'Preparing the audio…',
      'playerPaused': 'Paused',
      'playerInSession': 'In session',
      'playerDoneTitle': 'Session complete',
      'playerDoneAuto': 'Session finished. How was it for you?',
      'playerDoneManual': 'Session ended. We recorded the effective time.',
      'playerAnswerQuick': 'Quick answer',
      'playerBackHome': 'Back to start',
      'playerBreathe': 'Close your eyes and breathe calmly.',
      'surveyTitle': 'How was the session',
      'surveyFeeling': 'How do you feel now? (0 very bad – 4 very good)',
      'surveyRelaxation': 'How relaxed are you? (0 not at all – 4 very)',
      'surveySleptBetter': 'If it was at night, do you think you slept better? (optional)',
      'surveyLiked': 'How much did you like this session? (0 not at all – 4 very)',
      'surveyIntensity': 'How did you perceive the audio intensity? (0 weak – 4 strong)',
      'surveyWouldRepeat': 'Would you repeat this session?',
      'surveyThanks': 'Thanks for your feedback!',
      'surveyAlready': 'You have already answered this session.',
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
  // Comuns (ações)
  String get back => _t('back');
  String get send => _t('send');
  String get yes => _t('yes');
  String get no => _t('no');
  // Player de sessão
  String get playerLoadError => _t('playerLoadError');
  String get playerPreparing => _t('playerPreparing');
  String get playerPaused => _t('playerPaused');
  String get playerInSession => _t('playerInSession');
  String get playerDoneTitle => _t('playerDoneTitle');
  String get playerDoneAuto => _t('playerDoneAuto');
  String get playerDoneManual => _t('playerDoneManual');
  String get playerAnswerQuick => _t('playerAnswerQuick');
  String get playerBackHome => _t('playerBackHome');
  String get playerBreathe => _t('playerBreathe');
  // Pós-sessão
  String get surveyTitle => _t('surveyTitle');
  String get surveyFeeling => _t('surveyFeeling');
  String get surveyRelaxation => _t('surveyRelaxation');
  String get surveySleptBetter => _t('surveySleptBetter');
  String get surveyLiked => _t('surveyLiked');
  String get surveyIntensity => _t('surveyIntensity');
  String get surveyWouldRepeat => _t('surveyWouldRepeat');
  String get surveyThanks => _t('surveyThanks');
  String get surveyAlready => _t('surveyAlready');
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
