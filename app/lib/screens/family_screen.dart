import 'package:material_ui/material_ui.dart';
import 'package:share_plus/share_plus.dart';

import '../models/family_link.dart';
import '../services/family_service.dart';
import '../services/speech.dart';
import '../state/app_store.dart';
import '../theme.dart';
import '../utils/keep_all.dart';
import 'family_permission_screen.dart';
import 'invite_code_screen.dart';
import 'join_screen.dart';
import 'parent_docs_screen.dart';
import 'relation_picker.dart';

const _spine = 36.0;

/// 우리 가족. 나는 가운데, 연결된 사람은 아래로 선으로 잇는다.
class FamilyScreen extends StatelessWidget {
  const FamilyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final store = AppScope.of(context);
    final user = AppScope.authOf(context).user;
    final raw = user?.name?.trim() ?? '';
    final meName = raw.isEmpty ? '나' : raw;
    final seesParents = store.links.any((l) => l.myRole == 'CHILD');
    return Scaffold(
      appBar: AppBar(title: const Text('우리 가족')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Space.s16, Space.s8, Space.s16, Space.s40),
          children: [
            Center(child: _Bubble(initial: _initial(meName), photoUrl: user?.profileImageUrl, size: 120, ring: true)),
            if (store.links.isEmpty) ...[
              const SizedBox(height: Space.s16),
              Text('아직 연결된 가족이 없어요'.keepAll, textAlign: TextAlign.center, style: AppText.body),
            ] else ...[
              const SizedBox(
                height: 36,
                width: double.infinity,
                child: CustomPaint(painter: _BridgePainter()),
              ),
              for (var i = 0; i < store.links.length; i++)
                _LinkedRow(link: store.links[i], last: i == store.links.length - 1),
            ],
            const SizedBox(height: Space.s24),
            FilledButton(onPressed: () => _invite(context), child: const Text('가족 초대하기')),
            const SizedBox(height: Space.s12),
            OutlinedButton(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const JoinScreen())),
              child: const Text('번호 넣기'),
            ),
            if (seesParents) ...[
              const SizedBox(height: Space.s12),
              OutlinedButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => const ParentDocsScreen()),
                ),
                child: const Text('부모님 서류'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _invite(BuildContext context) async {
    final role = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppColors.canvas,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Space.s16),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Text('나는 누구인가요?', style: AppText.heading2),
            const SizedBox(height: Space.s16),
            FilledButton(onPressed: () => Navigator.pop(ctx, 'CHILD'), child: const Text('나는 자녀예요')),
            const SizedBox(height: Space.s12),
            OutlinedButton(onPressed: () => Navigator.pop(ctx, 'SENIOR'), child: const Text('나는 부모예요')),
          ]),
        ),
      ),
    );
    if (role == null || !context.mounted) return;
    final picked = await Navigator.of(context).push<({String relation, String? nick, String? counter, String? counterNick})>(
      MaterialPageRoute(builder: (_) => InviteRelationScreen(myRole: role)),
    );
    if (picked == null || !context.mounted) return;
    try {
      final ticket = await AppScope.read(context).family!.createInvite(
            myRole: role,
            label: role == 'CHILD' ? picked.counterNick : picked.nick,
            relationCd: role == 'CHILD' ? picked.counter : picked.relation,
            counterRelationCd: role == 'CHILD' ? picked.relation : picked.counter,
            counterNickname: role == 'CHILD' ? picked.nick : picked.counterNick,
          );
      if (!context.mounted) return;
      await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => InviteCodeScreen(ticket: ticket)));
    } on FamilyException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.userMessage)));
      }
    }
  }
}

class _BridgePainter extends CustomPainter {
  const _BridgePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.ink
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    final spineX = _spine / 2;
    final midY = size.height * 0.45;
    canvas.drawLine(Offset(size.width / 2, 0), Offset(size.width / 2, midY), paint);
    canvas.drawLine(Offset(size.width / 2, midY), Offset(spineX, midY), paint);
    canvas.drawLine(Offset(spineX, midY), Offset(spineX, size.height), paint);
  }

  @override
  bool shouldRepaint(_BridgePainter old) => false;
}

class _SpinePainter extends CustomPainter {
  const _SpinePainter({required this.last});
  final bool last;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.ink
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    final x = size.width / 2;
    const join = 56.0;
    canvas.drawLine(Offset(x, 0), Offset(x, last ? join : size.height), paint);
    canvas.drawLine(Offset(x, join), Offset(size.width, join), paint);
  }

  @override
  bool shouldRepaint(_SpinePainter old) => old.last != last;
}

class _LinkedRow extends StatelessWidget {
  const _LinkedRow({required this.link, required this.last});
  final FamilyLink link;
  final bool last;

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SizedBox(width: _spine, child: CustomPaint(painter: _SpinePainter(last: last))),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(bottom: Space.s12),
            child: _MemberCard(link: link),
          ),
        ),
      ]),
    );
  }
}

class _MemberCard extends StatelessWidget {
  const _MemberCard({required this.link});
  final FamilyLink link;

  @override
  Widget build(BuildContext context) {
    final relation = link.relationLabel;
    final nick = link.nickname.trim();
    final showNick = nick.isNotEmpty && nick != relation;
    return Container(
      padding: const EdgeInsets.all(Space.s16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(Radii.r16),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _Bubble(initial: _initial(link.name.trim().isEmpty ? link.display : link.name), photoUrl: link.photoUrl, size: 80),
          const SizedBox(width: Space.s16),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(relation, style: AppText.heading2),
              if (showNick) Text(nick, style: AppText.body),
            ]),
          ),
        ]),
        const SizedBox(height: Space.s8),
        _action('별명·관계 바꾸기', () => editRelation(context, link)),
        if (link.isPrimary) _action('권한', () {
          Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => FamilyPermissionScreen(link: link)));
        }),
        _action('연결 끊기', () => confirmUnlink(context, link)),
      ]),
    );
  }

  Widget _action(String label, VoidCallback onPressed) {
    return TextButton(
      style: TextButton.styleFrom(
        alignment: Alignment.centerLeft,
        minimumSize: const Size.fromHeight(48),
        padding: EdgeInsets.zero,
      ),
      onPressed: onPressed,
      child: Text(label),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.initial, this.photoUrl, this.size = 80, this.ring = false});
  final String initial;
  final String? photoUrl;
  final double size;
  final bool ring;

  @override
  Widget build(BuildContext context) {
    final letter = Text(initial, style: size >= 100 ? AppText.heading1 : AppText.title);
    final fallback = Center(child: letter);
    final url = photoUrl;
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: AppColors.surface,
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.ink, width: ring ? 3 : 1.5),
      ),
      child: url == null || url.isEmpty
          ? fallback
          : Image.network(
              url,
              width: size,
              height: size,
              fit: BoxFit.cover,
              errorBuilder: (context, error, stackTrace) => fallback,
            ),
    );
  }
}

String _initial(String name) {
  final t = name.trim();
  if (t.isEmpty) return '나';
  return t.substring(0, 1);
}

Future<void> editRelation(BuildContext context, FamilyLink link) async {
  final options = link.myRole == 'CHILD' ? elderRelations : parentRelations;
  var selected = options.any((o) => o.$1 == link.relationCd) ? link.relationCd : null;
  final nick = TextEditingController(text: link.nickname == link.relationLabel ? '' : link.nickname);
  try {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.canvas,
      builder: (ctx) {
        final inset = MediaQuery.viewInsetsOf(ctx).bottom;
        final height = (MediaQuery.sizeOf(ctx).height - inset) * 0.92;
        return Padding(
          padding: EdgeInsets.only(bottom: inset),
          child: SizedBox(
            height: height,
            child: StatefulBuilder(
              builder: (ctx, setLocal) {
                return SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(Space.s16, Space.s24, Space.s16, Space.s16),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    const Text('별명·관계', style: AppText.heading2),
                    const SizedBox(height: Space.s12),
                    RelationPicker(
                      options: options,
                      selected: selected,
                      onPick: (c) => setLocal(() => selected = c),
                    ),
                    const SizedBox(height: Space.s12),
                    NicknameField(controller: nick, hint: '큰딸, 어머니'),
                    const SizedBox(height: Space.s16),
                    FilledButton(
                      onPressed: selected == null ? null : () => Navigator.pop(ctx, true),
                      child: const Text('저장'),
                    ),
                  ]),
                );
              },
            ),
          ),
        );
      },
    );
    if (saved != true || !context.mounted || selected == null) return;
    await AppScope.read(context).family!.updateRelation(link.linkId, label: nick.text.trim(), relationCd: selected);
    if (context.mounted) await AppScope.read(context).refreshFamily();
  } on FamilyException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.userMessage)));
    }
  } finally {
    nick.dispose();
  }
}

Future<void> confirmUnlink(BuildContext context, FamilyLink link) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      backgroundColor: AppColors.canvas,
      title: const Text('연결을 끊을까요?', style: AppText.heading2),
      content: Text('${link.display}와 서류를 더 이상 나누지 않아요'.keepAll, style: AppText.body),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('아니요')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('끊기')),
      ],
    ),
  );
  if (ok != true || !context.mounted) return;
  try {
    await AppScope.read(context).family!.unlink(link.linkId);
    if (context.mounted) await AppScope.read(context).refreshFamily();
  } on FamilyException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.userMessage)));
    }
  }
}

/// 초대 전에 관계와 별명을 고른다. 한 번에 한 질문만 보여 412×915 에 잘리지 않게 한다.
class InviteRelationScreen extends StatefulWidget {
  const InviteRelationScreen({super.key, required this.myRole});
  final String myRole;

  @override
  State<InviteRelationScreen> createState() => _InviteRelationScreenState();
}

class _InviteRelationScreenState extends State<InviteRelationScreen> {
  int _step = 0;
  bool _leaving = false;
  String? _parentSide;
  String? _elderSide;
  final _parentNick = TextEditingController();
  final _elderNick = TextEditingController();

  @override
  void dispose() {
    _parentNick.dispose();
    _elderNick.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final childInvites = widget.myRole == 'CHILD';
    final first = _step == 0;
    final question = first
        ? (childInvites ? '부모님은 나를 어떻게 부르나요?' : '나는 가족을 어떻게 부르나요?')
        : (childInvites ? '나는 부모님을 어떻게 부르나요?' : '가족은 나를 어떻게 부르나요?');
    final options = first ? parentRelations : elderRelations;
    final selected = first ? _parentSide : _elderSide;
    final nick = first ? _parentNick : _elderNick;
    final hint = first ? '큰딸, 막내아들' : '어머니, 아버지';
    return PopScope(
      canPop: first || _leaving,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop || !mounted) return;
        setState(() => _step = 0);
      },
      child: Scaffold(
        appBar: AppBar(title: Text(first ? '관계 1/2' : '관계 2/2')),
        body: ListView(
          padding: const EdgeInsets.all(Space.s16),
          children: [
            Text(question.keepAll, style: AppText.heading2),
            const SizedBox(height: Space.s12),
            RelationPicker(
              options: options,
              selected: selected,
              onPick: (c) => setState(() {
                if (first) {
                  _parentSide = c;
                } else {
                  _elderSide = c;
                }
              }),
            ),
            const SizedBox(height: Space.s12),
            NicknameField(controller: nick, hint: hint),
            const SizedBox(height: Space.s24),
            FilledButton(
              onPressed: first
                  ? (_parentSide == null ? null : () => setState(() => _step = 1))
                  : (_parentSide == null
                      ? null
                      : () {
                          final picked = (
                            relation: _parentSide!,
                            nick: _parentNick.text.trim().isEmpty ? null : _parentNick.text.trim(),
                            counter: _elderSide,
                            counterNick: _elderNick.text.trim().isEmpty ? null : _elderNick.text.trim(),
                          );
                          setState(() => _leaving = true);
                          WidgetsBinding.instance.addPostFrameCallback((_) {
                            if (mounted) Navigator.pop(context, picked);
                          });
                        }),
              child: Text(first ? '다음' : '번호 만들기'),
            ),
          ],
        ),
      ),
    );
  }
}

Future<void> shareInvite(String text) => Share.share(text);

Future<void> speakCode(String pretty) async {
  final speech = Speech();
  await speech.init(onDone: () {});
  await speech.speak(pretty.split('').join(' '));
}
