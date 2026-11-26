import 'package:material_ui/material_ui.dart';

import '../state/app_store.dart';
import '../theme.dart';
import '../utils/keep_all.dart';
import '../widgets/illustrations.dart';
import '../widgets/todo_card.dart';
import 'result_screen.dart';

/// 챙길 일: 기한 가까운 순. 줄을 누르면 서류, 오른쪽 네모를 누르면 완료.
class TodoScreen extends StatelessWidget {
  const TodoScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final store = AppScope.of(context);
    final todos = store.pendingTodos;

    return Scaffold(
      appBar: AppBar(title: const Text('챙길 일')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Space.s16, Space.s4, Space.s16, Space.s32),
          children: [
            _Banner(
              illo: Illo.calendarDone,
              text: todos.isEmpty ? '챙길 일이 없어요' : '${todos.length}가지 남았어요',
            ),
            const SizedBox(height: Space.s16),
            if (todos.isNotEmpty)
              GroupedList(children: [
                for (final (todo, doc) in todos)
                  TodoRow(
                    todo: todo,
                    doc: doc,
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => ResultScreen(result: doc, fromHistory: true),
                    )),
                    onToggleDone: () {
                      store.toggleDone(todo);
                      ScaffoldMessenger.of(context)
                        ..hideCurrentSnackBar()
                        ..showSnackBar(SnackBar(
                          content: Text('"${todo.title}" 끝났어요'),
                          action: SnackBarAction(label: '되돌리기', onPressed: () => store.toggleDone(todo)),
                        ));
                    },
                  ),
              ]),
          ],
        ),
      ),
    );
  }
}

/// 화면 머리 그림 띠 (할 일·지난 서류 공통)
class _Banner extends StatelessWidget {
  const _Banner({required this.illo, required this.text});
  final Illo illo;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(Space.s24, Space.s12, Space.s16, Space.s12),
      decoration: BoxDecoration(color: AppColors.accentSoft, borderRadius: BorderRadius.circular(Radii.r24)),
      child: Row(children: [
        Expanded(child: Text(text.keepAll, style: AppText.heading2)),
        Illustration(illo, size: 88),
      ]),
    );
  }
}
