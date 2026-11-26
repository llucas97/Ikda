import 'package:material_ui/material_ui.dart';

import '../services/auth_service.dart';
import '../state/app_store.dart';
import '../theme.dart';
import 'login_screen.dart';

/// 홈 머리글의 계정 버튼. 이름·로그아웃·탈퇴, 또는 로그인하기.
void showAccountSheet(BuildContext context) {
  final auth = AppScope.authOf(context);
  final messenger = ScaffoldMessenger.of(context);
  showModalBottomSheet<void>(
    context: context,
    backgroundColor: AppColors.canvas,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(Radii.r24)),
    ),
    builder: (sheetContext) {
      return ListenableBuilder(
        listenable: auth,
        builder: (context, _) {
          final user = auth.user;
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(Space.s16, Space.s24, Space.s16, Space.s16),
              child: user == null
                  ? _LoginPrompt(onLogin: () {
                      Navigator.pop(sheetContext);
                      Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const LoginScreen()));
                    })
                  : _SignedIn(
                      userName: (user.name == null || user.name!.isEmpty) ? '회원' : user.name!,
                      provider: _providerLabel(user.providers),
                      onLogout: () => _confirm(
                        sheetContext,
                        title: '로그아웃할까요?',
                        confirm: '로그아웃',
                        action: auth.logout,
                        messenger: messenger,
                      ),
                      onWithdraw: () => _confirm(
                        sheetContext,
                        title: '탈퇴하면 기록이 모두 지워져요',
                        confirm: '탈퇴할게요',
                        danger: true,
                        action: auth.withdraw,
                        messenger: messenger,
                      ),
                    ),
            ),
          );
        },
      );
    },
  );
}

class _LoginPrompt extends StatelessWidget {
  const _LoginPrompt({required this.onLogin});
  final VoidCallback onLogin;

  @override
  Widget build(BuildContext context) {
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('로그인하면 기록이 이 계정에 남아요', style: AppText.body),
      const SizedBox(height: Space.s16),
      FilledButton(onPressed: onLogin, child: const Text('로그인하기')),
    ]);
  }
}

class _SignedIn extends StatelessWidget {
  const _SignedIn({
    required this.userName,
    required this.provider,
    required this.onLogout,
    required this.onWithdraw,
  });

  final String userName;
  final String provider;
  final VoidCallback onLogout;
  final VoidCallback onWithdraw;

  @override
  Widget build(BuildContext context) {
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(userName, style: AppText.heading2),
      if (provider.isNotEmpty) ...[
        const SizedBox(height: Space.s4),
        Text(provider, style: AppText.caption),
      ],
      const SizedBox(height: Space.s24),
      FilledButton(onPressed: onLogout, child: const Text('로그아웃')),
      const SizedBox(height: Space.s12),
      TextButton(
        onPressed: onWithdraw,
        style: TextButton.styleFrom(foregroundColor: AppColors.urgent),
        child: const Text('회원 탈퇴'),
      ),
    ]);
  }
}

Future<void> _confirm(
  BuildContext sheetContext, {
  required String title,
  required String confirm,
  required Future<void> Function() action,
  required ScaffoldMessengerState messenger,
  bool danger = false,
}) async {
  final ok = await showDialog<bool>(
    context: sheetContext,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: AppColors.canvas,
      title: Text(title, style: AppText.title),
      actions: [
        TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('아니요')),
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, true),
          style: danger ? TextButton.styleFrom(foregroundColor: AppColors.urgent) : null,
          child: Text(confirm),
        ),
      ],
    ),
  );
  if (ok != true) return;
  if (sheetContext.mounted) Navigator.pop(sheetContext);
  try {
    await action();
  } on AuthException catch (e) {
    messenger.showSnackBar(SnackBar(content: Text(e.userMessage)));
  }
}

String _providerLabel(List<String> providers) {
  const names = {'KAKAO': '카카오', 'GOOGLE': '구글', 'FAKE': '시험'};
  return providers.map((p) => names[p] ?? p).join(' · ');
}
