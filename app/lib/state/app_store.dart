import 'package:cross_file/cross_file.dart';
import 'package:flutter/widgets.dart';

import '../config.dart';
import '../models/document_result.dart';
import '../models/family_link.dart';
import '../services/analysis_service.dart';
import '../services/auth_service.dart';
import '../services/document_repository.dart';
import '../services/document_sync.dart';
import '../services/family_service.dart';
import '../services/reminders.dart';

/// 앱 전체 상태 (MVP라 외부 상태관리 패키지 없이 ChangeNotifier 하나로).
/// 바뀔 때마다 기기에 저장하고, 할 일 알림을 맞춘다.
class AppStore extends ChangeNotifier {
  AppStore({
    required this.analysisService,
    required this.repository,
    required this.reminders,
    this.family,
    this.sync,
  });

  final AnalysisService analysisService;
  final DocumentRepository repository;
  final Reminders reminders;
  final FamilyService? family;
  final DocumentSync? sync;
  final List<DocumentResult> _documents = [];
  List<FamilyLink> links = [];
  List<DocumentResult> familyDocs = [];
  String? pendingJoinToken;
  List<XFile> pendingShare = [];

  List<DocumentResult> get documents => List.unmodifiable(_documents);

  /// 앱 시작 때 한 번: 저장본 읽기 (예약된 알림은 기기에 남아 있으므로 다시 맞추지 않는다)
  Future<void> load() async {
    _documents
      ..clear()
      ..addAll(await repository.load());
    if (AppConfig.seedDemo && AppConfig.useMock) {
      final api = family;
      if (api is MockFamilyService) api.seedDemoFamily();
      if (_documents.isEmpty) _documents.addAll(demoDocuments());
      if (api != null) {
        try {
          final snap = await api.list();
          links = snap.links;
          familyDocs = await api.familyDocuments();
        } catch (e) {
          debugPrint('family: $e');
        }
      }
    }
    notifyListeners();
  }

  /// 끝내지 않은 할 일, 기한 가까운 순
  List<(TodoItem, DocumentResult)> get pendingTodos {
    final list = <(TodoItem, DocumentResult)>[
      for (final d in _documents)
        for (final t in d.todos)
          if (!t.done) (t, d),
    ];
    list.sort((a, b) {
      final ad = a.$1.dueDate, bd = b.$1.dueDate;
      if (ad == null && bd == null) return 0;
      if (ad == null) return 1;
      if (bd == null) return -1;
      return ad.compareTo(bd);
    });
    return list;
  }

  DocumentResult? _docOf(TodoItem t) => _documents.where((d) => d.todos.contains(t)).firstOrNull;

  Future<void> _persist() => repository.save(_documents);

  Future<void> refreshFamily() async {
    final api = family;
    if (api == null) return;
    try {
      final snap = await api.list();
      links = snap.links;
      familyDocs = await api.familyDocuments();
    } catch (e) {
      debugPrint('family: $e');
    }
    notifyListeners();
  }

  Future<void> syncNow() async {
    final engine = sync;
    if (engine == null) return;
    await engine.pull();
    await load();
  }

  Future<void> onLogin() async {
    await refreshFamily();
    await sync?.bootstrap();
    await load();
  }

  Future<void> onLogout() async {
    await sync?.clearQueue();
    links = [];
    familyDocs = [];
    pendingJoinToken = null;
    pendingShare = [];
    notifyListeners();
  }

  Future<DocumentResult> analyze(List<XFile> images, {int? linkId, bool save = false}) async {
    final result = await analysisService.analyze(images, save: save, linkId: linkId);
    if (linkId != null) {
      familyDocs.insert(0, result);
      notifyListeners();
      return result;
    }
    _documents.insert(0, result);
    notifyListeners();
    await _persist();
    for (final t in result.todos) {
      await reminders.sync(t, result);
    }
    return result;
  }

  Future<void> toggleDone(TodoItem t) async {
    t.done = !t.done;
    notifyListeners();
    await _persist();
    final d = _docOf(t);
    if (d != null) {
      await reminders.sync(t, d); // 끝냈으면 지우고, 되돌리면 다시
      await sync?.enqueue({'kind': 'todo', 'id': d.id, 'todoId': t.id, 'done': t.done, 'remind': t.remind});
    }
  }

  /// 알림 켜기/끄기. 켰을 때 예약된 첫 알림 시각을 돌려준다.
  Future<DateTime?> toggleRemind(TodoItem t) async {
    t.remind = !t.remind;
    notifyListeners();
    await _persist();
    final d = _docOf(t);
    if (d == null) return null;
    await sync?.enqueue({'kind': 'todo', 'id': d.id, 'todoId': t.id, 'done': t.done, 'remind': t.remind});
    return reminders.sync(t, d);
  }

  Future<void> deleteDocument(DocumentResult d) async {
    _documents.remove(d);
    notifyListeners();
    await _persist();
    for (final t in d.todos) {
      await reminders.cancel(t);
    }
    await sync?.enqueue({'kind': 'delete', 'id': d.id});
  }

  Future<void> markSeen(DocumentResult d) async {
    d.seen = true;
    notifyListeners();
    await _persist();
    await sync?.enqueue({'kind': 'seen', 'id': d.id});
  }
}

/// SEED_DEMO 미리보기용 서류 두 건. 기기는 저장하지 않는다.
List<DocumentResult> demoDocuments() {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final billDue = today.add(const Duration(days: 9));
  final visit = today.add(const Duration(days: 2));
  return [
    DocumentResult(
      id: 'doc_seed_bill',
      type: DocType.bill,
      title: '한국전력 전기요금 고지서',
      summary: '이번 달 전기요금이 32,400원 나왔어요. ${billDue.month}월 ${billDue.day}일까지 내시면 돼요.',
      keyPoints: const ['청구 금액: 32,400원', '자동이체: 신청 안 되어 있음'],
      amount: 32400,
      dueDate: billDue,
      todos: [
        TodoItem(id: 'doc_seed_bill_t1', title: '전기요금 내기', dueDate: billDue, detail: '은행, 편의점, 한전 앱에서 낼 수 있어요'),
      ],
      createdAt: now,
    ),
    DocumentResult(
      id: 'doc_seed_hospital',
      type: DocType.hospital,
      title: '건강검진 예약 안내',
      summary: '건강검진이 예약되어 있어요. 검사 전날 밤부터 음식을 드시면 안 돼요.',
      keyPoints: const ['장소: 시민병원 3층', '신분증 꼭 챙기기'],
      dueDate: visit,
      warnings: const ['검사 전날 밤 9시 이후로는 물 말고 아무것도 드시지 마세요.'],
      todos: [
        TodoItem(id: 'doc_seed_hospital_t1', title: '건강검진 받으러 가기', dueDate: visit, detail: '오전 8시 30분까지'),
      ],
      createdAt: now.subtract(const Duration(hours: 2)),
    ),
  ];
}

class AppScope extends InheritedNotifier<AppStore> {
  const AppScope({super.key, required AppStore store, required this.auth, required super.child})
      : super(notifier: store);

  final AuthService auth;

  /// build 안에서: 상태가 바뀌면 다시 그림
  static AppStore of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;

  static AuthService authOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.auth;

  /// 이벤트 핸들러 / 비동기 코드에서: 구독 없이 읽기만
  static AppStore read(BuildContext context) =>
      context.getInheritedWidgetOfExactType<AppScope>()!.notifier!;
}
