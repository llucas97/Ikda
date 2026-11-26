/// 빌드할 때 --dart-define 으로 넣는 설정.
///
///   flutter run --dart-define=SERVER_URL=http://10.0.2.2:8000
///   flutter run --dart-define=USE_MOCK=true          (서버 없이 화면만)
///   flutter run --dart-define=KAKAO_NATIVE_APP_KEY=... --dart-define=GOOGLE_SERVER_CLIENT_ID=...
class AppConfig {
  static const serverUrl = String.fromEnvironment('SERVER_URL');
  static const _useMock = String.fromEnvironment('USE_MOCK');

  /// 카카오 네이티브 앱 키. 앱에 들어가도 되는 키다.
  static const kakaoNativeAppKey = String.fromEnvironment('KAKAO_NATIVE_APP_KEY');

  /// 구글 웹 클라이언트 ID. ID 토큰의 aud 가 된다.
  static const googleServerClientId = String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');

  /// iOS 클라이언트 ID. iOS 에서만 쓴다.
  static const googleIosClientId = String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');

  /// true 면 로그인 화면에 '나중에'가 없다.
  static const requireLogin = bool.fromEnvironment('REQUIRE_LOGIN');

  /// true 면 '시험 로그인' 버튼. 서버 AUTH_FAKE_PROVIDER=1 과 함께.
  static const showTestLogin = bool.fromEnvironment('SHOW_TEST_LOGIN');

  /// true 면 가짜 모드에서 예시 서류와 가족 둘을 채워 화면을 미리 본다.
  static const seedDemo = bool.fromEnvironment('SEED_DEMO');

  /// USE_MOCK 을 따로 안 주면: 서버 주소가 없을 때만 가짜 분석·가짜 로그인
  static bool get useMock => _useMock.isEmpty ? serverUrl.isEmpty : _useMock == 'true';
}
