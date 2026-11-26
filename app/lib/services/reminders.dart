import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import '../models/document_result.dart';

/// 할 일 알림. 기한 하루 전 아침 9시 + 당일 아침 9시 (한국 시간).
abstract class Reminders {
  Future<void> init();

  /// 알림 권한 요청 (Android 13+, iOS). 허용되면 true.
  Future<bool> requestPermission();

  /// 이 할 일의 알림을 다시 맞춘다. 끝났거나 꺼졌거나 기한이 없으면 지우기만 한다.
  /// 예약된 첫 알림 시각을 돌려준다 (없으면 null).
  Future<DateTime?> sync(TodoItem todo, DocumentResult doc);

  Future<void> cancel(TodoItem todo);
}

/// 웹·테스트: 아무것도 하지 않음. 계산만 해서 돌려준다.
class NoopReminders implements Reminders {
  @override
  Future<void> init() async {}
  @override
  Future<bool> requestPermission() async => true;
  @override
  Future<DateTime?> sync(TodoItem todo, DocumentResult doc) async =>
      reminderTimes(todo, DateTime.now()).firstOrNull;
  @override
  Future<void> cancel(TodoItem todo) async {}
}

/// 할 일 → 알림 시각들 (기한 전날 9시, 당일 9시 중 아직 안 지난 것)
List<DateTime> reminderTimes(TodoItem t, DateTime now) {
  final due = t.dueDate;
  if (due == null || t.done || !t.remind) return const [];
  return [
    DateTime(due.year, due.month, due.day - 1, 9),
    DateTime(due.year, due.month, due.day, 9),
  ].where((d) => d.isAfter(now)).toList();
}

/// 할 일 id → 알림 id (실행마다 같은 값이 나오도록 FNV-1a, 31비트). 하루 전=짝수, 당일=홀수.
int notificationIdBase(String todoId) {
  var h = 0x811c9dc5;
  for (final c in todoId.codeUnits) {
    h ^= c;
    h = (h * 0x01000193) & 0xffffffff;
  }
  return (h & 0x3fffffff) * 2;
}

class LocalReminders implements Reminders {
  LocalReminders({this.timeZone = 'Asia/Seoul'});
  final String timeZone;
  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;
  bool? _granted;

  static const _details = NotificationDetails(
    android: AndroidNotificationDetails(
      'todo_reminders',
      '할 일 알림',
      channelDescription: '서류 기한 하루 전과 당일 아침에 알려 드려요',
      importance: Importance.high,
      priority: Priority.high,
    ),
    iOS: DarwinNotificationDetails(),
  );

  @override
  Future<void> init() async {
    if (kIsWeb || _ready) return;
    tzdata.initializeTimeZones();
    tz.setLocalLocation(tz.getLocation(timeZone));
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        // 권한은 앱 시작 때가 아니라 처음 알림을 맞출 때 묻는다
        iOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
      ),
    );
    final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
    await android?.createNotificationChannel(const AndroidNotificationChannel(
      'family',
      '가족 알림',
      description: '가족이 서류를 보내면 알려 드려요',
      importance: Importance.high,
    ));
    _ready = true;
  }

  @override
  Future<bool> requestPermission() async {
    if (!_ready) return false;
    if (_granted != null) return _granted!;
    bool? ok;
    if (defaultTargetPlatform == TargetPlatform.android) {
      ok = await _plugin
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
    } else if (defaultTargetPlatform == TargetPlatform.iOS) {
      ok = await _plugin
          .resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>()
          ?.requestPermissions(alert: true, badge: true, sound: true);
    }
    return _granted = ok ?? true;
  }

  @override
  Future<DateTime?> sync(TodoItem todo, DocumentResult doc) async {
    if (!_ready) return null;
    await cancel(todo);
    final times = reminderTimes(todo, DateTime.now());
    if (times.isEmpty) return null;
    if (!await requestPermission()) return null;
    final base = notificationIdBase(todo.id);
    final due = todo.dueDate!;
    final amount = doc.amount != null && doc.mainDue == due ? ' · ${formatWon(doc.amount!)}' : '';
    for (final at in times) {
      final dayBefore = at.day != due.day;
      await _plugin.zonedSchedule(
        id: dayBefore ? base : base + 1,
        scheduledDate: tz.TZDateTime(tz.local, at.year, at.month, at.day, at.hour),
        notificationDetails: _details,
        // 정확한 알람 권한 없이도 되도록(Android 12+). 몇 분 늦을 수 있다.
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        title: dayBefore ? '내일까지: ${todo.title}' : '오늘까지: ${todo.title}',
        body: '${doc.title}$amount',
        payload: doc.id,
      );
    }
    return times.first;
  }

  @override
  Future<void> cancel(TodoItem todo) async {
    if (!_ready) return;
    final base = notificationIdBase(todo.id);
    await _plugin.cancel(id: base);
    await _plugin.cancel(id: base + 1);
  }
}

Reminders createReminders() => kIsWeb ? NoopReminders() : LocalReminders();
