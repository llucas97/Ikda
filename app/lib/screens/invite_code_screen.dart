import 'dart:async';

import 'package:material_ui/material_ui.dart';

import '../models/family_link.dart';
import '../state/app_store.dart';
import '../theme.dart';
import 'family_screen.dart';

/// 6자리 번호를 크게. 3초마다 연결됐는지 본다.
class InviteCodeScreen extends StatefulWidget {
  const InviteCodeScreen({super.key, required this.ticket});
  final InviteTicket ticket;

  @override
  State<InviteCodeScreen> createState() => _InviteCodeScreenState();
}

class _InviteCodeScreenState extends State<InviteCodeScreen> {
  Timer? _timer;
  bool _linked = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _poll());
  }

  Future<void> _poll() async {
    await AppScope.read(context).refreshFamily();
    if (!mounted) return;
    if (AppScope.read(context).links.isNotEmpty) {
      setState(() => _linked = true);
      _timer?.cancel();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final left = widget.ticket.expiresAt?.difference(DateTime.now().toUtc());
    final minutes = left == null ? 30 : left.inMinutes.clamp(0, 30);
    return Scaffold(
      appBar: AppBar(title: const Text('가족 초대')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Space.s16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text(_linked ? '연결됐어요' : '이 번호를 가족에게 알려 주세요', style: AppText.heading2),
            const SizedBox(height: Space.s24),
            FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(widget.ticket.pretty, textAlign: TextAlign.center, style: AppText.display.copyWith(fontSize: 56, height: 1.1)),
            ),
            const SizedBox(height: Space.s12),
            Text('$minutes분 동안만 쓸 수 있어요', textAlign: TextAlign.center, style: AppText.caption),
            const Spacer(),
            FilledButton(onPressed: () => shareInvite(widget.ticket.shareText), child: const Text('카톡으로 보내기')),
            const SizedBox(height: Space.s12),
            OutlinedButton(
              style: OutlinedButton.styleFrom(
                backgroundColor: AppColors.canvas,
                foregroundColor: AppColors.ink,
                surfaceTintColor: Colors.transparent,
                side: const BorderSide(color: AppColors.ink, width: 2),
                minimumSize: const Size.fromHeight(64),
              ),
              onPressed: () => speakCode(widget.ticket.pretty),
              child: const Text('번호 읽어 주기'),
            ),
          ]),
        ),
      ),
    );
  }
}
