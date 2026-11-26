/// 서버 토큰 응답 (docs/auth-plan.md §6). 만료 시각은 ExpiresIn(초)으로 계산한다.
class AuthUser {
  const AuthUser({
    required this.userNo,
    required this.userType,
    this.name,
    this.email,
    this.profileImageUrl,
    this.providers = const [],
  });

  final int userNo;
  final String userType;
  final String? name;
  final String? email;
  final String? profileImageUrl;
  final List<String> providers;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      userNo: (json['userNo'] as num).toInt(),
      userType: json['userType'] as String? ?? 'SENIOR',
      name: json['name'] as String?,
      email: json['email'] as String?,
      profileImageUrl: json['profileImageUrl'] as String?,
      providers: [for (final p in (json['providers'] as List?) ?? const []) p.toString()],
    );
  }

  Map<String, dynamic> toJson() => {
        'userNo': userNo,
        'userType': userType,
        'name': name,
        'email': email,
        'profileImageUrl': profileImageUrl,
        'providers': providers,
      };
}

class AuthTokens {
  const AuthTokens({
    required this.accessToken,
    required this.accessExpiresAt,
    required this.refreshToken,
    required this.refreshExpiresAt,
  });

  final String accessToken;
  final DateTime accessExpiresAt;
  final String refreshToken;
  final DateTime refreshExpiresAt;

  /// [now] 는 테스트에서 시계를 고정할 때. 응답의 ExpiresIn 은 초.
  factory AuthTokens.fromJson(Map<String, dynamic> json, {DateTime? now}) {
    final clock = (now ?? DateTime.now()).toUtc();
    return AuthTokens(
      accessToken: json['accessToken'] as String,
      accessExpiresAt: clock.add(Duration(seconds: (json['accessTokenExpiresIn'] as num).toInt())),
      refreshToken: json['refreshToken'] as String,
      refreshExpiresAt: clock.add(Duration(seconds: (json['refreshTokenExpiresIn'] as num).toInt())),
    );
  }

  /// 만료 60초 전이면 갱신한다.
  bool expiresSoon([DateTime? now]) {
    final clock = (now ?? DateTime.now()).toUtc();
    return !accessExpiresAt.toUtc().isAfter(clock.add(const Duration(seconds: 60)));
  }
}
