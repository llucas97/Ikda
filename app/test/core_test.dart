import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ilgeodeurim/models/document_result.dart';
import 'package:ilgeodeurim/services/analysis_service.dart';
import 'package:ilgeodeurim/services/document_repository.dart';
import 'package:ilgeodeurim/services/reminders.dart';
import 'package:ilgeodeurim/state/app_store.dart';
import 'package:ilgeodeurim/widgets/todo_card.dart';

const serverJson = {
  'id': 'doc_1',
  'docType': 'government',
  'title': '주민센터 안내문',
  'oneLiner': '서류를 내셔야 해요.',
  'amount': 32400,
  'dueDate': '2026-11-25',
  'todos': [
    {'id': 't1', 'title': '서류 내기', 'dueDate': '2026-11-25', 'detail': '신분증 챙기기'},
    {'id': 't2', 'title': '전화하기', 'dueDate': null, 'detail': null},
  ],
  'warnings': ['늦으면 과태료가 있어요.'],
  'details': ['장소: 주민센터'],
  'model': 'fake:fake-default',
};

class _CountingReminders extends NoopReminders {
  final synced = <String>[];
  final cancelled = <String>[];
  @override
  Future<DateTime?> sync(TodoItem todo, DocumentResult doc) async {
    synced.add('${todo.id}:${todo.done}:${todo.remind}');
    return super.sync(todo, doc);
  }

  @override
  Future<void> cancel(TodoItem todo) async => cancelled.add(todo.id);
}

void main() {
  test('server JSON → model, amount/dueDate explicit, government → publicNotice', () {
    final d = DocumentResult.fromJson(Map<String, dynamic>.from(serverJson));
    expect(d.type, DocType.publicNotice);
    expect(d.amount, 32400);
    expect(d.dueDate, DateTime(2026, 11, 25));
    expect(d.caution, '늦으면 과태료가 있어요.');
    expect(amountOf(d), '32,400원');
    expect(amountOf(d, d.todos[0]), '32,400원');
    expect(formatWon(1234567), '1,234,567원');
  });

  test('save/load round trip keeps done & remind', () async {
    final d = DocumentResult.fromJson(Map<String, dynamic>.from(serverJson));
    d.todos[0].done = true;
    d.todos[1].remind = false;
    final repo = MemoryDocumentRepository();
    await repo.save([d]);
    final back = (await repo.load()).single;
    expect(back.todos[0].done, true);
    expect(back.todos[1].remind, false);
    expect(back.type, DocType.publicNotice);
    expect(back.createdAt, d.createdAt);
  });

  test('reminder times: day before 9:00 and due day 9:00, future only', () {
    final t = TodoItem(id: 'x', title: 'a', dueDate: DateTime(2026, 12, 1));
    expect(reminderTimes(t, DateTime(2026, 11, 16)), [DateTime(2026, 11, 30, 9), DateTime(2026, 12, 1, 9)]);
    expect(reminderTimes(t, DateTime(2026, 11, 30, 10)), [DateTime(2026, 12, 1, 9)]);
    t.done = true;
    expect(reminderTimes(t, DateTime(2026, 11, 16)), isEmpty);
    expect(notificationIdBase('abc'), notificationIdBase('abc'));
    expect(notificationIdBase('abc') % 2, 0);
  });

  test('HttpAnalysisService uploads multipart and parses', () async {
    late http.BaseRequest seen;
    final client = MockClient.streaming((req, body) async {
      seen = req;
      final bytes = await body.toBytes();
      expect(utf8.decode(bytes, allowMalformed: true), contains('filename="bill.png"'));
      return http.StreamedResponse(Stream.value(utf8.encode(jsonEncode(serverJson))), 200);
    });
    final svc = HttpAnalysisService('http://srv/', client: client);
    final r = await svc.analyze([XFile.fromData(utf8.encode('img'), name: 'bill.png', path: '/tmp/bill.png')]);
    expect(seen.url.toString(), 'http://srv/api/analyze');
    expect(r.title, '주민센터 안내문');
  });

  test('HttpAnalysisService shows server userMessage on error', () async {
    final client = MockClient((_) async => http.Response(
        jsonEncode({'error': {'code': 'unreadable', 'userMessage': '글씨가 잘 안 보여요.'}}), 422,
        headers: {'content-type': 'application/json; charset=utf-8'}));
    final svc = HttpAnalysisService('http://srv', client: client);
    expect(
      () => svc.analyze([XFile.fromData(utf8.encode('img'), name: 'a.png')]),
      throwsA(isA<AnalysisException>().having((e) => e.userMessage, 'msg', '글씨가 잘 안 보여요.')),
    );
  });

  test('store: analyze persists + schedules, done cancels, delete cancels', () async {
    final repo = MemoryDocumentRepository();
    final rem = _CountingReminders();
    final client = MockClient((_) async => http.Response.bytes(utf8.encode(jsonEncode(serverJson)), 200));
    final store = AppStore(analysisService: HttpAnalysisService('http://s', client: client), repository: repo, reminders: rem);
    final d = await store.analyze([XFile.fromData(utf8.encode('i'), name: 'a.png')]);
    expect(repo.data.length, 1);
    expect(rem.synced, ['t1:false:true', 't2:false:true']);
    await store.toggleDone(d.todos[0]);
    expect(repo.data.single['todos'][0]['done'], true);
    expect(rem.synced.last, 't1:true:true');

    final again = AppStore(analysisService: MockAnalysisService(), repository: repo, reminders: rem);
    await again.load();
    expect(again.documents.single.todos[0].done, true);
    await again.deleteDocument(again.documents.single);
    expect(repo.data, isEmpty);
    expect(rem.cancelled, ['t1', 't2']);
  });
}
