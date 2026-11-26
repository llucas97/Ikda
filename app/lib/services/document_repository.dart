import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/document_result.dart';

/// 서류·할 일 저장소. 지금은 기기 안(shared_preferences, 웹은 localStorage)에 JSON 으로.
/// 나중에 자녀 계정 연결·백업이 생기면 서버 동기화 구현으로 바꿔 끼운다.
abstract class DocumentRepository {
  Future<List<DocumentResult>> load();
  Future<void> save(List<DocumentResult> docs);
}

class PrefsDocumentRepository implements DocumentRepository {
  static const _key = 'ilgeodeurim.documents.v1';

  @override
  Future<List<DocumentResult>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null) return [];
    try {
      final list = jsonDecode(raw) as List;
      return list.map((e) => DocumentResult.fromJson(Map<String, dynamic>.from(e as Map))).toList();
    } catch (e) {
      debugPrint('저장된 서류를 읽지 못했어요: $e');
      return [];
    }
  }

  @override
  Future<void> save(List<DocumentResult> docs) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(docs.map((d) => d.toJson()).toList()));
  }
}

/// 테스트용 메모리 저장소
class MemoryDocumentRepository implements DocumentRepository {
  List<Map<String, dynamic>> data = [];

  @override
  Future<List<DocumentResult>> load() async => data.map(DocumentResult.fromJson).toList();

  @override
  Future<void> save(List<DocumentResult> docs) async =>
      data = docs.map((d) => jsonDecode(jsonEncode(d.toJson())) as Map<String, dynamic>).toList();
}
