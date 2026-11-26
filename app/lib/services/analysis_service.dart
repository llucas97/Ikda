import 'dart:async';
import 'dart:convert';

import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/document_result.dart';
import 'auth_service.dart';

/// 서류 사진을 분석하는 서비스.
///
/// 앱은 AI API 를 직접 부르지 않는다(키 노출 위험). 우리 서버에 사진을 올리면
/// 서버가 AI 를 불러서 아래 JSON 으로 돌려준다. (server/app/schema.py 와 같은 계약)
///
/// POST {SERVER_URL}/api/analyze   multipart: images=사진 (여러 장이면 같은 이름으로 여러 번)
/// 200 응답:
/// {
///   "id": "doc_123",
///   "docType": "bill",            // bill | medicine | hospital | contract | government | other
///   "title": "한국전력 전기요금 고지서",
///   "oneLiner": "이번 달 전기요금 32,400원을 25일까지 내시면 돼요.",
///   "amount": 32400,              // 원 단위 정수, 없으면 null
///   "dueDate": "2026-11-25",      // 가장 중요한 기한, 없으면 null
///   "todos": [{"id": "t1", "title": "전기요금 내기", "dueDate": "2026-11-25", "detail": "..."}],
///   "warnings": ["기한이 지나면 연체료가 붙어요."],
///   "details": ["청구 금액: 32,400원", "사용량: 285kWh"],
///   "model": "gemini:gemini-3.8-flash"
/// }
/// 실패 응답 (4xx/5xx): {"error": {"code": "unreadable", "userMessage": "글씨가 잘 안 보여요..."}}
abstract class AnalysisService {
  /// [linkId] 가 있으면 그 가족 대신 보낸다. [save] 는 내 서류로 서버에 보관.
  Future<DocumentResult> analyze(List<XFile> images, {bool save = false, int? linkId});
}

class AnalysisException implements Exception {
  AnalysisException(this.userMessage, {this.code, this.page});
  final String userMessage; // 어르신에게 그대로 보여줄 문장
  final String? code;
  final int? page;

  /// 서버가 정말 못 읽는 사진으로 막은 경우. '그래도 보내기'가 없다.
  bool get blocksSend => code != null && code!.startsWith('photo_');

  @override
  String toString() => 'AnalysisException($userMessage)';
}

/// 실제 서버로 사진을 올려 분석한다.
class HttpAnalysisService implements AnalysisService {
  HttpAnalysisService(
    String baseUrl, {
    http.Client? client,
    this.timeout = const Duration(seconds: 90),
    this.accessToken,
  })  : baseUrl = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl,
        _client = client ?? http.Client();

  final String baseUrl;
  final Duration timeout;
  final http.Client _client;

  /// 있으면 Authorization 헤더를 붙인다. 401 token_expired 면 forceRefresh 로 한 번 더.
  final Future<String?> Function({bool forceRefresh})? accessToken;

  @override
  Future<DocumentResult> analyze(List<XFile> images, {bool save = false, int? linkId}) async {
    if (images.isEmpty) throw AnalysisException('사진이 없어요.\n다시 찍어 주세요.');
    // 멀티파트 본문은 한 번 보내면 다시 못 쓰므로, 재시도 때 요청을 새로 만든다.
    final parts = <(String, List<int>)>[];
    for (var i = 0; i < images.length; i++) {
      final x = images[i];
      final name = x.name.isNotEmpty ? x.name : 'page${i + 1}.jpg';
      parts.add((name, await x.readAsBytes()));
    }

    Future<http.Response> send(String? token) async {
      final path = linkId == null ? '/api/analyze' : '/api/family/links/$linkId/analyze';
      final req = http.MultipartRequest('POST', Uri.parse('$baseUrl$path'));
      if (token != null && token.isNotEmpty) req.headers['Authorization'] = 'Bearer $token';
      if (linkId == null && save) req.fields['save'] = 'true';
      for (final (name, bytes) in parts) {
        req.files.add(http.MultipartFile.fromBytes('images', bytes, filename: name));
      }
      try {
        return await http.Response.fromStream(await _client.send(req).timeout(timeout));
      } on TimeoutException {
        throw AnalysisException('시간이 너무 오래 걸려요.\n잠시 뒤에 다시 해 주세요.');
      } catch (e) {
        if (e is AnalysisException) rethrow;
        debugPrint('analyze network error: $e');
        throw AnalysisException('인터넷 연결을 확인해 주세요.\n와이파이나 데이터가 켜져 있어야 해요.');
      }
    }

    var token = await _token();
    var res = await send(token);
    if (res.statusCode == 401 && _errorCode(res) == 'token_expired' && accessToken != null) {
      token = await _token(forceRefresh: true);
      res = await send(token);
    }

    Map<String, dynamic>? body;
    try {
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      body = decoded is Map ? Map<String, dynamic>.from(decoded) : null;
    } catch (_) {
      body = null;
    }
    final ok = linkId == null ? res.statusCode == 200 : res.statusCode == 201;
    if (!ok || body == null) {
      final err = body?['error'] as Map?;
      final msg = err?['userMessage'] as String?;
      throw AnalysisException(msg ?? '잠시 문제가 생겼어요.\n조금 뒤에 다시 해 주세요.',
          code: err?['code'] as String?, page: (err?['page'] as num?)?.toInt());
    }
    return DocumentResult.fromJson(body, imagePaths: kIsWeb ? const [] : images.map((e) => e.path).toList());
  }

  Future<String?> _token({bool forceRefresh = false}) async {
    if (accessToken == null) return null;
    try {
      return await accessToken!(forceRefresh: forceRefresh);
    } on AuthException catch (e) {
      throw AnalysisException(e.userMessage.isEmpty
          ? '인터넷 연결을 확인해 주세요.\n와이파이나 데이터가 켜져 있어야 해요.'
          : e.userMessage);
    }
  }
}

String? _errorCode(http.Response res) {
  try {
    final decoded = jsonDecode(utf8.decode(res.bodyBytes));
    if (decoded is Map) {
      final error = decoded['error'];
      if (error is Map) return error['code'] as String?;
    }
  } catch (_) {}
  return null;
}

/// 서버 없이 화면 개발용으로 쓰는 가짜 서비스.
/// 호출할 때마다 고지서 → 약 안내 → 병원 안내 순서로 돌아가며 결과를 준다.
class MockAnalysisService implements AnalysisService {
  int _count = 0;

  @override
  Future<DocumentResult> analyze(List<XFile> images, {bool save = false, int? linkId}) async {
    await Future<void>.delayed(const Duration(seconds: 3));
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final n = _count++ % 3;
    final id = 'doc_${now.millisecondsSinceEpoch}';
    final paths = kIsWeb ? const <String>[] : images.map((e) => e.path).toList();

    switch (n) {
      case 0:
        final due = today.add(const Duration(days: 9));
        return DocumentResult(
          id: id,
          type: DocType.bill,
          title: '한국전력 전기요금 고지서',
          summary: '이번 달 전기요금이 32,400원 나왔어요. 지난달보다 4,100원 더 나왔어요. '
              '${due.month}월 ${due.day}일까지 내시면 돼요.',
          keyPoints: const ['청구 금액: 32,400원', '지난달보다 4,100원 많음', '자동이체: 신청 안 되어 있음'],
          amount: 32400,
          dueDate: due,
          todos: [
            TodoItem(id: '${id}_t1', title: '전기요금 내기', dueDate: due, detail: '은행, 편의점, 한전 앱에서 낼 수 있어요'),
          ],
          createdAt: now,
          imagePaths: paths,
        );
      case 1:
        final due = today.add(const Duration(days: 7));
        return DocumentResult(
          id: id,
          type: DocType.medicine,
          title: '약국 복약 안내 (7일분)',
          summary: '하루 세 번, 식사하고 30분 뒤에 드시는 약이에요. 7일 동안 드시면 돼요.',
          keyPoints: const ['하루 3번 (아침·점심·저녁)', '식사 후 30분', '7일분'],
          dueDate: due,
          todos: [
            TodoItem(id: '${id}_t1', title: '약 다 드시는 날', dueDate: due, detail: '증상이 계속되면 다시 병원에 가 보세요'),
          ],
          warnings: const ['정확한 복용법은 약봉투와 약사 안내를 꼭 다시 확인해 주세요.'],
          createdAt: now,
          imagePaths: paths,
        );
      default:
        final due = today.add(const Duration(days: 1));
        return DocumentResult(
          id: id,
          type: DocType.hospital,
          title: '건강검진 예약 안내',
          summary: '건강검진이 예약되어 있어요. 검사 전날 밤부터 음식을 드시면 안 돼요.',
          keyPoints: const ['장소: 시민병원 3층 검진센터', '신분증 꼭 챙기기', '전날 밤부터 금식'],
          dueDate: due,
          todos: [
            TodoItem(id: '${id}_t1', title: '건강검진 받으러 가기', dueDate: due, detail: '오전 8시 30분까지 · 신분증 챙기기'),
          ],
          warnings: const ['검사 전날 밤 9시 이후로는 물 말고 아무것도 드시지 마세요.'],
          createdAt: now,
          imagePaths: paths,
        );
    }
  }
}
