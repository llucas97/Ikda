import 'package:flutter_svg/flutter_svg.dart';
import 'package:material_ui/material_ui.dart';

import '../config.dart';
import '../services/auth_service.dart';
import '../state/app_store.dart';
import '../theme.dart';

/// 카카오·구글 로그인. 글은 제목 두 줄과 버튼뿐이다.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.asGate = false});

  /// 앱 첫 화면으로 쓰일 때. 성공하면 바깥 게이트가 홈으로 바꾼다.
  final bool asGate;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      if (!mounted) return;
      final auth = AppScope.authOf(context);
      if (auth.user != null && !widget.asGate && Navigator.canPop(context)) {
        Navigator.pop(context);
      }
    } on AuthException catch (e) {
      if (!e.cancelled && mounted) {
        setState(() => _error = e.userMessage.isEmpty ? '로그인하지 못했어요. 다시 해 주세요.' : e.userMessage);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = AppScope.authOf(context);
    return Scaffold(
      backgroundColor: AppColors.canvas,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: Space.s16),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
            const SizedBox(height: Space.s24),
            Center(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(Radii.r24),
                child: Image.asset('assets/brand/app_icon.png', width: 132, height: 132, fit: BoxFit.cover),
              ),
            ),
            const SizedBox(height: Space.s16),
            Text('서류를 찍으면 쉽게 읽어 드려요', textAlign: TextAlign.center, style: AppText.body.copyWith(color: AppColors.inkSub)),
            const SizedBox(height: Space.s24),
            if (_error != null) ...[
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(Space.s16),
                decoration: BoxDecoration(
                  color: AppColors.warnBg,
                  borderRadius: BorderRadius.circular(Radii.r12),
                  border: Border.all(color: AppColors.warnLine),
                ),
                child: Text(_error!, style: AppText.body.copyWith(color: AppColors.warnText)),
              ),
              const SizedBox(height: Space.s16),
            ],
            if (_busy)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: Space.s24),
                child: Column(children: [
                  SizedBox(
                    width: 64,
                    height: 64,
                    child: CircularProgressIndicator(strokeWidth: 6, color: AppColors.accent),
                  ),
                  SizedBox(height: Space.s16),
                  Text('로그인하는 중이에요', style: AppText.body),
                ]),
              )
            else ...[
              _BrandButton(
                background: const Color(0xFFFEE500),
                foreground: const Color(0xD9000000),
                semanticsLabel: '카카오로 로그인',
                label: '카카오 로그인',
                icon: SvgPicture.asset('assets/brand/kakao_symbol.svg', width: 24, height: 22),
                onPressed: () => _run(auth.loginKakao),
              ),
              const SizedBox(height: Space.s16),
              _BrandButton(
                background: const Color(0xFFFFFFFF),
                foreground: const Color(0xFF1F1F1F),
                side: const BorderSide(color: Color(0xFF747775)),
                semanticsLabel: 'Google 계정으로 로그인',
                label: 'Google 계정으로 로그인',
                icon: SvgPicture.asset('assets/brand/google_g.svg', width: 24, height: 24),
                onPressed: () => _run(auth.loginGoogle),
              ),
              if (AppConfig.showTestLogin) ...[
                const SizedBox(height: Space.s16),
                _BrandButton(
                  background: AppColors.accentSoft,
                  foreground: AppColors.ink,
                  semanticsLabel: '시험 로그인',
                  label: '시험 로그인',
                  icon: const SizedBox(width: 24, height: 24),
                  onPressed: () => _run(auth.loginTest),
                ),
              ],
            ],
            if (!AppConfig.requireLogin) ...[
              const SizedBox(height: Space.s24),
              TextButton(
                onPressed: _busy
                    ? null
                    : () async {
                        await auth.skip();
                        if (context.mounted && !widget.asGate && Navigator.canPop(context)) {
                          Navigator.pop(context);
                        }
                      },
                child: const Text('나중에 할게요'),
              ),
            ],
            const SizedBox(height: 96),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _BrandButton extends StatelessWidget {
  const _BrandButton({
    required this.background,
    required this.foreground,
    required this.label,
    required this.semanticsLabel,
    required this.icon,
    required this.onPressed,
    this.side,
  });

  final Color background;
  final Color foreground;
  final String label;
  final String semanticsLabel;
  final Widget icon;
  final VoidCallback onPressed;
  final BorderSide? side;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticsLabel,
      excludeSemantics: true,
      child: Material(
        color: background,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Radii.r12),
          side: side ?? BorderSide.none,
        ),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(Radii.r12),
          child: SizedBox(
            height: 64,
            width: double.infinity,
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              icon,
              const SizedBox(width: Space.s12),
              Text(
                label,
                style: AppText.button.copyWith(color: foreground),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
