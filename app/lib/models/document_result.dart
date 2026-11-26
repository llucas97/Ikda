import 'package:flutter/widgets.dart';
import '../widgets/ph_icons.dart';

/// 서류 종류. 서버(AI)가 분류해서 내려준다. 서버 코드 → 앱 enum 은 [DocType.fromCode].
enum DocType {
  bill('고지서', PhosphorIconsBold.receipt),
  medicine('약 안내', PhosphorIconsBold.pill),
  hospital('병원 안내', PhosphorIconsBold.firstAidKit),
  publicNotice('관공서 서류', PhosphorIconsBold.bank),
  contract('계약서', PhosphorIconsBold.signature),
  other('기타 서류', PhosphorIconsBold.fileText);

  const DocType(this.label, this.icon);
  final String label;
  final IconData icon;

  /// 서버는 `government`, 예전 앱 저장본은 `publicNotice` 를 쓴다. 둘 다 받는다.
  static DocType fromCode(String? code) {
    if (code == 'government') return DocType.publicNotice;
    return DocType.values.firstWhere((e) => e.name == code, orElse: () => DocType.other);
  }

  String get serverCode => this == DocType.publicNotice ? 'government' : name;
}

/// "큰딸이 보냈어요". 마지막 글자에 받침이 있으면 '이', 없으면 '가'.
String sentByPhrase(String label) {
  if (label.isEmpty) return '가족이 보냈어요';
  final c = label.runes.last;
  final batchim = c >= 0xAC00 && c <= 0xD7A3 && (c - 0xAC00) % 28 != 0;
  return '$label${batchim ? '이' : '가'} 보냈어요';
}

DateTime? _parseDate(Object? v) {
  if (v is! String || v.isEmpty) return null;
  final d = DateTime.tryParse(v);
  return d == null ? null : DateTime(d.year, d.month, d.day);
}

String? _formatDate(DateTime? d) => d == null
    ? null
    : '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// 해야 할 일 (납부, 병원 방문, 서류 제출 등)
class TodoItem {
  TodoItem({
    required this.id,
    required this.title,
    this.dueDate,
    this.detail,
    this.done = false,
    this.remind = true,
  });

  final String id;
  final String title; // 예: "전기요금 내기"
  final DateTime? dueDate;
  final String? detail; // 예: "은행, 편의점에서 낼 수 있어요"
  bool done;
  bool remind; // 기한 하루 전·당일 아침 알림

  factory TodoItem.fromJson(Map<String, dynamic> j) => TodoItem(
        id: (j['id'] as String?) ?? 't_${DateTime.now().microsecondsSinceEpoch}',
        title: j['title'] as String,
        dueDate: _parseDate(j['dueDate']),
        detail: j['detail'] as String?,
        done: (j['done'] as bool?) ?? false,
        remind: (j['remind'] as bool?) ?? true,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'dueDate': _formatDate(dueDate),
        'detail': detail,
        'done': done,
        'remind': remind,
      };
}

/// AI 분석 결과 한 건.
///
/// JSON 은 서버 응답과 같은 모양(docType, oneLiner, amount, dueDate, todos, warnings, details)이고,
/// 앱에 저장할 때는 여기에 createdAt 과 할 일의 done/remind 가 더 붙는다.
class DocumentResult {
  DocumentResult({
    required this.id,
    required this.type,
    required this.title,
    required this.summary,
    required this.keyPoints,
    required this.todos,
    required this.createdAt,
    this.amount,
    this.dueDate,
    this.warnings = const [],
    this.imagePaths = const [],
    this.source = 'SELF',
    this.sentByLabel,
    this.sentByLinkId,
    this.seen = true,
    this.access = 'OWNER',
    this.ownerLabel,
    this.updatedAt,
    this.modelName,
  });

  final String id;
  final DocType type;
  final String title; // 예: "한국전력 전기요금 고지서"
  final String summary; // 서버의 oneLiner: 쉬운 말 1~2문장
  final List<String> keyPoints; // 서버의 details: '항목: 값' 3~5줄
  final List<TodoItem> todos;
  final int? amount; // 내야 할 돈 (원). 없으면 null
  final DateTime? dueDate; // 가장 중요한 기한
  final List<String> warnings; // 꼭 조심할 점 (약, 계약서 등)
  final DateTime createdAt;
  /// 이번 실행에서 찍은 사진 경로. 개인정보 때문에 저장하지 않는다.
  final List<String> imagePaths;
  /// SELF / FAMILY / IMPORT
  final String source;
  final String? sentByLabel;
  final int? sentByLinkId;
  bool seen;
  final String access;
  final String? ownerLabel;
  final DateTime? updatedAt;
  final String? modelName;

  String? get caution => warnings.isEmpty ? null : warnings.join('\n');

  /// 서버 응답 또는 저장본 JSON → 모델
  factory DocumentResult.fromJson(Map<String, dynamic> j, {List<String> imagePaths = const []}) {
    final created = j['createdAt'] is String ? DateTime.tryParse(j['createdAt'] as String) : null;
    final warnings = (j['warnings'] as List?)?.cast<String>() ??
        [if (j['caution'] is String) j['caution'] as String];
    return DocumentResult(
      id: j['id'] as String,
      type: DocType.fromCode((j['docType'] ?? j['type']) as String?),
      title: j['title'] as String,
      summary: (j['oneLiner'] ?? j['summary'] ?? '') as String,
      keyPoints: ((j['details'] ?? j['keyPoints']) as List?)?.cast<String>() ?? const [],
      todos: ((j['todos'] as List?) ?? const [])
          .map((e) => TodoItem.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      amount: (j['amount'] as num?)?.toInt(),
      dueDate: _parseDate(j['dueDate']),
      warnings: warnings.where((w) => w.trim().isNotEmpty).toList(),
      createdAt: created ?? DateTime.now(),
      imagePaths: imagePaths,
      source: (j['source'] as String?) ?? 'SELF',
      sentByLabel: j['sentBy'] is Map ? (j['sentBy']['label'] as String?) : null,
      sentByLinkId: j['sentBy'] is Map ? (j['sentBy']['linkId'] as num?)?.toInt() : null,
      seen: (j['seen'] as bool?) ?? true,
      access: (j['access'] as String?) ?? 'OWNER',
      ownerLabel: j['owner'] is Map ? (j['owner']['label'] as String?) : null,
      updatedAt: j['updatedAt'] is String ? DateTime.tryParse(j['updatedAt'] as String) : null,
      modelName: j['model'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'docType': type.serverCode,
        'title': title,
        'oneLiner': summary,
        'amount': amount,
        'dueDate': _formatDate(dueDate),
        'todos': todos.map((t) => t.toJson()).toList(),
        'warnings': warnings,
        'details': keyPoints,
        'model': modelName,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt?.toIso8601String(),
        'source': source,
        'sentBy': sentByLabel == null ? null : {'linkId': sentByLinkId, 'label': sentByLabel},
        'seen': seen,
        'access': access,
        if (ownerLabel != null) 'owner': {'label': ownerLabel},
      };

  /// 대표 기한: 서버가 준 dueDate, 없으면 기한 있는 첫 할 일
  DateTime? get mainDue => dueDate ?? todos.where((t) => t.dueDate != null).firstOrNull?.dueDate;

  /// 소리로 읽어줄 문장
  String toSpeech() {
    final b = StringBuffer('$title 입니다. $summary ');
    for (final t in todos) {
      b.write('해야 할 일. ${t.title}. ');
      if (t.detail != null) b.write('${t.detail}. ');
    }
    if (caution != null) b.write('주의하실 점. $caution');
    return b.toString();
  }
}

/// 32400 → "32,400원"
String formatWon(int won) {
  final s = won.toString();
  final b = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return '$b원';
}
