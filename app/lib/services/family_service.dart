import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/document_result.dart';
import '../models/family_link.dart';

class FamilyException implements Exception {
  FamilyException(this.userMessage, {this.code});
  final String userMessage;
  final String? code;
}

abstract class FamilyService {
  Future<InviteTicket> createInvite({
    String? myRole,
    String? label,
    String? relationCd,
    String? counterRelationCd,
    String? counterNickname,
  });
  Future<InvitePreview> preview({String? code, String? token});
  Future<FamilyLink> accept({String? code, String? token, String? label, String? relationCd});
  Future<({List<FamilyLink> links, int? pendingInviteId})> list();
  Future<FamilyLink> updateRelation(int linkId, {String? label, String? relationCd});
  Future<FamilyLink> updatePermissions(int linkId,
      {bool? canView, bool? canEdit, bool? canDelete, bool? notification});
  Future<void> unlink(int linkId);
  Future<List<DocumentResult>> familyDocuments();
  Future<List<({int linkId, String label, bool created})>> shareDocument(String docId, {List<int>? linkIds});
}

class HttpFamilyService implements FamilyService {
  HttpFamilyService(String baseUrl, {http.Client? client, this.accessToken})
      : baseUrl = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl,
        _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;
  final Future<String?> Function({bool forceRefresh})? accessToken;

  Future<Map<String, String>> _headers({bool json = true}) async {
    final token = accessToken == null ? null : await accessToken!();
    return {
      if (json) 'content-type': 'application/json; charset=utf-8',
      if (token != null && token.isNotEmpty) 'authorization': 'Bearer $token',
    };
  }

  Future<Map<String, dynamic>> _send(String method, String path, {Object? body, int ok = 200}) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = await _headers(json: body != null);
    late http.Response res;
    try {
      res = switch (method) {
        'GET' => await _client.get(uri, headers: headers),
        'DELETE' => await _client.delete(uri, headers: headers),
        'PATCH' => await _client.patch(uri, headers: headers, body: jsonEncode(body)),
        _ => await _client.post(uri, headers: headers, body: body == null ? null : jsonEncode(body)),
      };
    } catch (e) {
      debugPrint('family network: $e');
      throw FamilyException('인터넷 연결을 확인해 주세요.\n와이파이나 데이터가 켜져 있어야 해요.');
    }
    if (res.statusCode == 204) return {};
    Map<String, dynamic>? decoded;
    try {
      final raw = jsonDecode(utf8.decode(res.bodyBytes));
      if (raw is Map) decoded = Map<String, dynamic>.from(raw);
    } catch (_) {}
    if (res.statusCode != ok || decoded == null) {
      final err = decoded?['error'];
      final msg = err is Map ? err['userMessage'] as String? : null;
      final code = err is Map ? err['code'] as String? : null;
      throw FamilyException(msg ?? '잠시 문제가 생겼어요.\n조금 뒤에 다시 해 주세요.', code: code);
    }
    return decoded;
  }

  @override
  Future<InviteTicket> createInvite({
    String? myRole,
    String? label,
    String? relationCd,
    String? counterRelationCd,
    String? counterNickname,
  }) async {
    final j = await _send('POST', '/api/family/invites', ok: 201, body: {
      if (myRole != null) 'myRole': myRole,
      if (label != null) 'label': label,
      if (relationCd != null) 'relationCd': relationCd,
      if (counterRelationCd != null) 'counterRelationCd': counterRelationCd,
      if (counterNickname != null) 'counterNickname': counterNickname,
    });
    return InviteTicket.fromJson(j);
  }

  @override
  Future<InvitePreview> preview({String? code, String? token}) async {
    final j = await _send('POST', '/api/family/invites/preview', body: {
      if (code != null) 'code': code,
      if (token != null) 'token': token,
    });
    return InvitePreview.fromJson(j);
  }

  @override
  Future<FamilyLink> accept({String? code, String? token, String? label, String? relationCd}) async {
    final j = await _send('POST', '/api/family/invites/accept', body: {
      if (code != null) 'code': code,
      if (token != null) 'token': token,
      if (label != null) 'label': label,
      if (relationCd != null) 'relationCd': relationCd,
    });
    return FamilyLink.fromJson(Map<String, dynamic>.from(j['link'] as Map));
  }

  @override
  Future<({List<FamilyLink> links, int? pendingInviteId})> list() async {
    final j = await _send('GET', '/api/family');
    final links = ((j['links'] as List?) ?? const [])
        .map((e) => FamilyLink.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    final pending = j['pendingInvite'];
    final id = pending is Map ? (pending['inviteId'] as num?)?.toInt() : null;
    return (links: links, pendingInviteId: id);
  }

  @override
  Future<FamilyLink> updateRelation(int linkId, {String? label, String? relationCd}) async {
    final j = await _send('PATCH', '/api/family/links/$linkId', body: {
      if (label != null) 'label': label,
      if (relationCd != null) 'relationCd': relationCd,
    });
    return FamilyLink.fromJson(Map<String, dynamic>.from(j['link'] as Map));
  }

  @override
  Future<FamilyLink> updatePermissions(int linkId,
      {bool? canView, bool? canEdit, bool? canDelete, bool? notification}) async {
    final j = await _send('PATCH', '/api/family/links/$linkId/permissions', body: {
      if (canView != null) 'canView': canView,
      if (canEdit != null) 'canEdit': canEdit,
      if (canDelete != null) 'canDelete': canDelete,
      if (notification != null) 'notification': notification,
    });
    return FamilyLink.fromJson(Map<String, dynamic>.from(j['link'] as Map));
  }

  @override
  Future<void> unlink(int linkId) => _send('DELETE', '/api/family/links/$linkId');

  @override
  Future<List<DocumentResult>> familyDocuments() async {
    final j = await _send('GET', '/api/family/documents');
    return ((j['documents'] as List?) ?? const [])
        .map((e) => DocumentResult.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  @override
  Future<List<({int linkId, String label, bool created})>> shareDocument(String docId,
      {List<int>? linkIds}) async {
    final j = await _send('POST', '/api/documents/$docId/shares', body: {
      if (linkIds != null) 'linkIds': linkIds,
    });
    return ((j['sharedTo'] as List?) ?? const []).map((e) {
      final m = Map<String, dynamic>.from(e as Map);
      return (linkId: (m['linkId'] as num).toInt(), label: (m['label'] as String?) ?? '가족', created: m['new'] == true);
    }).toList();
  }
}

/// 서버 없이 화면만. 번호 123456 이면 바로 연결되고 가짜 서류가 하나 있다.
class MockFamilyService implements FamilyService {
  final List<FamilyLink> _links = [];
  InviteTicket? pending;

  /// SEED_DEMO. 이미 연결된 사람이 있으면 건드리지 않는다.
  void seedDemoFamily() {
    if (_links.isNotEmpty) return;
    _links.addAll(const [
      FamilyLink(
        linkId: 1,
        myRole: 'SENIOR',
        name: '김지은',
        label: '큰딸',
        relationCd: 'DAUGHTER',
        relationLabel: '딸',
        nickname: '큰딸',
        isPrimary: true,
        canView: true,
        canEdit: true,
        canDelete: false,
        notification: true,
        canSend: false,
      ),
      FamilyLink(
        linkId: 2,
        myRole: 'SENIOR',
        name: '김민수',
        label: '아들',
        relationCd: 'SON',
        relationLabel: '아들',
        nickname: '아들',
        isPrimary: true,
        canView: true,
        canEdit: true,
        canDelete: false,
        notification: true,
        canSend: false,
      ),
    ]);
  }

  @override
  Future<InviteTicket> createInvite({
    String? myRole,
    String? label,
    String? relationCd,
    String? counterRelationCd,
    String? counterNickname,
  }) async {
    pending = InviteTicket(
      inviteId: 1,
      code: '123456',
      myRole: myRole ?? 'CHILD',
      expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 30)),
      shareText: '읽다에서 가족으로 연결해요.\n앱에서 번호 123 456 을 넣어 주세요.',
      appLink: 'https://example.com/f/mock',
      webLink: 'https://example.com/f/mock',
    );
    return pending!;
  }

  @override
  Future<InvitePreview> preview({String? code, String? token}) async {
    if (_digits(code) != '123456' && token != 'mock') {
      throw FamilyException('번호가 맞지 않거나 시간이 지났어요. 새 번호를 받아 주세요.', code: 'invite_invalid');
    }
    return const InvitePreview(name: '김순자', yourRole: 'SENIOR', alreadyLinked: false, counterRelationCd: 'MOTHER');
  }

  @override
  Future<FamilyLink> accept({String? code, String? token, String? label, String? relationCd}) async {
    await preview(code: code, token: token);
    final link = FamilyLink(
      linkId: 1,
      myRole: 'SENIOR',
      name: '김지은',
      label: label ?? '큰딸',
      relationCd: relationCd ?? 'DAUGHTER',
      relationLabel: relationKo(relationCd ?? 'DAUGHTER'),
      nickname: label ?? '큰딸',
      isPrimary: true,
      canView: true,
      canEdit: true,
      canDelete: false,
      notification: true,
      canSend: false,
    );
    _links
      ..clear()
      ..add(link);
    pending = null;
    return link;
  }

  @override
  Future<({List<FamilyLink> links, int? pendingInviteId})> list() async =>
      (links: List<FamilyLink>.from(_links), pendingInviteId: pending?.inviteId);

  @override
  Future<FamilyLink> updateRelation(int linkId, {String? label, String? relationCd}) async {
    final i = _links.indexWhere((l) => l.linkId == linkId);
    if (i < 0) throw FamilyException('가족 연결을 찾을 수 없어요.', code: 'link_not_found');
    final old = _links[i];
    final nextCd = relationCd ?? old.relationCd;
    final nextRelation = relationKo(nextCd);
    final trimmed = label?.trim();
    final nextNick = (trimmed == null || trimmed.isEmpty) ? nextRelation : trimmed;
    final next = FamilyLink(
      linkId: old.linkId,
      myRole: old.myRole,
      name: old.name,
      label: nextNick,
      relationCd: nextCd,
      relationLabel: nextRelation,
      nickname: nextNick,
      isPrimary: old.isPrimary,
      canView: old.canView,
      canEdit: old.canEdit,
      canDelete: old.canDelete,
      notification: old.notification,
      canSend: old.canSend,
      photoUrl: old.photoUrl,
      mappingId: old.mappingId,
    );
    _links[i] = next;
    return next;
  }

  @override
  Future<FamilyLink> updatePermissions(int linkId,
      {bool? canView, bool? canEdit, bool? canDelete, bool? notification}) async {
    final old = _links.firstWhere((l) => l.linkId == linkId, orElse: () => throw FamilyException('가족 연결을 찾을 수 없어요.'));
    if (!old.isPrimary) throw FamilyException('권한은 대표 가족만 바꿀 수 있어요.', code: 'not_primary');
    final next = FamilyLink(
      linkId: old.linkId,
      myRole: old.myRole,
      name: old.name,
      label: old.label,
      relationCd: old.relationCd,
      relationLabel: old.relationLabel,
      nickname: old.nickname,
      isPrimary: old.isPrimary,
      canView: canView ?? old.canView,
      canEdit: canEdit ?? old.canEdit,
      canDelete: canDelete ?? old.canDelete,
      notification: notification ?? old.notification,
      canSend: old.canSend,
    );
    _links[_links.indexWhere((l) => l.linkId == linkId)] = next;
    return next;
  }

  @override
  Future<void> unlink(int linkId) async => _links.removeWhere((l) => l.linkId == linkId);

  @override
  Future<List<DocumentResult>> familyDocuments() async {
    if (_links.isEmpty) return const [];
    final now = DateTime.now();
    return [
      DocumentResult(
        id: 'doc_mock_family',
        type: DocType.hospital,
        title: '건강검진 안내',
        summary: '내일 아침 검진이 있어요. 전날 밤부터는 음식을 드시지 마세요.',
        keyPoints: const ['장소: 시민병원', '신분증 챙기기'],
        todos: [TodoItem(id: 't_mock', title: '검진 받으러 가기', dueDate: now.add(const Duration(days: 1)))],
        createdAt: now,
        source: 'FAMILY',
        sentByLabel: '큰딸',
        sentByLinkId: 1,
        seen: false,
        access: 'OWNER',
        ownerLabel: '어머니',
      ),
    ];
  }

  @override
  Future<List<({int linkId, String label, bool created})>> shareDocument(String docId, {List<int>? linkIds}) async {
    if (_links.isEmpty) throw FamilyException('연결된 자녀가 없어요. 먼저 가족을 연결해 주세요.', code: 'no_family');
    final targets = linkIds == null ? _links : _links.where((l) => linkIds.contains(l.linkId)).toList();
    return [for (final l in targets) (linkId: l.linkId, label: l.display, created: true)];
  }
}

String? _digits(String? raw) => raw?.replaceAll(RegExp(r'[\s-]'), '');
