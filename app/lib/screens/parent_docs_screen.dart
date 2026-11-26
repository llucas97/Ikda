import 'package:material_ui/material_ui.dart';

import '../state/app_store.dart';
import '../theme.dart';
import '../utils/keep_all.dart';
import '../widgets/illustrations.dart';
import '../widgets/todo_card.dart';
import 'result_screen.dart';

/// 자녀 화면. 연결된 부모님 서류 중 보기 권한이 있는 것만.
class ParentDocsScreen extends StatelessWidget {
  const ParentDocsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final store = AppScope.of(context);
    final docs = store.familyDocs;
    final nav = Navigator.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('부모님 서류')),
      body: SafeArea(
        child: docs.isEmpty
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(Space.s24),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Illustration(Illo.folder, size: 120),
                    const SizedBox(height: Space.s16),
                    Text('볼 수 있는 부모님 서류가 없어요'.keepAll, textAlign: TextAlign.center, style: AppText.body),
                  ]),
                ),
              )
            : ListView(
                padding: const EdgeInsets.fromLTRB(Space.s16, Space.s8, Space.s16, Space.s32),
                children: [
                  Text('연결된 부모님이 나눠 준 서류예요'.keepAll, style: AppText.caption),
                  const SizedBox(height: Space.s12),
                  GroupedList(children: [
                    for (final d in docs)
                      DocRow(
                        doc: d,
                        onTap: () => nav.push(MaterialPageRoute<void>(
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
