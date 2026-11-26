import 'package:material_ui/material_ui.dart';

import '../models/document_result.dart';
import '../services/family_service.dart';
import '../services/speech.dart';
import '../state/app_store.dart';
import '../theme.dart';
import '../utils/date_text.dart';
import '../utils/keep_all.dart';
import '../widgets/ph_icons.dart';
import '../widgets/todo_card.dart';

/// 결과: 무슨 서류 → 언제·얼마 → 한마디(듣기) → 할 일 → 주의 → (접힌) 자세히.
class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key, required this.result, this.fromHistory = false});
  final DocumentResult result;
  final bool fromHistory;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  final Speech _speech = Speech();
  bool _speaking = false;
  bool _showDetail = false;

  @override
  void initState() {
    super.initState();
    _speech.init(onDone: () {
      if (mounted) setState(() => _speaking = false);
    });
  }

  @override
  void dispose() {
    _speech.stop();
    super.dispose();
  }

  Future<void> _shareWithFamily(BuildContext context) async {
    final store = AppScope.read(context);
    final api = store.family;
    if (api == null || store.links.where((l) => l.myRole == 'SENIOR').isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('가족을 연결하면 보낼 수 있어요')));
      return;
    }
    try {
      final sent = await api.shareDocument(widget.result.id);
      if (!context.mounted) return;
      final who = sent.isEmpty ? '가족' : sent.map((e) => e.label).join(', ');
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$who에게 보냈어요')));
    } on FamilyException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.userMessage)));
      }
    }
  }

  Future<void> _toggleSpeak() async {
    if (_speaking) {
      await _speech.stop();
      setState(() => _speaking = false);
    } else {
      setState(() => _speaking = true);
      await _speech.speak(widget.result.toSpeech());
    }
  }

  Future<void> _toggleRemind(AppStore store, TodoItem t) async {
    final messenger = ScaffoldMessenger.of(context);
    final at = await store.toggleRemind(t);
    if (!mounted) return;
    final String msg;
    if (!t.remind) {
      msg = '알림을 껐어요';
    } else if (at != null) {
      msg = '${at.month}월 ${at.day}일 아침 9시에 알려 드릴게요';
    } else if (t.dueDate != null && t.dueDate!.isBefore(DateTime.now())) {
      msg = '기한이 지나서 알림을 맞출 수 없어요';
    } else {
      msg = '알림이 꺼져 있어요.\n휴대폰 설정에서 알림을 허용해 주세요.';
    }
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _confirmDelete(AppStore store) async {
    final nav = Navigator.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.canvas,
        surfaceTintColor: Colors.transparent,
        title: const Text('이 서류를 지울까요?'),
        content: Text('할 일과 알림도 함께 없어져요.'.keepAll, style: AppText.body),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('그대로 두기')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('지우기')),
        ],
      ),
    );
    if (ok != true) return;
    await store.deleteDocument(widget.result);
    nav.pop();
  }

  static String _dateLabel(DocType t) => switch (t) {
        DocType.bill => '내는 날',
        DocType.medicine => '다 드시는 날',
        DocType.hospital => '가는 날',
        _ => '기한',
      };

  @override
  Widget build(BuildContext context) {
    final store = AppScope.of(context);
    final r = widget.result;
    final showShare = r.source != 'FAMILY' && r.access == 'OWNER';
    final mainDue = r.mainDue;
    final firstDue = r.todos.where((t) => t.dueDate != null).firstOrNull;
    final amount = amountOf(r);
    final dot = r.summary.indexOf('. ');
    final lead = dot > 0 ? r.summary.substring(0, dot + 1) : r.summary;
    final rest = dot > 0 ? r.summary.substring(dot + 2).trim() : '';

    return Scaffold(
      appBar: AppBar(
        title: const Text('정리했어요'),
        actions: [
          if (widget.fromHistory)
            TextButton.icon(
              onPressed: () => _confirmDelete(store),
              icon: const Icon(PhosphorIconsBold.trash, size: 24),
              label: const Text('지우기'),
            ),
          const SizedBox(width: Space.s8),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(Space.s16, Space.s4, Space.s16, Space.s32),
        children: [
          // ── 무슨 서류 ──
          _Panel(
            child: Row(children: [
              DocThumb(type: r.type, size: 80),
              const SizedBox(width: Space.s16),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(r.type.label.noBreak,
                      style: AppText.caption.copyWith(color: AppColors.accent, fontWeight: FontWeight.w700)),
                  Text(r.title.keepAll, style: AppText.heading2),
                  if (r.sentByLabel != null)
                    Text(sentByPhrase(r.sentByLabel!).noBreak, style: AppText.caption.copyWith(color: AppColors.ink)),
                  Text('${formatKoreanDate(r.createdAt)} 찍음'.noBreak, style: AppText.caption),
                ]),
              ),
            ]),
          ),

          // ── 언제 · 얼마 ──
          if (mainDue != null) ...[
            const SizedBox(height: Space.s12),
            _Panel(
              padding: const EdgeInsets.symmetric(vertical: Space.s16),
              child: IntrinsicHeight(
                child: Row(children: [
                  Expanded(
                    child: _Fact(
                      label: _dateLabel(r.type),
                      value: '${mainDue.month}월 ${mainDue.day}일',
                      sub: weekdayLong(mainDue),
                      emphasis: true,
                    ),
                  ),
                  const VerticalDivider(width: 1),
                  Expanded(
                    child: amount != null
                        ? _Fact(label: '금액', value: amount, emphasis: true)
                        : _Fact(
                            label: '남은 날',
                            value: chipText(firstDue ?? TodoItem(id: '', title: '', dueDate: mainDue)),
                            emphasis: true),
                  ),
                ]),
              ),
            ),
          ],

          // ── 한마디 + 듣기 ──
          const SizedBox(height: Space.s12),
          Container(
            padding: const EdgeInsets.fromLTRB(Space.s16, Space.s16, Space.s12, Space.s16),
            decoration: BoxDecoration(
              color: AppColors.accentSoft,
              borderRadius: BorderRadius.circular(Radii.r16),
              border: Border.all(color: AppColors.accent, width: 1.5),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(lead.keepAll, style: AppText.title.copyWith(color: AppColors.accentPressed)),
                  if (rest.isNotEmpty) ...[
                    const SizedBox(height: Space.s4),
                    Text(rest.keepAll, style: AppText.caption.copyWith(color: AppColors.ink)),
                  ],
                ]),
              ),
              const SizedBox(width: Space.s8),
              _ListenButton(speaking: _speaking, onTap: _toggleSpeak),
            ]),
          ),

          // ── 해야 할 일 ──
          if (r.todos.isNotEmpty) ...[
            const SizedBox(height: Space.s32),
            const SectionHeader(title: '해야 할 일'),
            const SizedBox(height: Space.s8),
            GroupedList(children: [
              for (final t in r.todos)
                _ResultTodo(
                  todo: t,
                  onToggleDone: () => store.toggleDone(t),
                  onToggleRemind: () => _toggleRemind(store, t),
                ),
            ]),
          ],

          // ── 꼭 확인하세요 ──
          if (r.caution != null) ...[
            const SizedBox(height: Space.s32),
            const SectionHeader(title: '꼭 확인하세요'),
            const SizedBox(height: Space.s8),
            Container(
              padding: const EdgeInsets.all(Space.s16),
              decoration: BoxDecoration(
                color: AppColors.warnBg,
                borderRadius: BorderRadius.circular(Radii.r16),
                border: Border.all(color: AppColors.warnLine, width: 1.5),
              ),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Icon(PhosphorIconsBold.warning, size: 32, color: AppColors.warnText),
                const SizedBox(width: Space.s12),
                Expanded(
                  child: Text(r.caution!.keepAll,
                      style: AppText.body.copyWith(color: AppColors.warnText, fontWeight: FontWeight.w700)),
                ),
              ]),
            ),
          ],

          // ── 자세한 내용 (접어 둠) ──
          if (r.keyPoints.isNotEmpty) ...[
            const SizedBox(height: Space.s24),
            _Panel(
              padding: EdgeInsets.zero,
              child: Column(children: [
                InkWell(
                  borderRadius: BorderRadius.circular(Radii.r16),
                  onTap: () => setState(() => _showDetail = !_showDetail),
                  child: SizedBox(
                    height: 64,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: Space.s16),
                      child: Row(children: [
                        const Icon(PhosphorIconsBold.fileText, size: 24, color: AppColors.inkSub),
                        const SizedBox(width: Space.s12),
                        const Expanded(child: Text('자세히 보기', style: AppText.title)),
                        Icon(_showDetail ? PhosphorIconsBold.caretUp : PhosphorIconsBold.caretDown,
                            size: 24, color: AppColors.inkSub),
                      ]),
                    ),
                  ),
                ),
                AnimatedSize(
                  duration: const Duration(milliseconds: 300),
                  curve: kEase,
                  alignment: Alignment.topCenter,
                  child: !_showDetail
                      ? const SizedBox(width: double.infinity)
                      : Column(children: [
                          for (final p in r.keyPoints) ...[
                            const Divider(indent: Space.s16, endIndent: Space.s16),
                            _KeyPoint(text: p),
                          ],
                        ]),
                ),
              ]),
            ),
          ],
        ],
      ),
      bottomNavigationBar: ColoredBox(
        color: AppColors.canvas,
        child: SafeArea(
          top: false,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Divider(),
            Padding(
              padding: const EdgeInsets.all(Space.s16),
              child: showShare
                  ? Row(children: [
                      Expanded(
                        flex: 2,
                        child: OutlinedButton(
                          onPressed: () async {
                            if (!widget.fromHistory) await AppScope.read(context).markSeen(widget.result);
                            if (context.mounted) Navigator.of(context).popUntil((route) => route.isFirst);
                          },
                          child: Text(widget.fromHistory ? '돌아가기' : '다 봤어요'),
                        ),
                      ),
                      const SizedBox(width: Space.s12),
                      Expanded(
                        flex: 3,
                        child: FilledButton.icon(
                          icon: const Icon(PhosphorIconsBold.paperPlaneTilt, size: 24),
                          label: Text('자녀에게 보내기'.noBreak, maxLines: 1),
                          onPressed: () => _shareWithFamily(context),
                        ),
                      ),
                    ])
                  : OutlinedButton(
                      onPressed: () async {
                        if (!widget.fromHistory) await AppScope.read(context).markSeen(widget.result);
                        if (context.mounted) Navigator.of(context).popUntil((route) => route.isFirst);
                      },
                      child: Text(widget.fromHistory ? '돌아가기' : '다 봤어요'),
                    ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.child, this.padding = const EdgeInsets.all(Space.s16)});
  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) => Container(
        padding: padding,
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(Radii.r16),
          border: Border.all(color: AppColors.line),
        ),
        child: child,
      );
}

class _Fact extends StatelessWidget {
  const _Fact({required this.label, required this.value, this.sub, this.emphasis = false});
  final String label;
  final String value;
  final String? sub;
  final bool emphasis;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.s16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label.noBreak, style: AppText.caption),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: emphasis
              ? HighlightMark(
                  child: Text(value.noBreak,
                      style: AppText.heading1.copyWith(color: AppColors.ink, fontFeatures: kTabular)),
                )
              : Text(value.noBreak,
                  style: AppText.heading1.copyWith(color: AppColors.ink, fontFeatures: kTabular)),
        ),
        if (sub != null) Text(sub!, style: AppText.caption.copyWith(color: AppColors.ink)),
      ]),
    );
  }
}

class _ListenButton extends StatelessWidget {
  const _ListenButton({required this.speaking, required this.onTap});
  final bool speaking;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: speaking ? '그만 듣기' : '소리로 듣기',
      excludeSemantics: true,
      child: Material(
        color: AppColors.accent,
        borderRadius: BorderRadius.circular(Radii.r12),
        child: InkWell(
          borderRadius: BorderRadius.circular(Radii.r12),
          onTap: onTap,
          child: SizedBox(
            width: 72,
            height: 72,
            child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(speaking ? PhosphorIconsBold.stop : PhosphorIconsBold.speakerHigh,
                  size: 28, color: AppColors.onAccent),
              Text(speaking ? '멈춤' : '듣기',
                  style: AppText.chip.copyWith(color: AppColors.onAccent)),
            ]),
          ),
        ),
      ),
    );
  }
}

class _ResultTodo extends StatelessWidget {
  const _ResultTodo({required this.todo, required this.onToggleDone, required this.onToggleRemind});
  final TodoItem todo;
  final VoidCallback onToggleDone;
  final VoidCallback onToggleRemind;

  @override
  Widget build(BuildContext context) {
    final due = todo.dueDate;
    return Padding(
      padding: const EdgeInsets.all(Space.s16),
      child: Column(children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(color: AppColors.accentSoft, borderRadius: BorderRadius.circular(Radii.r12)),
            child: const Icon(PhosphorIconsBold.calendarBlank, size: 28, color: AppColors.accent),
          ),
          const SizedBox(width: Space.s12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(todo.title.keepAll,
                  style: AppText.title.copyWith(
                    color: todo.done ? AppColors.inkSub : AppColors.ink,
                    decoration: todo.done ? TextDecoration.lineThrough : null,
                  )),
              if (due != null) ...[
                const SizedBox(height: Space.s4),
                Row(children: [
                  StatusChip(todo: todo),
                  const SizedBox(width: Space.s8),
                  Flexible(
                    child: HighlightMark(
                      child: Text(formatKoreanDate(due).noBreak, style: AppText.caption.copyWith(color: AppColors.ink)),
                    ),
                  ),
                ]),
              ],
              if (todo.detail != null) ...[
                const SizedBox(height: Space.s4),
                Text(todo.detail!.keepAll, style: AppText.caption),
              ],
            ]),
          ),
        ]),
        const SizedBox(height: Space.s12),
        Row(children: [
          if (due != null) ...[
            Expanded(
              child: _SmallToggle(
                on: todo.remind,
                icon: todo.remind ? PhosphorIconsBold.bellRinging : PhosphorIconsBold.bellSlash,
                label: todo.remind ? '하루 전 알림' : '알림 꺼짐',
                onTap: onToggleRemind,
              ),
            ),
            const SizedBox(width: Space.s8),
          ],
          Expanded(
            child: _SmallToggle(
              on: todo.done,
              icon: PhosphorIconsBold.check,
              label: '다 했어요',
              onTap: onToggleDone,
              filledWhenOn: true,
            ),
          ),
        ]),
      ]),
    );
  }
}

class _SmallToggle extends StatelessWidget {
  const _SmallToggle({
    required this.on,
    required this.icon,
    required this.label,
    required this.onTap,
    this.filledWhenOn = false,
  });
  final bool on;
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool filledWhenOn;

  @override
  Widget build(BuildContext context) {
    final filled = filledWhenOn && on;
    final bg = filled ? AppColors.accent : (on ? AppColors.accentSoft : AppColors.surface);
    final fg = filled ? AppColors.onAccent : (on ? AppColors.accent : AppColors.inkSub);
    return Semantics(
      button: true,
      toggled: on,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: bg,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Radii.r12),
          side: BorderSide(color: on ? AppColors.accent : AppColors.control, width: 1.5),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(Radii.r12),
          onTap: onTap,
          child: SizedBox(
            height: 56,
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(icon, size: 22, color: fg),
              const SizedBox(width: Space.s8),
              Flexible(child: Text(label.noBreak, maxLines: 1, style: AppText.chip.copyWith(color: fg))),
            ]),
          ),
        ),
      ),
    );
  }
}

class _KeyPoint extends StatelessWidget {
  const _KeyPoint({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final i = text.indexOf(':');
    final has = i > 0 && i < text.length - 1;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.s16, vertical: Space.s12),
      child: SizedBox(
        width: double.infinity,
        child: has
            ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(text.substring(0, i).trim().keepAll, style: AppText.caption),
                Text(text.substring(i + 1).trim().keepAll,
                    style: AppText.body.copyWith(fontWeight: FontWeight.w700, fontFeatures: kTabular)),
              ])
            : Text(text.keepAll, style: AppText.body),
      ),
    );
  }
}
