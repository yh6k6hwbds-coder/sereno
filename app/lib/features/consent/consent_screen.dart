import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/theme.dart';
import '../../l10n/app_localizations.dart';
import '../../services/participant_repository.dart';
import '../../shared/disclaimer_banner.dart';
import '../home/home_screen.dart';
import 'tcle_full_text_screen.dart';

/// Consentimento (TCLE): resumo em linguagem simples + confirmações. O participante
/// só prossegue ao aceitar; a decisão é enviada ao backend (registro versionado + hash).
class ConsentScreen extends StatefulWidget {
  final ParticipantRepository repo;
  const ConsentScreen({super.key, required this.repo});
  @override
  State<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends State<ConsentScreen> {
  bool _read = false, _agree = false, _lgpd = false, _loading = false;
  bool get _canProceed => _read && _agree && _lgpd && !_loading;

  Future<void> _submit() async {
    setState(() => _loading = true);
    try {
      await widget.repo.recordConsent(version: tcleVersion, accepted: true);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeScreen()));
    } on ApiException catch (e) {
      _snack(e.toString());
    } catch (_) {
      _snack(AppLocalizations.of(context).connectionError);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String m) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(t.consentTitle), backgroundColor: SerenoColors.paper, elevation: 0),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(
              child: ListView(children: [
                Text(t.consentReadSummary, style: const TextStyle(color: SerenoColors.muted)),
                const SizedBox(height: 12),
                ...t.consentSummary.map((item) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 6, right: 10),
                          child: Icon(Icons.circle, size: 6, color: SerenoColors.teal),
                        ),
                        Expanded(child: Text(item, style: const TextStyle(height: 1.4))),
                      ]),
                    )),
                const SizedBox(height: 4),
                // O resumo acima NÃO substitui o termo. O texto integral fica a um toque,
                // ANTES das confirmações — marcar "li e entendi" sem ter tido acesso ao
                // termo inteiro não seria consentimento informado.
                OutlinedButton.icon(
                  onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const TcleFullTextScreen())),
                  icon: const Icon(Icons.description_outlined, size: 18),
                  label: Text(t.consentReadFull),
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(46),
                    foregroundColor: SerenoColors.petrol,
                    side: const BorderSide(color: SerenoColors.border),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
                const SizedBox(height: 8),
                CheckboxListTile(
                  value: _read,
                  onChanged: (v) => setState(() => _read = v ?? false),
                  title: Text(t.consentRead),
                  contentPadding: EdgeInsets.zero,
                ),
                CheckboxListTile(
                  value: _agree,
                  onChanged: (v) => setState(() => _agree = v ?? false),
                  title: Text(t.consentAgree),
                  contentPadding: EdgeInsets.zero,
                ),
                CheckboxListTile(
                  value: _lgpd,
                  onChanged: (v) => setState(() => _lgpd = v ?? false),
                  title: Text(t.consentLgpd),
                  contentPadding: EdgeInsets.zero,
                ),
              ]),
            ),
            FilledButton(
              onPressed: _canProceed ? _submit : null,
              child: _loading
                  ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(t.consentContinue),
            ),
            const SizedBox(height: 8),
            Text(t.consentWithdraw,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 12, color: SerenoColors.muted)),
            const SizedBox(height: 12),
            const DisclaimerBanner(),
          ]),
        ),
      ),
    );
  }
}
