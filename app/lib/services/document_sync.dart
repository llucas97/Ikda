import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/document_result.dart';
import 'document_repository.dart';

/// 기기 저장본이 먼저다. 온라인이면 올리고, since 로 받아 합친다. 실패는 큐에 남긴다.
class DocumentSync {
  DocumentSync({
    required this.baseUrl,
    required this.local,
    required this.accessToken,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final DocumentRepository local;
  final Future<String?> Function({bool forceRefresh}) accessToken;
  final http.Client _client;

  static const _sinceKey = 'ilgeodeurim.sync.since';
  static const _queueKey = 'ilgeodeurim.sync.queue';

  Future<Map<String, String>> _headers() async {
    final token = await accessToken();
    return {
      'content-type': 'application/json; charset=utf-8',
      if (token != null && token.isNotEmpty) 'authorization': 'Bearer $token',
    };
  }

  Future<void> bootstrap() async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getString(_sinceKey) == null) {
      for (final doc in await local.load()) {
        await _postDoc(doc);
      }
    }
    await pull();
  }

  Future<void> pull() async {
    final prefs = await SharedPreferences.getInstance();
    final since = prefs.getString(_sinceKey);
    final uri = Uri.parse('$baseUrl/api/documents').replace(queryParameters: {if (since != null) 'since': since});
    http.Response res;
    try {
      res = await _client.get(uri, headers: await _headers());
    } catch (e) {
      debugPrint('sync pull: $e');
      return;
    }
    if (res.statusCode != 200) return;
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    if (body is! Map) return;
    final remote = ((body['documents'] as List?) ?? const [])
        .map((e) => DocumentResult.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    final deleted = ((body['deleted'] as List?) ?? const []).cast<String>().toSet();
    final localDocs = await local.load();
    final byId = {for (final d in localDocs) d.id: d};
    for (final id in deleted) {
      byId.remove(id);
    }
    for (final doc in remote) {
      final old = byId[doc.id];
      final remoteAt = doc.updatedAt ?? doc.createdAt;
      final localAt = old?.updatedAt ?? old?.createdAt;
      if (old == null || localAt == null || !remoteAt.isBefore(localAt)) {
        byId[doc.id] = doc;
      }
    }
    final merged = byId.values.toList()..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    await local.save(merged);
    final serverTime = body['serverTime'] as String?;
    if (serverTime != null) await prefs.setString(_sinceKey, serverTime);
    await flush();
  }

  Future<void> enqueue(Map<String, dynamic> job) async {
    final prefs = await SharedPreferences.getInstance();
    final list = _queue(prefs)..add(job);
    await prefs.setString(_queueKey, jsonEncode(list));
    await flush();
  }

  Future<void> clearQueue() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_queueKey);
  }

  Future<void> flush() async {
    final prefs = await SharedPreferences.getInstance();
    final list = _queue(prefs);
    if (list.isEmpty) return;
    final left = <Map<String, dynamic>>[];
    for (final job in list) {
      final status = await _run(job);
      if (status == _Job.later) left.add(job);
    }
    await prefs.setString(_queueKey, jsonEncode(left));
  }

  Future<void> _postDoc(DocumentResult doc) async {
    try {
      await _client.post(Uri.parse('$baseUrl/api/documents'), headers: await _headers(), body: jsonEncode(doc.toJson()));
    } catch (e) {
      debugPrint('sync upload: $e');
    }
  }

  Future<_Job> _run(Map<String, dynamic> job) async {
    try {
      final kind = job['kind'] as String?;
      final id = job['id'] as String?;
      http.Response res;
      if (kind == 'delete' && id != null) {
        res = await _client.delete(Uri.parse('$baseUrl/api/documents/$id'), headers: await _headers());
      } else if (kind == 'seen' && id != null) {
        res = await _client.post(Uri.parse('$baseUrl/api/documents/$id/seen'), headers: await _headers());
      } else if (kind == 'todo' && id != null) {
        res = await _client.patch(
          Uri.parse('$baseUrl/api/documents/$id/todos/${job['todoId']}'),
          headers: await _headers(),
          body: jsonEncode({'done': job['done'], 'remind': job['remind']}),
        );
      } else {
        return _Job.drop;
      }
      if (res.statusCode == 404 || res.statusCode == 403) return _Job.drop;
      if (res.statusCode >= 200 && res.statusCode < 300) return _Job.ok;
      return _Job.later;
    } catch (e) {
      debugPrint('sync flush: $e');
      return _Job.later;
    }
  }

  List<Map<String, dynamic>> _queue(SharedPreferences prefs) {
    final raw = prefs.getString(_queueKey);
    if (raw == null) return [];
    final decoded = jsonDecode(raw);
    if (decoded is! List) return [];
    return decoded.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }
}

enum _Job { ok, later, drop }
