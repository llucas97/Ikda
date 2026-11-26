import 'dart:convert';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/auth_session.dart';

/// 로그인 토큰은 일반 저장소에 두지 않는다.
/// Android 는 EncryptedSharedPreferences, iOS 는 첫 잠금 해제 뒤에도 읽히게 first_unlock.
class TokenStore {
  TokenStore({Map<String, String>? memory, FlutterSecureStorage? secure})
      : _memory = memory,
        _secure = memory != null
            ? null
            : (secure ??
                const FlutterSecureStorage(
                  aOptions: AndroidOptions(encryptedSharedPreferences: true),
                  iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
                ));

  static const accessKey = 'auth.access';
  static const accessExpKey = 'auth.accessExp';
  static const refreshKey = 'auth.refresh';
  static const refreshExpKey = 'auth.refreshExp';
  static const userKey = 'auth.user';
  static const deviceIdKey = 'auth.deviceId';
  static const skippedKey = 'auth.skipped';

  final Map<String, String>? _memory;
  final FlutterSecureStorage? _secure;

  Future<String?> _read(String key) async {
    final memory = _memory;
    if (memory != null) return memory[key];
    return _secure!.read(key: key);
  }

  Future<void> _write(String key, String? value) async {
    final memory = _memory;
    if (memory != null) {
      if (value == null) {
        memory.remove(key);
      } else {
        memory[key] = value;
      }
      return;
    }
    if (value == null) {
      await _secure!.delete(key: key);
    } else {
      await _secure!.write(key: key, value: value);
    }
  }

  Future<void> saveSession(AuthTokens tokens, AuthUser user) async {
    await _write(accessKey, tokens.accessToken);
    await _write(accessExpKey, tokens.accessExpiresAt.toUtc().toIso8601String());
    await _write(refreshKey, tokens.refreshToken);
    await _write(refreshExpKey, tokens.refreshExpiresAt.toUtc().toIso8601String());
    await _write(userKey, jsonEncode(user.toJson()));
  }

  Future<void> saveUser(AuthUser user) => _write(userKey, jsonEncode(user.toJson()));

  Future<AuthTokens?> readTokens() async {
    final access = await _read(accessKey);
    final refresh = await _read(refreshKey);
    final accessExp = await _read(accessExpKey);
    final refreshExp = await _read(refreshExpKey);
    if (access == null || refresh == null || accessExp == null || refreshExp == null) return null;
    return AuthTokens(
      accessToken: access,
      refreshToken: refresh,
      accessExpiresAt: DateTime.parse(accessExp).toUtc(),
      refreshExpiresAt: DateTime.parse(refreshExp).toUtc(),
    );
  }

  Future<AuthUser?> readUser() async {
    final raw = await _read(userKey);
    if (raw == null || raw.isEmpty) return null;
    final decoded = jsonDecode(raw);
    if (decoded is! Map) return null;
    return AuthUser.fromJson(Map<String, dynamic>.from(decoded));
  }

  /// 세션만 지운다. 기기 ID 와 '나중에' 표시는 남긴다.
  Future<void> clearSession() async {
    await _write(accessKey, null);
    await _write(accessExpKey, null);
    await _write(refreshKey, null);
    await _write(refreshExpKey, null);
    await _write(userKey, null);
  }

  Future<bool> isSkipped() async => (await _read(skippedKey)) == 'true';

  Future<void> setSkipped(bool skipped) => _write(skippedKey, skipped ? 'true' : null);

  /// 설치마다 하나. 로그인 요청의 deviceId 로 쓴다.
  Future<String> deviceId() async {
    final existing = await _read(deviceIdKey);
    if (existing != null && existing.isNotEmpty) return existing;
    final created = _uuid();
    await _write(deviceIdKey, created);
    return created;
  }
}

String _uuid() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-'
      '${hex.substring(16, 20)}-${hex.substring(20)}';
}
