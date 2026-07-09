import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/participant_repository.dart';
import '../../shared/disclaimer_banner.dart';
import '../../shared/wave_mark.dart';
import '../consent/consent_screen.dart';

/// Login do participante por e-mail/OTP (sem senha). Duas etapas:
/// (1) informar o código de estudo → solicitar OTP; (2) digitar o OTP → entrar.
class OtpScreen extends StatefulWidget {
  final ParticipantRepository repo;
  const OtpScreen({super.key, required this.repo});
  @override
  State<OtpScreen> createState() => _OtpScreenState();
}

enum _Step { request, verify }

class _OtpScreenState extends State<OtpScreen> {
  final _studyCode = TextEditingController();
  final _code = TextEditingController();
  _Step _step = _Step.request;
  bool _loading = false;

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _loading = true);
    try {
      await action();
    } on ApiException catch (e) {
      _snack(e.toString());
    } catch (_) {
      _snack(AppLocalizations.of(context).connectionError);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String msg) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(msg)));

  Future<void> _requestOtp() => _run(() async {
        await widget.repo.requestOtp(_studyCode.text.trim());
        setState(() => _step = _Step.verify);
        _snack(AppLocalizations.of(context).otpSent);
      });

  Future<void> _verify() => _run(() async {
        await widget.repo.verifyOtp(_studyCode.text.trim(), _code.text.trim());
        if (!mounted) return;
        Navigator.of(context).pushReplacement(MaterialPageRoute(
            builder: (_) => ConsentScreen(repo: widget.repo)));
      });

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final isRequest = _step == _Step.request;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const WaveMark(),
            const SizedBox(height: 24),
            Text('Sereno', style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 8),
            Text(
              isRequest ? t.otpRequestPrompt : t.otpVerifyPrompt,
              style: const TextStyle(color: SerenoColors.muted, height: 1.4),
            ),
            const SizedBox(height: 24),
            if (isRequest)
              TextField(
                controller: _studyCode,
                textCapitalization: TextCapitalization.characters,
                decoration: InputDecoration(labelText: t.otpStudyCodeLabel),
              )
            else
              TextField(
                controller: _code,
                keyboardType: TextInputType.number,
                maxLength: 6,
                style: const TextStyle(fontFamily: 'IBM Plex Mono', fontSize: 22, letterSpacing: 8),
                textAlign: TextAlign.center,
                decoration: InputDecoration(labelText: t.otpCodeLabel, counterText: ''),
              ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _loading ? null : (isRequest ? _requestOtp : _verify),
              child: _loading
                  ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(isRequest ? t.otpSendCode : t.otpEnter),
            ),
            if (!isRequest)
              TextButton(
                onPressed: _loading ? null : () => setState(() => _step = _Step.request),
                child: Text(t.otpBack),
              ),
            const Spacer(),
            const DisclaimerBanner(),
          ]),
        ),
      ),
    );
  }
}
