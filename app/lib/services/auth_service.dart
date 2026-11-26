import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';

import '../config.dart';
import '../models/auth_session.dart';
import 'device_os_web.dart' if (dart.library.io) 'device_os_io.dart' as device;
import 'token_store.dart';

/// 로그인 실패. [cancelled] 이면 화면은 아무 말도 하지 않는다.
class AuthException implements Exception {
  const AuthException(this.userMessage, {this.cancelled = false});
  const AuthException.cancelled() : userMessage = '', cancelled = true;

  final String userMessage;
  final bool cancelled;
}

const _loginFailed = '로그인하지 못했어요. 다시 해 주세요.';
const _offline = '인터넷 연결을 확인해 주세요.';

/// access 가 만료됐거나 세션이 끊기면 저장된 토큰을 지우고 로그인 화면으로.
const _terminalRefresh = {
  'invalid_token',
  'session_revoked',
  'user_inactive',
  'refresh_revoked',
  'refresh_reused',
  'refresh_expired',
  'invalid_refresh',
  'login_required',
};

abstract class AuthService extends ChangeNotifier {
  AuthUser? get user;
  bool get skipped;

  Future<void> restore();
  Future<void> skip();
  Future<void> loginKakao();
  Future<void> loginGoogle();
  Future<void> loginTest();

  /// 만료 60초 전이면 갱신한 access 토큰. 없으면 null.
  /// [forceRefresh] 는 서버가 token_expired 를 줬을 때 한 번 더.
  Future<String?> accessToken({bool forceRefresh = false});

  Future<void> logout();
  Future<void> withdraw();

  /// FCM 토큰. 실패해도 로그인은 유지한다.
  Future<void> registerPushToken(String token, {required String platform});
}

class HttpAuthService extends AuthService {
  HttpAuthService({
    required String serverUrl,
    required TokenStore store,
    http.Client? client,
  })  : _base = serverUrl.endsWith('/') ? serverUrl.substring(0, serverUrl.length - 1) : serverUrl,
        _store = store,
        _client = client ?? http.Client();

  final String _base;
  final TokenStore _store;
  final http.Client _client;

  AuthUser? _user;
  bool _skipped = false;
  Future<String?>? _inflight;
  Future<void>? _googleReady;

  @override
  AuthUser? get user => _user;

  @override
  bool get skipped => _skipped;

  @override
  Future<void> restore() async {
    _skipped = await _store.isSkipped();
    final tokens = await _store.readTokens();
    _user = tokens == null ? null : await _store.readUser();
    notifyListeners();
  }

  @override
  Future<void> skip() async {
    await _store.setSkipped(true);
    _skipped = true;
    notifyListeners();
  }

  @override
  Future<void> loginKakao() async {
    if (kIsWeb) throw const AuthException('웹에서는 카카오 로그인을 아직 쓸 수 없어요.');
    if (AppConfig.kakaoNativeAppKey.isEmpty) {
      throw const AuthException('카카오 로그인 설정이 아직 안 됐어요.');
    }
    final token = await _kakaoAccessToken();
    await _exchange('/api/auth/kakao', {
      'accessToken': token,
      'deviceId': await _store.deviceId(),
      'deviceOs': device.deviceOs(),
    });
  }

  @override
  Future<void> loginGoogle() async {
    if (AppConfig.googleServerClientId.isEmpty) {
      throw const AuthException('구글 로그인 설정이 아직 안 됐어요.');
    }
    await _ensureGoogle();
    if (!GoogleSignIn.instance.supportsAuthenticate()) {
      throw const AuthException('이 화면에서는 구글 로그인을 쓸 수 없어요.');
    }
    final GoogleSignInAccount account;
    try {
      account = await GoogleSignIn.instance.authenticate();
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) throw const AuthException.cancelled();
      throw const AuthException(_loginFailed);
    }
    final idToken = account.authentication.idToken;
    if (idToken is! String || idToken.isEmpty) {
      throw const AuthException('구글 로그인 설정을 확인해 주세요. 웹 클라이언트 ID가 필요해요.');
    }
    await _exchange('/api/auth/google', {
      'idToken': idToken,
      'deviceId': await _store.deviceId(),
      'deviceOs': device.deviceOs(),
    });
  }

  @override
  Future<void> loginTest() async {
    final id = await _store.deviceId();
    await _exchange('/api/auth/fake', {
      'accessToken': 'fake:$id',
      'deviceId': id,
      'deviceOs': device.deviceOs(),
    });
  }

  @override
  Future<String?> accessToken({bool forceRefresh = false}) {
    // 갱신은 한 번에 하나만. 두 번째 호출은 진행 중인 Future 를 같이 기다린다.
    final running = _inflight;
    if (running != null) return running;
    final flight = _resolve(forceRefresh);
    _inflight = flight;
    flight.whenComplete(() {
      if (identical(_inflight, flight)) _inflight = null;
    });
    return flight;
  }

  Future<String?> _resolve(bool forceRefresh) async {
    final tokens = await _store.readTokens();
    if (tokens == null) return null;
    if (!forceRefresh && !tokens.expiresSoon()) return tokens.accessToken;
    final next = await _refresh(tokens);
    return next?.accessToken;
  }

  @override
  Future<void> logout() async {
    final tokens = await _store.readTokens();
    try {
      final headers = <String, String>{'Content-Type': 'application/json'};
      if (tokens != null) headers['Authorization'] = 'Bearer ${tokens.accessToken}';
      await _client
          .post(
            Uri.parse('$_base/api/auth/logout'),
            headers: headers,
            body: jsonEncode({
              'refreshToken': tokens?.refreshToken,
              'deviceId': await _store.deviceId(),
            }),
          )
          .timeout(const Duration(seconds: 8));
    } catch (_) {
      // 서버가 안 돼도 이 기기의 토큰은 지운다.
    }
    await _clearLocal();
    try {
      await UserApi.instance.logout();
    } catch (_) {}
    try {
      if (AppConfig.googleServerClientId.isNotEmpty) {
        await _ensureGoogle();
        await GoogleSignIn.instance.signOut();
      }
    } catch (_) {}
  }

  @override
  Future<void> registerPushToken(String token, {required String platform}) async {
    final access = await accessToken();
    if (access == null) return;
    try {
      await _client.post(
        Uri.parse('$_base/api/me/push-token'),
        headers: {
          'content-type': 'application/json; charset=utf-8',
          'authorization': 'Bearer $access',
        },
        body: jsonEncode({
          'pushToken': token,
          'platform': platform,
          'deviceId': await _store.deviceId(),
        }),
      );
    } catch (e) {
      debugPrint('push token: $e');
    }
  }

  Future<void> withdraw() async {
    String? kakaoAccessToken;
    if (_user?.providers.contains('KAKAO') ?? false) {
      try {
        kakaoAccessToken = (await TokenManagerProvider.instance.manager.getToken())?.accessToken;
      } catch (_) {}
    }
    final tokens = await _store.readTokens();
    final req = http.Request('DELETE', Uri.parse('$_base/api/me'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode({'kakaoAccessToken': kakaoAccessToken});
    if (tokens != null) req.headers['Authorization'] = 'Bearer ${tokens.accessToken}';
    final http.Response res;
    try {
      res = await http.Response.fromStream(await _client.send(req).timeout(const Duration(seconds: 15)));
    } on TimeoutException {
      throw const AuthException(_offline);
    } catch (e) {
      if (e is AuthException) rethrow;
      throw const AuthException(_offline);
    }
    if (res.statusCode != 200) throw AuthException(_serverMessage(res) ?? '탈퇴하지 못했어요. 다시 해 주세요.');
    if (_user?.providers.contains('GOOGLE') ?? false) {
      try {
        await _ensureGoogle();
        await GoogleSignIn.instance.disconnect();
      } catch (_) {}
    }
    await _clearLocal();
  }

  Future<void> _clearLocal() async {
    await _store.clearSession();
    _user = null;
    notifyListeners();
  }

  Future<String> _kakaoAccessToken() async {
    if (await isKakaoTalkInstalled()) {
      try {
        return (await UserApi.instance.loginWithKakaoTalk()).accessToken;
      } on PlatformException catch (e) {
        if (e.code == 'CANCELED') throw const AuthException.cancelled();
      } on AuthException {
        rethrow;
      } catch (_) {
        // 카카오톡 로그인이 취소가 아니면 카카오계정으로 이어 간다.
      }
    }
    try {
      return (await UserApi.instance.loginWithKakaoAccount()).accessToken;
    } on PlatformException catch (e) {
      if (e.code == 'CANCELED') throw const AuthException.cancelled();
      throw const AuthException(_loginFailed);
    }
  }

  Future<void> _ensureGoogle() {
    return _googleReady ??= GoogleSignIn.instance.initialize(
      clientId: device.isIosDevice && AppConfig.googleIosClientId.isNotEmpty ? AppConfig.googleIosClientId : null,
      serverClientId: AppConfig.googleServerClientId,
    );
  }

  Future<void> _exchange(String path, Map<String, Object?> body) async {
    final http.Response res;
    try {
      res = await _client
          .post(
            Uri.parse('$_base$path'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw const AuthException(_offline);
    } catch (e) {
      if (e is AuthException) rethrow;
      throw const AuthException(_offline);
    }
    if (res.statusCode != 200) throw AuthException(_serverMessage(res) ?? _loginFailed);
    final decoded = jsonDecode(utf8.decode(res.bodyBytes));
    if (decoded is! Map) throw const AuthException(_loginFailed);
    final json = Map<String, dynamic>.from(decoded);
    final userJson = json['user'];
    if (userJson is! Map) throw const AuthException(_loginFailed);
    final tokens = AuthTokens.fromJson(json);
    final user = AuthUser.fromJson(Map<String, dynamic>.from(userJson));
    await _store.saveSession(tokens, user);
    _user = user;
    notifyListeners();
  }

  Future<AuthTokens?> _refresh(AuthTokens current, {bool allowSuperseded = true}) async {
    final http.Response res;
    try {
      res = await _client
          .post(
            Uri.parse('$_base/api/auth/refresh'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'refreshToken': current.refreshToken,
              'deviceId': await _store.deviceId(),
            }),
          )
          .timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw const AuthException(_offline);
    } catch (e) {
      if (e is AuthException) rethrow;
      throw const AuthException(_offline);
    }
    if (res.statusCode == 200) {
      final decoded = jsonDecode(utf8.decode(res.bodyBytes));
      if (decoded is! Map) throw const AuthException(_loginFailed);
      final json = Map<String, dynamic>.from(decoded);
      final tokens = AuthTokens.fromJson(json);
      final userJson = json['user'];
      if (userJson is Map) {
        _user = AuthUser.fromJson(Map<String, dynamic>.from(userJson));
        await _store.saveSession(tokens, _user!);
        notifyListeners();
      } else {
        final user = _user ?? await _store.readUser();
        if (user != null) await _store.saveSession(tokens, user);
      }
      return tokens;
    }
    final code = _errorCode(res);
    if (code == 'refresh_superseded' && allowSuperseded) {
      await Future<void>.delayed(const Duration(seconds: 1));
      final again = await _store.readTokens();
      if (again != null && again.refreshToken != current.refreshToken) {
        if (!again.expiresSoon()) return again;
        return _refresh(again);
      }
      return _refresh(again ?? current, allowSuperseded: false);
    }
    if (code != null && _terminalRefresh.contains(code)) {
      await _clearLocal();
      return null;
    }
    throw AuthException(_serverMessage(res) ?? _offline);
  }
}

/// 서버·키 없이 화면만 끝까지 돈다. access 토큰은 없다.
class MockAuthService extends AuthService {
  MockAuthService({required TokenStore store, this.delay = const Duration(milliseconds: 500)}) : _store = store;

  final TokenStore _store;
  final Duration delay;
  AuthUser? _user;
  bool _skipped = false;

  @override
  AuthUser? get user => _user;

  @override
  bool get skipped => _skipped;

  @override
  Future<void> restore() async {
    _skipped = await _store.isSkipped();
    _user = await _store.readUser();
    notifyListeners();
  }

  @override
  Future<void> skip() async {
    await _store.setSkipped(true);
    _skipped = true;
    notifyListeners();
  }

  @override
  Future<void> loginKakao() => _enter(const ['KAKAO']);

  @override
  Future<void> loginGoogle() => _enter(const ['GOOGLE']);

  @override
  Future<void> loginTest() => _enter(const ['KAKAO']);

  Future<void> _enter(List<String> providers) async {
    await Future<void>.delayed(delay);
    _user = AuthUser(userNo: 0, userType: 'SENIOR', name: '시험 사용자', providers: providers);
    await _store.saveUser(_user!);
    notifyListeners();
  }

  @override
  Future<String?> accessToken({bool forceRefresh = false}) async => null;

  @override
  Future<void> logout() async {
    await _store.clearSession();
    _user = null;
    notifyListeners();
  }

  @override
  Future<void> withdraw() => logout();

  @override
  Future<void> registerPushToken(String token, {required String platform}) async {}
}

Map<String, dynamic>? _body(http.Response res) {
  try {
    final decoded = jsonDecode(utf8.decode(res.bodyBytes));
    if (decoded is Map) return Map<String, dynamic>.from(decoded);
  } catch (_) {}
  return null;
}

String? _errorCode(http.Response res) {
  final error = _body(res)?['error'];
  if (error is Map) return error['code'] as String?;
  return null;
}

String? _serverMessage(http.Response res) {
  final error = _body(res)?['error'];
  if (error is Map && error['userMessage'] is String && (error['userMessage'] as String).isNotEmpty) {
    return error['userMessage'] as String;
  }
  return null;
}
