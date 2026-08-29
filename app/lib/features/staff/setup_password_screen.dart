import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show SystemNavigator;

import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../shared/wave_mark.dart';

/// Tela que recebe o link de convite/redefinição de senha da EQUIPE (ADR-094/096).
///
/// É a única tela do app voltada ao staff, e só é alcançável com um token na URL — o
/// participante nunca chega aqui. Não faz login nem guarda sessão: define a senha e para.
/// A conta de staff é usada na API/painel de pesquisa, não neste aplicativo.
class SetupPasswordScreen extends StatefulWidget {
  final ApiClient api;
  final String token;
  const SetupPasswordScreen({super.key, required this.api, required this.token});

  @override
  State<SetupPasswordScreen> createState() => _SetupPasswordScreenState();
}

class _SetupPasswordScreenState extends State<SetupPasswordScreen> {
  static const int minLength = 8; // casa com a validação do servidor (422 abaixo disso)

  final _password = TextEditingController();
  final _confirm = TextEditingController();
  bool _loading = false;
  bool _obscure = true;
  bool _done = false;
  bool _mfaEnabled = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _scrubUrl();
  }

  /// Tira o token da barra de endereço assim que a tela abre.
  ///
  /// O token equivale à senha durante sua janela de validade: deixá-lo na URL o expõe ao
  /// histórico do navegador e ao cabeçalho `Referer` de qualquer requisição que a página
  /// venha a fazer. Trocar a URL não invalida o token (isso quem faz é o consumo no
  /// servidor), mas encurta bastante o rastro.
  void _scrubUrl() {
    if (!kIsWeb) return;
    final limpa = Uri.base.replace(
        queryParameters: Map<String, String>.from(Uri.base.queryParameters)..remove('token'));
    SystemNavigator.routeInformationUpdated(uri: limpa, replace: true);
  }

  @override
  void dispose() {
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final t = AppLocalizations.of(context);
    final senha = _password.text;
    // Valida antes de chamar: erro de digitação não deve gastar o token nem uma tentativa
    // do rate limit do endpoint público.
    if (senha.length < minLength) {
      setState(() => _error = t.staffSetupTooShort);
      return;
    }
    if (senha != _confirm.text) {
      setState(() => _error = t.staffSetupMismatch);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await widget.api
          .post('/staff/setup-password', {'token': widget.token, 'new_password': senha});
      if (!mounted) return;
      setState(() {
        _done = true;
        _mfaEnabled = r['mfa_enabled'] == true;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      // `t` foi resolvido ANTES do await: nada de usar o context depois de uma espera.
      if (mounted) setState(() => _error = t.connectionError);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const WaveMark(),
            const SizedBox(height: 24),
            Text('Sereno', style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 8),
            Text(_done ? t.staffSetupDoneTitle : t.staffSetupTitle,
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_done) ..._success(t) else ..._form(t),
          ]),
        ),
      ),
    );
  }

  List<Widget> _form(AppLocalizations t) => [
        Text(t.staffSetupPrompt,
            style: const TextStyle(color: SerenoColors.muted, height: 1.4)),
        const SizedBox(height: 24),
        TextField(
          controller: _password,
          obscureText: _obscure,
          decoration: InputDecoration(
            labelText: t.staffSetupPasswordLabel,
            helperText: t.staffSetupPasswordHelp,
            suffixIcon: IconButton(
              icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
              tooltip: t.staffSetupShowPassword,
              onPressed: () => setState(() => _obscure = !_obscure),
            ),
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _confirm,
          obscureText: _obscure,
          decoration: InputDecoration(labelText: t.staffSetupConfirmLabel),
          onSubmitted: (_) => _loading ? null : _submit(),
        ),
        if (_error != null) ...[
          const SizedBox(height: 16),
          Text(_error!, style: const TextStyle(color: SerenoColors.alert, height: 1.4)),
        ],
        const SizedBox(height: 24),
        FilledButton(
          onPressed: _loading ? null : _submit,
          child: _loading
              ? const SizedBox(
                  height: 22,
                  width: 22,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
              : Text(t.staffSetupSubmit),
        ),
        const SizedBox(height: 24),
        // O reset NÃO mexe no segundo fator (ADR-094). Dizer isso aqui evita que alguém
        // conclua que "redefinir a senha" reinicia também o MFA.
        Text(t.staffSetupMfaNote,
            style: const TextStyle(color: SerenoColors.muted, fontSize: 13, height: 1.4)),
      ];

  List<Widget> _success(AppLocalizations t) => [
        Text(t.staffSetupDoneBody,
            style: const TextStyle(color: SerenoColors.muted, height: 1.4)),
        if (_mfaEnabled) ...[
          const SizedBox(height: 12),
          Text(t.staffSetupDoneMfa,
              style: const TextStyle(color: SerenoColors.muted, height: 1.4)),
        ],
      ];
}
