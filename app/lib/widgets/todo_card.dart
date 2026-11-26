import 'package:material_ui/material_ui.dart';

import '../models/document_result.dart';
import '../theme.dart';
import '../utils/date_text.dart';
import '../utils/keep_all.dart';
import 'illustrations.dart';
import 'ph_icons.dart';

/// 금액 표시 ("32,400원"). 서버가 준 amount 만 쓴다 (글에서 숫자를 긁어내지 않음).
/// 할 일을 주면, 그 할 일이 서류의 대표 기한과 같은 날일 때만 금액을 붙인다.
String? amountOf(DocumentResult d, [TodoItem? t]) {
  final a = d.amount;
  if (a == null) return null;
  // 할 일 줄에는: 할 일이 하나뿐이거나, 그 할 일 기한이 서류의 대표 기한일 때만
  if (t != null && d.todos.length > 1 && (t.dueDate == null || t.dueDate != d.mainDue)) return null;
  return formatWon(a);
}

enum Urgency { urgent, soon, later, done }

Urgency urgencyOf(TodoItem t) {
  if (t.done) return Urgency.done;
  final due = t.dueDate;
  if (due == null) return Urgency.later;
  final n = DateTime.now();
  final diff = DateTime(due.year, due.month, due.day).difference(DateTime(n.year, n.month, n.day)).inDays;
  if (diff <= 3) return Urgency.urgent;
  if (diff <= 30) return Urgency.soon;
  return Urgency.later;
}

String chipText(TodoItem t) {
  if (t.done) return '다 했어요';
  final due = t.dueDate;
  if (due == null) return '날짜 없음';
  final n = DateTime.now();
  final diff = DateTime(due.year, due.month, due.day).difference(DateTime(n.year, n.month, n.day)).inDays;
  if (diff > 30) return due.month != n.month ? '다음 달' : '$diff일 남음';
  return ddayText(due);
}

/// 남은 기간 칩. 급함=주홍 바탕 흰 글자, 여유=옅은 먹색 바탕, 먼 일·끝낸 일=중립. 색과 함께 글자가 상태를 말한다.
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.todo, this.width});
  final TodoItem todo;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final u = urgencyOf(todo);
    final (bg, fg) = switch (u) {
      Urgency.urgent => (AppColors.urgent, AppColors.onAccent),
      Urgency.soon => (AppColors.accentSoft, AppColors.accent),
      Urgency.later => (AppColors.neutralSoft, AppColors.inkSub),
      Urgency.done => (AppColors.neutralSoft, AppColors.inkSub),
    };
    return Container(
      width: width,
      constraints: const BoxConstraints(minHeight: 40),
      padding: const EdgeInsets.symmetric(horizontal: Space.s8, vertical: Space.s8),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(Radii.r8)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (u == Urgency.done) ...[
            Icon(PhosphorIconsBold.check, size: 18, color: fg),
            const SizedBox(width: Space.s4),
          ],
          Flexible(child: Text(chipText(todo).noBreak, maxLines: 1, style: AppText.chip.copyWith(color: fg))),
        ],
      ),
    );
  }
}

/// 흰 면 하나에 줄을 묶는 목록 (카드 반복·카드 속 카드 없이)
class GroupedList extends StatelessWidget {
  const GroupedList({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(Radii.r16),
        border: Border.all(color: AppColors.line),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(children: [
        for (var i = 0; i < children.length; i++) ...[
          if (i > 0) const Divider(indent: Space.s16, endIndent: Space.s16),
          children[i],
        ],
      ]),
    );
  }
}

/// 섹션 머리: 제목 + (선택) "전체" 링크
class SectionHeader extends StatelessWidget {
  const SectionHeader({super.key, required this.title, this.onMore, this.moreLabel = '전체'});
  final String title;
  final VoidCallback? onMore;
  final String moreLabel;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 48,
      child: Row(children: [
        Expanded(child: Text(title, style: AppText.heading2)),
        if (onMore != null)
          TextButton(
            onPressed: onMore,
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Text(moreLabel),
              const SizedBox(width: Space.s4),
              const Icon(PhosphorIconsBold.caretRight, size: 18),
            ]),
          ),
      ]),
    );
  }
}

/// 할 일 한 줄 (홈·할 일 화면): [상태 칩] 제목 / 금액·날짜 [완료 또는 >]
class TodoRow extends StatelessWidget {
  const TodoRow({super.key, required this.todo, required this.doc, this.onTap, this.onToggleDone});
  final TodoItem todo;
  final DocumentResult doc;
  final VoidCallback? onTap;
  final VoidCallback? onToggleDone;

  @override
  Widget build(BuildContext context) {
    final amount = amountOf(doc, todo);
    final date = todo.dueDate == null ? null : formatKoreanDate(todo.dueDate!);
    // 금액과 날짜는 줄을 나눠서 (한 줄에 붙이면 좁은 폭에서 '·' 뒤로 어색하게 꺾인다)
    final sub = [if (amount != null) amount.noBreak, if (date != null) date.noBreak].join('\n');
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.s16, Space.s16, Space.s8, Space.s16),
          child: Row(children: [
            StatusChip(todo: todo, width: 96),
            const SizedBox(width: Space.s12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(todo.title.keepAll,
                    style: AppText.title.copyWith(
                      color: todo.done ? AppColors.inkSub : AppColors.ink,
                      decoration: todo.done ? TextDecoration.lineThrough : null,
                    )),
                if (sub.isNotEmpty)
                  Text(sub, style: AppText.caption.copyWith(fontFeatures: kTabular)),
              ]),
            ),
            if (onToggleDone != null)
              DoneButton(done: todo.done, onTap: onToggleDone!)
            else
              const SizedBox(
                width: 40,
                child: Icon(PhosphorIconsBold.caretRight, size: 24, color: AppColors.inkSub),
              ),
          ]),
        ),
      ),
    );
  }
}

/// 네모 + "완료" (누르는 영역 64×64)
class DoneButton extends StatelessWidget {
  const DoneButton({super.key, required this.done, required this.onTap});
  final bool done;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      checked: done,
      label: '다 했어요',
      excludeSemantics: true,
      child: InkResponse(
        onTap: onTap,
        radius: 32,
        child: SizedBox(
          width: 64,
          height: 64,
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              curve: kEase,
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: done ? AppColors.accent : AppColors.surface,
                borderRadius: BorderRadius.circular(Radii.r8),
                border: Border.all(color: done ? AppColors.accent : AppColors.control, width: 2),
              ),
              child: done ? const Icon(PhosphorIconsBold.check, size: 22, color: AppColors.onAccent) : null,
            ),
            Text('완료', style: AppText.caption.copyWith(fontSize: 18, height: 24 / 18)),
          ]),
        ),
      ),
    );
  }
}

/// 서류 한 줄 (홈·지난 서류): [그림] 제목 / 날짜 >
class DocRow extends StatelessWidget {
  const DocRow({super.key, required this.doc, required this.onTap});
  final DocumentResult doc;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.s12, Space.s12, Space.s8, Space.s12),
          child: Row(children: [
            DocThumb(type: doc.type, size: 72),
            const SizedBox(width: Space.s16),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(doc.title.keepAll, style: AppText.title),
                if (doc.sentByLabel != null)
                  Text(sentByPhrase(doc.sentByLabel!).noBreak, style: AppText.caption.copyWith(color: AppColors.ink)),
                Text('${doc.type.label} · ${formatKoreanDate(doc.createdAt)}'.noBreakParts,
                    style: AppText.caption),
              ]),
            ),
            const SizedBox(
              width: 40,
              child: Icon(PhosphorIconsBold.caretRight, size: 24, color: AppColors.inkSub),
            ),
          ]),
        ),
      ),
    );
  }
}

/// 회청 칸 안의 서류 그림
class DocThumb extends StatelessWidget {
  const DocThumb({super.key, required this.type, this.size = 72});
  final DocType type;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: AppColors.accentSoft, borderRadius: BorderRadius.circular(Radii.r12)),
      alignment: Alignment.center,
      child: Illustration(illoFor(type), size: size * 0.8),
    );
  }
}
