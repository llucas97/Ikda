import 'package:material_ui/material_ui.dart';

import '../services/scanner.dart';
import '../state/app_store.dart';
import '../theme.dart';
import '../utils/date_text.dart';
import '../utils/keep_all.dart';
import '../widgets/illustrations.dart';
import '../widgets/ph_icons.dart';
import '../widgets/todo_card.dart';
import 'account_sheet.dart';
import 'family_screen.dart';
import 'history_screen.dart';
import 'parent_docs_screen.dart';
import 'result_screen.dart';
import 'todo_screen.dart';

/// 홈: 인사 → 큰 "서류 찍기" → 챙길 일 → 지난 서류.
/// 글은 최소로, 그림과 칩으로 알아보게.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final store = AppScope.of(context);
    final todos = store.pendingTodos;
    final docs = store.documents;
    final nav = Navigator.of(context);

    void openTodos() => nav.push(MaterialPageRoute<void>(builder: (_) => const TodoScreen()));
    void openHistory() => nav.push(MaterialPageRoute<void>(builder: (_) => const HistoryScreen()));

    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Space.s16, Space.s8, Space.s16, Space.s40),
          children: [
            const _Header(),
            const SizedBox(height: Space.s8),
            const _Greeting(),
            const SizedBox(height: Space.s16),
            _CaptureButton(onTap: () => startDocumentCapture(context)),
            const SizedBox(height: Space.s12),
            OutlinedButton(
              onPressed: () => startGalleryCapture(context),
              child: const Text('사진첩에서 고르기'),
            ),
            if (store.links.any((l) => l.myRole == 'CHILD')) ...[
              const SizedBox(height: Space.s32),
              SectionHeader(
                title: '부모님 서류',
                onMore: () => nav.push(MaterialPageRoute<void>(builder: (_) => const ParentDocsScreen())),
              ),
              const SizedBox(height: Space.s8),
              if (store.familyDocs.isEmpty)
                const _EmptyPanel(illo: Illo.folder, text: '볼 수 있는 서류가 없어요')
              else
                GroupedList(children: [
                  for (final d in store.familyDocs.take(3))
                    DocRow(
                      doc: d,
                      onTap: () => nav.push(MaterialPageRoute<void>(
                          builder: (_) => ResultScreen(result: d, fromHistory: true))),
                    ),
                ]),
            ] else if (store.familyDocs.isNotEmpty) ...[
              const SizedBox(height: Space.s32),
              const SectionHeader(title: '자녀가 보냄'),
              const SizedBox(height: Space.s8),
              GroupedList(children: [
                for (final d in store.familyDocs.take(3))
                  DocRow(
                    doc: d,
                    onTap: () => nav.push(MaterialPageRoute<void>(
                        builder: (_) => ResultScreen(result: d, fromHistory: true))),
                  ),
              ]),
            ],
            const SizedBox(height: Space.s32),

            SectionHeader(title: '챙길 일', onMore: todos.isEmpty ? null : openTodos),
            const SizedBox(height: Space.s8),
            if (todos.isEmpty)
              const _EmptyPanel(illo: Illo.calendarDone, text: '챙길 일이 없어요')
            else
              GroupedList(children: [
                for (final (todo, doc) in todos.take(3))
                  TodoRow(
                    todo: todo,
                    doc: doc,
                    onTap: () => nav.push(MaterialPageRoute<void>(
                        builder: (_) => ResultScreen(result: doc, fromHistory: true))),
                  ),
              ]),
            const SizedBox(height: Space.s32),

            SectionHeader(title: '지난 서류', onMore: docs.isEmpty ? null : openHistory),
            const SizedBox(height: Space.s8),
            if (docs.isEmpty)
              const _EmptyPanel(illo: Illo.folder, text: '찍은 서류가 여기 모여요')
            else
              GroupedList(children: [
                for (final d in docs.take(2))
                  DocRow(
                    doc: d,
                    onTap: () => nav.push(MaterialPageRoute<void>(
                        builder: (_) => ResultScreen(result: d, fromHistory: true))),
                  ),
              ]),
          ],
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 64,
      child: Row(children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(Radii.r8),
          child: Image.asset('assets/brand/app_icon.png', width: 40, height: 40, fit: BoxFit.cover),
        ),
        const SizedBox(width: Space.s12),
        const Expanded(child: Text('읽다', style: AppText.title)),
        IconButton(
          tooltip: '계정',
          iconSize: 28,
          constraints: const BoxConstraints(minWidth: 56, minHeight: 56),
          onPressed: () => showAccountSheet(context),
          icon: const Icon(PhosphorIconsBold.user, color: AppColors.ink),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const FamilyScreen())),
          child: const Text('가족'),
        ),
      ]),
    );
  }
}

class _Greeting extends StatelessWidget {
  const _Greeting();

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    return Container(
      padding: const EdgeInsets.fromLTRB(Space.s24, Space.s16, Space.s16, Space.s16),
      decoration: BoxDecoration(color: AppColors.accentSoft, borderRadius: BorderRadius.circular(Radii.r24)),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${now.month}월 ${now.day}일 ${weekdayLong(now)}'.noBreak,
                style: AppText.caption.copyWith(color: AppColors.accent, fontWeight: FontWeight.w700)),
            const SizedBox(height: Space.s4),
            const Text('안녕하세요!', style: AppText.heading1),
            Text('서류를 찍어 보세요'.keepAll, style: AppText.body.copyWith(color: AppColors.inkSub)),
          ]),
        ),
        const Illustration(Illo.plant, size: 80),
      ]),
    );
  }
}

class _CaptureButton extends StatelessWidget {
  const _CaptureButton({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '서류 찍기',
      excludeSemantics: true,
      child: Material(
        color: AppColors.highlight,
        borderRadius: BorderRadius.circular(Radii.r24),
        child: InkWell(
          borderRadius: BorderRadius.circular(Radii.r24),
          splashColor: AppColors.highlightPressed,
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(Space.s24, Space.s32, Space.s24, Space.s24),
            child: Column(children: [
              const ScanBrackets(color: AppColors.ink, padding: 28, child: CameraDrawing(size: 124)),
              const SizedBox(height: Space.s16),
              Text('서류 찍기', style: AppText.display.copyWith(color: AppColors.ink)),
            ]),
          ),
        ),
      ),
    );
  }
}

class _EmptyPanel extends StatelessWidget {
  const _EmptyPanel({required this.illo, required this.text});
  final Illo illo;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Space.s16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(Radii.r16),
        border: Border.all(color: AppColors.line),
      ),
      child: Row(children: [
        Illustration(illo, size: 72),
        const SizedBox(width: Space.s16),
        Expanded(child: Text(text.keepAll, style: AppText.body.copyWith(color: AppColors.inkSub))),
      ]),
    );
  }
}
