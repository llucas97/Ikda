import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:ilgeodeurim/models/auth_session.dart';
import 'package:ilgeodeurim/services/auth_service.dart';
import 'package:ilgeodeurim/services/token_store.dart';

void main() {
  test('AuthTokens.fromJson adds ExpiresIn seconds to the clock', () {
    final now = DateTime.utc(2026, 11, 17, 3);
    final tokens = AuthTokens.fromJson({
      'accessToken': 'access',
      'accessTokenExpiresIn': 900,
      'refreshToken': 'refresh',
      'refreshTokenExpiresIn': 120,
    }, now: now);
    expect(tokens.accessExpiresAt, now.add(const Duration(seconds: 900)));
    expect(tokens.refreshExpiresAt, now.add(const Duration(seconds: 120)));
    expect(tokens.expiresSoon(now), isFalse);
    expect(tokens.expiresSoon(now.add(const Duration(seconds: 840))), isTrue);
  });

  test('MockAuthService login and logout stay on device', () async {
    final store = TokenStore(memory: {});
    final auth = MockAuthService(store: store, delay: Duration.zero);
    expect(await auth.accessToken(), isNull);
    await auth.loginKakao();
    expect(auth.user?.name, '시험 사용자');
    expect(auth.user?.userNo, 0);
    expect(auth.user?.providers, ['KAKAO']);
    await auth.loginGoogle();
    expect(auth.user?.providers, ['GOOGLE']);

    final again = MockAuthService(store: store, delay: Duration.zero);
    await again.restore();
    expect(again.user?.name, '시험 사용자');
    await again.logout();
    expect(again.user, isNull);
    expect(await store.readUser(), isNull);
  });

  test('refresh is single-flight', () async {
    var calls = 0;
    final client = MockClient((request) async {
      expect(request.url.path, '/api/auth/refresh');
      calls += 1;
      await Future<void>.delayed(const Duration(milliseconds: 40));
      final bytes = utf8.encode(jsonEncode(_refreshBody('new-access', 'new-refresh')));
      return http.Response.bytes(bytes, 200, headers: {'content-type': 'application/json; charset=utf-8'});
    });
    final store = TokenStore(memory: {});
    final now = DateTime.now().toUtc();
    await store.saveSession(
      AuthTokens(
        accessToken: 'old-access',
        accessExpiresAt: now.subtract(const Duration(minutes: 1)),
        refreshToken: 'old-refresh',
        refreshExpiresAt: now.add(const Duration(days: 30)),
      ),
      const AuthUser(userNo: 7, userType: 'SENIOR', name: '박영감', providers: ['KAKAO']),
    );
    final auth = HttpAuthService(serverUrl: 'http://srv', store: store, client: client);
    final results = await Future.wait([
      auth.accessToken(),
      auth.accessToken(),
    ]);
    expect(calls, 1);
    expect(results, ['new-access', 'new-access']);
    expect((await store.readTokens())?.refreshToken, 'new-refresh');
  });
}

Map<String, dynamic> _refreshBody(String access, String refresh) => {
      'tokenType': 'Bearer',
      'accessToken': access,
      'accessTokenExpiresIn': 900,
      'refreshToken': refresh,
      'refreshTokenExpiresIn': 5184000,
      'user': {
        'userNo': 7,
        'userType': 'SENIOR',
        'name': '박영감',
        'email': null,
        'profileImageUrl': null,
        'providers': ['KAKAO'],
      },
    };
