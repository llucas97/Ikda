import 'package:material_ui/material_ui.dart';

import '../state/app_store.dart';
import '../theme.dart';
import '../utils/keep_all.dart';
import '../widgets/illustrations.dart';
import '../widgets/todo_card.dart';
import 'result_screen.dart';

/// 지난 서류 (최근 것이 위). 서류 종류는 그림으로 알아보게.
class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final docs = AppScope.of(context).documents;

    return Scaffold(
      appBar: AppBar(title: const Text('지난 서류')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Space.s16, Space.s4, Space.s16, Space.s32),
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(Space.s24, Space.s12, Space.s16, Space.s12),
              decoration:
                  BoxDecoration(color: AppColors.accentSoft, borderRadius: BorderRadius.circular(Radii.r24)),
              child: Row(children: [
                Expanded(
                  child: Text((docs.isEmpty ? '찍은 서류가 여기 모여요' : '서류 ${docs.length}장').keepAll,
                      style: AppText.heading2),
                ),
                const Illustration(Illo.folder, size: 88),
              ]),
            ),
            const SizedBox(height: Space.s16),
            if (docs.isNotEmpty)
              GroupedList(children: [
                for (final d in docs)
                  DocRow(
                    doc: d,
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => ResultScreen(result: d, fromHistory: true),
                    )),
                  ),
              ]),
          ],
        ),
      ),
    );
  }
}
