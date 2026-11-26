# 읽어드림 로그인 설계 (카카오·구글 + OAuth 2.0)

> 이 문서는 두 단계로 나눠 만든다.
> **Stage 1 (끝남)**: DB 스키마·모델, 제공자 확인(카카오, 구글 JWKS), 인가 코드 + PKCE + state 흐름, JWT 발급, refresh 회전·재사용 탐지, 로그아웃, 탈퇴, 그리고 그 테스트.
> **Stage 2 (할 일)**: Flutter 로그인 화면·토큰 저장·자동 갱신·로그아웃, USE_MOCK 가짜 로그인, `GET /api/me`, 푸시 토큰 등록, `/api/analyze` 선택 인증, docker-compose, README 한국어 출시 안내.
> 각 항목 옆 표시: ✅ Stage 1 에서 끝남 · ⬜ Stage 2 가 할 일.
> Stage 2 는 보안 핵심 코드(`server/app/auth/*.py`)를 다시 쓰지 말고 **가져다 쓰기만** 한다.

---

## 0. 한눈에

```
[앱] ─카카오 SDK→ 카카오 access token ─┐
[앱] ─구글 SDK→   구글 ID token ───────┼─ POST /api/auth/{kakao|google} ─→ 서버가 제공자에 직접 확인
                                       │                                  (카카오 /v1/user/access_token_info + /v2/user/me,
                                       │                                   구글 JWKS 서명·aud·iss·exp)
[웹/예비] GET /api/auth/{p}/authorize ─┘─ 제공자 ─ GET /callback ─→ 앱 딥링크 ?code=1회용 → POST /api/auth/token (+PKCE)
                                                   ↓
                         우리 토큰: access JWT(15분, HS256) + refresh(무작위, 60일, 회전, 해시 저장)
                         POST /api/auth/refresh · POST /api/auth/logout · DELETE /api/me(탈퇴)
```

---

## 1. AsOne 참고 → 우리 표 (같은 점과 일부러 다른 점)

AsOne(`docs/sql/01_ct_member.sql`, `entity/*.java`, `mapper/*.xml`)의 회원 영역 이름 규칙을 그대로 따른다.

| 규칙 | AsOne | 읽어드림 |
|---|---|---|
| 표 접두사 | `ct_` (회원 영역) | `ct_` 그대로 |
| PK | `<이름>_no BIGSERIAL` | 같음 (`user_no`, `access_no`, `push_token_no` …) |
| 코드값 / 여부 | `_cd VARCHAR`, `_yn BOOLEAN` | 같음 |
| 시각 | `TIMESTAMPTZ` (99_utc_timestamptz.sql) | 처음부터 모두 `TIMESTAMPTZ`, UTC 저장 |
| 감사 컬럼 | `created_at/by`, `updated_at/by` | 같음 |
| 논리삭제 | `deleted_yn` | 같음 + 탈퇴 시 개인정보 지움 |
| 주석 | `COMMENT ON` 한국어 | 같음 |
| 마이그레이션 | `ci/sql/V0001__*.sql` (Flyway 식) | `server/db/migrations/V0001__ct_member.sql` + `db/migrate.py` |

### 표·컬럼 매핑

| AsOne | 읽어드림 | 비고 |
|---|---|---|
| `ct_user` | `ct_user` | |
| `ct_user.user_no` | `ct_user.user_no` | |
| `ct_user.user_grade_cd` (ADMIN/MEMBER), `UserType` enum | `user_grade_cd` (MEMBER/ADMIN) | AsOne `UserType` 과 같은 뜻 |
| (없음) | `user_type_cd` (SENIOR/CHILD) | 가족 연결 기능 대비 **새로 추가** |
| `email`, `name`, `mobile_phone`, `birth_date`, `gender_cd` | 같은 이름 | email 은 제공자가 확인한 것만, 찾는 키로 안 씀 |
| `profile_photo_file_no` (파일 테이블) | `profile_image_url` | 우리는 파일 테이블이 없어 제공자 사진 주소 |
| `status_cd`, `status_reason`, `status_changed_at`, `suspend_until`, `withdraw_at`, `withdraw_type_cd` | 같은 이름 | ACTIVE/SUSPEND/WITHDRAW, SELF/FORCE |
| `join_channel_cd` | `join_channel_cd` | KAKAO/GOOGLE |
| `oauth_provider_cd`, `oauth_id` (ct_user 에 한 칸) | **`ct_user_oauth`** 로 분리 | 한 회원에 카카오·구글 여러 개, (제공자, ID) 유일 |
| `last_login_at`, `last_login_client_cd` | 같음 + `last_login_provider_cd` | |
| `password_hash`, `crew_no`, `referral_code`, `membership_type_cd`, `topzone_*` … | 없음 | 비밀번호 로그인·다른 도메인은 안 씀 |
| `User` 의 transient `oauthEmail/oauthName/oauthPicture` | `ct_user_oauth.oauth_email/oauth_name/oauth_picture` | 실제 컬럼으로 |
| `ct_user_access` | `ct_user_access` | 같은 표 이름·역할(로그인 토큰 이력) |
| `access_token VARCHAR(500)` (원문) | `access_jti` | **원문 저장 안 함** |
| `refresh_token VARCHAR(500)` (원문 JWT) | `refresh_token_hash CHAR(64)` | **SHA-256 만**, 유일 인덱스 |
| `client_type_cd`, `device_id`, `device_os`, `user_agent`, `ip_address`, `expires_at`, `refresh_expires_at`, `revoked_yn`, `created_at` | 같은 이름 | |
| (transient `provider`) | `login_provider_cd` | 실제 컬럼으로 |
| (없음) | `token_family`, `parent_access_no`, `auth_at`, `used_at`, `revoked_at`, `revoke_reason_cd` | 회전·재사용 탐지용 **새로 추가** |
| `ct_admin_login_log` (관리자용) | `ct_user_login_log` | 회원용으로. `event_cd`, `success_yn`, `fail_reason` 같은 이름 |
| `ct_user_push_token` (실제 7컬럼) + `A1_push_token_unique.sql` | `ct_user_push_token` + `ux_ct_user_push_token_user_token` | AsOne 매퍼 주석이 지적한 빠진 `device_id` 를 **추가** |
| `OAuthProvider` enum (GOOGLE/KAKAO/NAVER/…) | `oauth_provider_cd` 값 `KAKAO`/`GOOGLE` (+시험용 `FAKE`) | |
| (없음, state 고정값 `"google"`) | `ct_oauth_authorize` | state·PKCE·nonce·1회용 코드 저장 **새로 추가** |

### 코드 매핑

| AsOne | 읽어드림 |
|---|---|
| `oauth/OAuth2UserInfo`, `KakaoOAuth2UserInfo`, `GoogleOAuth2UserInfo`, `OAuth2UserInfoFactory` | `app/auth/providers.py` (`ProviderProfile`, `KakaoProvider.profile`, `GoogleProvider.profile`, `Providers.get`) |
| `oauth/OAuthClientRedirect` (successUrl / loginFailedUrl / errorUrl) | `app/auth/redirect.py` (`success_url`, `login_failed_url`, 허용 목록 `is_allowed`) |
| `controller/OAuthLoginController` (authorize·callback) | `app/auth/routes.py` + `service.begin_authorize / complete_callback` |
| `config/OAuth2SuccessHandler` | 콜백 끝의 302 (`complete_callback` 이 앱 주소를 돌려줌) |
| `util/JwtUtil` (tokenType ACCESS/REFRESH) | `app/auth/tokens.py` (`typ=access`) |
| `security/JwtAuthenticationFilter` (Bearer → 회원) | `app/auth/deps.py` `current_auth` / `optional_auth` + `service.authenticate` |
| `config/SecurityConfig` (STATELESS, csrf off, permitAll 목록) | FastAPI 는 기본이 무상태. 보호할 엔드포인트에만 `Depends(current_auth)` |
| `dto/AuthResponse` (success, message, accessToken, refreshToken, user) | 토큰 응답 JSON (§6). `success/message` 대신 기존 서버처럼 HTTP 상태 + `{"error":{code,userMessage}}` |
| `UserService.createAuthTokensAndSaveSession` / `refreshToken` / `logout` | `service.start_session` / `rotate_refresh` / `logout` |
| `cleanupOldSessions` (최근 5개) | `_enforce_session_limit` (`MAX_SESSIONS_PER_USER=5`) |
| `UserPushTokenMapper.insertOrUpdatePushToken` (ON CONFLICT) | ⬜ Stage 2 `POST /api/me/push-token` |

### 일부러 다르게 한 것 (보안)

1. **이메일로 회원을 찾지 않는다.** AsOne `saveOrUpdateUser` 는 이메일이 같으면 기존 회원에 붙였다. 카카오 이메일은 확인 안 된 것일 수 있어 남의 계정을 가로챌 수 있다. 회원은 (제공자, 제공자 ID) 로만 찾는다. 같은 사람이 카카오·구글로 각각 들어오면 회원이 둘이다(연결 기능은 나중에 로그인한 상태에서 "구글도 연결" 으로).
2. **카카오 이메일 필수를 없앴다.** AsOne 은 이메일 없으면 가입을 막았다(`KAKAO_EMAIL_REQUIRED`). 어르신은 이메일이 없는 경우가 많고, 카카오 이메일 필수 동의는 비즈 앱 심사가 필요하다.
3. **토큰을 딥링크에 싣지 않는다.** AsOne 은 `asone://oauth/callback?accessToken=…&refreshToken=…`. 여기서는 1회용 코드만 싣고, 앱이 PKCE verifier 와 함께 `POST /api/auth/token` 으로 바꾼다 (RFC 8252). 같은 스킴을 가로챈 앱은 verifier 가 없어 쓸 수 없다.
4. **state 를 진짜로 쓴다.** AsOne 은 `state=google` 고정(CSRF 방어 없음). 여기서는 무작위 256비트, 해시로 저장, 10분, 한 번만.
5. **카카오 토큰의 앱 확인.** 다른 카카오 앱이 받은 토큰을 우리 서버에 넣는 공격을 막으려고 `/v1/user/access_token_info` 의 `app_id` 를 `KAKAO_APP_ID` 와 비교한다.
6. **refresh 를 JWT 가 아닌 무작위 값으로, 해시만 저장, 쓸 때마다 회전, 재사용하면 세션 전체 폐기.**
7. **access 토큰도 즉시 끊긴다.** 매 요청마다 `sid`(세션)가 폐기됐는지 DB 에서 본다(인덱스 한 번). 로그아웃·탈퇴·탈취 탐지 후 15분을 기다리지 않는다.

---

## 2. 스키마 ✅

정본은 `server/db/migrations/V0001__ct_member.sql` (주석 포함). 모델은 `server/app/auth/models.py`. 둘이 어긋나면 `tests/test_auth_schema.py` 가 깨진다.
PostgreSQL 은 `python db/migrate.py` 로 적용(적용 기록 `sy_schema_migration`). SQLite(개발·테스트)는 서버가 처음 연결할 때 모델에서 만든다. Docker Postgres 17 에 실제로 적용해 보고 전체 테스트를 Postgres 로도 돌려 통과했다.

```sql
ct_user (
  user_no BIGSERIAL PK, user_type_cd VARCHAR(20) NOT NULL DEFAULT 'SENIOR', user_grade_cd VARCHAR(20) NOT NULL DEFAULT 'MEMBER',
  email VARCHAR(100), name VARCHAR(50), mobile_phone VARCHAR(20), birth_date DATE, gender_cd VARCHAR(10),
  profile_image_url VARCHAR(500), status_cd VARCHAR(20) NOT NULL DEFAULT 'ACTIVE', status_reason VARCHAR(500),
  status_changed_at TIMESTAMPTZ, suspend_until TIMESTAMPTZ, withdraw_at TIMESTAMPTZ, withdraw_type_cd VARCHAR(20),
  join_channel_cd VARCHAR(30), last_login_at TIMESTAMPTZ, last_login_provider_cd VARCHAR(20), last_login_client_cd VARCHAR(20),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_by BIGINT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_by BIGINT,
  deleted_yn BOOLEAN NOT NULL DEFAULT FALSE)

ct_user_oauth (
  oauth_no BIGSERIAL PK, user_no BIGINT NOT NULL → ct_user, oauth_provider_cd VARCHAR(20) NOT NULL, oauth_id VARCHAR(100),
  oauth_email VARCHAR(100), oauth_email_verified_yn BOOLEAN, oauth_name VARCHAR(100), oauth_picture VARCHAR(500),
  linked_at, last_login_at, unlinked_at TIMESTAMPTZ, unlink_result_cd VARCHAR(30), created_at, updated_at, deleted_yn)
  UNIQUE (oauth_provider_cd, oauth_id) WHERE deleted_yn = FALSE      -- ux_ct_user_oauth_provider_id
  UNIQUE (user_no, oauth_provider_cd)  WHERE deleted_yn = FALSE      -- ux_ct_user_oauth_user_provider

ct_user_access (
  access_no BIGSERIAL PK, user_no → ct_user, client_type_cd VARCHAR(20) DEFAULT 'APP', token_family VARCHAR(64) NOT NULL,
  parent_access_no BIGINT, access_jti VARCHAR(64) NOT NULL, refresh_token_hash CHAR(64) NOT NULL, login_provider_cd VARCHAR(20),
  device_id VARCHAR(100), device_os VARCHAR(30), user_agent VARCHAR(500), ip_address VARCHAR(50),
  auth_at, expires_at, refresh_expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ,
  revoked_yn BOOLEAN NOT NULL DEFAULT FALSE, revoked_at TIMESTAMPTZ, revoke_reason_cd VARCHAR(30), created_at)
  UNIQUE (refresh_token_hash); INDEX (token_family); INDEX (user_no, created_at)

ct_user_login_log (
  login_log_no BIGSERIAL PK, user_no BIGINT, event_cd VARCHAR(30) NOT NULL, oauth_provider_cd, client_type_cd, device_id,
  ip_address, user_agent, success_yn BOOLEAN, fail_reason VARCHAR(200), created_at)
  event_cd: LOGIN / LOGIN_FAIL / SIGNUP / REUSE_DETECTED / LOGOUT / LOGOUT_ALL / WITHDRAW

ct_user_push_token (
  push_token_no BIGSERIAL PK, user_no → ct_user, push_token VARCHAR(500) NOT NULL, platform_cd VARCHAR(20), device_id VARCHAR(100),
  active_yn BOOLEAN NOT NULL DEFAULT TRUE, created_at, updated_at)
  UNIQUE (user_no, push_token)                                        -- AsOne A1 과 같음

ct_oauth_authorize (
  authorize_no BIGSERIAL PK, oauth_provider_cd, state_hash CHAR(64) NOT NULL UNIQUE, provider_code_verifier VARCHAR(128) NOT NULL,
  nonce VARCHAR(64), app_redirect_uri VARCHAR(500) NOT NULL, app_state VARCHAR(200), app_code_challenge VARCHAR(128) NOT NULL,
  user_type_cd, device_id, expires_at NOT NULL, callback_at, user_no, is_new_user_yn, login_code_hash CHAR(64) UNIQUE,
  login_code_expires_at, consumed_at, issued_token_family VARCHAR(64), created_at)
```

나중(가족 연결)에 붙일 표 — 지금은 만들지 않는다: `ct_family_link (family_link_no, senior_user_no, child_user_no, invite_code_hash, status_cd, linked_at, …)`.

정리 작업(나중): `ct_oauth_authorize` 중 하루 지난 행, `ct_user_access` 중 `refresh_expires_at` 이 90일 지난 행은 지워도 된다(AsOne `deleteExpiredTokens` 와 같음). 지금은 크론이 없다.

---

## 3. 토큰 설계 ✅

### access token (JWT, HS256, `JWT_SECRET` 32바이트 이상)

```json
// 헤더 {"alg":"HS256","typ":"at+jwt"}
{
  "iss": "ilgeodeurim",        // JWT_ISSUER
  "aud": "ilgeodeurim-app",    // JWT_AUDIENCE
  "sub": "42",                 // ct_user.user_no (문자열)
  "iat": 1795400000, "nbf": 1795400000,
  "exp": 1795400900,           // ACCESS_TOKEN_TTL_MIN=15
  "jti": "9f…",                // ct_user_access.access_jti
  "sid": "c1…",                // ct_user_access.token_family (세션)
  "typ": "access",             // AsOne tokenType=ACCESS 와 같은 역할
  "utype": "SENIOR"            // 참고용. 권한 판단은 DB 의 user_type_cd 로
}
```

검증(`tokens.decode_access_token`): 알고리즘 HS256 고정, iss/aud/exp/iat/sub/jti 필수, 시계 오차 10초, `typ == access`, `sid` 있음.
그 다음 `service.authenticate`: 회원이 ACTIVE·삭제 안 됨 + `token_family = sid` 인 행 중 `revoked_yn = FALSE` 가 하나라도 있음. 아니면 401.

### refresh token

- `secrets.token_urlsafe(32)` (256비트, 43자). DB 에는 `sha256_hex` 만.
- 수명: `REFRESH_TOKEN_TTL_DAYS=60` (쓸 때마다 다시 60일, 미끄러짐) · 세션 최대 `SESSION_MAX_DAYS=365` (처음 로그인 `auth_at` 기준, 넘으면 다시 로그인).
  어르신이 자주 다시 로그인하지 않게 길게 잡았다(AsOne 은 1년). 짧게 하려면 환경변수만.
- 세션 수: 회원당 `MAX_SESSIONS_PER_USER=5`. 넘으면 가장 오래된 세션 폐기(`SESSION_LIMIT`).

### 회전과 재사용 탐지 (`service.rotate_refresh`)

```
refresh 받음 → 해시로 행 찾기 (PostgreSQL 은 FOR UPDATE)
  없음                         → 401 invalid_refresh
  revoked_yn                   → 401 refresh_revoked
  used_at 있음 (이미 한 번 씀)
     used_at 이 30초 이내       → 401 refresh_superseded   (동시 갱신. 세션은 그대로. REFRESH_REUSE_GRACE_S)
     30초 넘음                 → 세션 전체 폐기(REUSE_DETECTED) + 로그 → 401 refresh_reused
  refresh_expires_at 지남 또는 auth_at+365일 지남 → 401 refresh_expired
  회원이 ACTIVE 아님           → 세션 폐기(USER_INACTIVE) → 401 user_inactive
  UPDATE … SET used_at=now WHERE access_no=? AND used_at IS NULL AND revoked_yn=FALSE
     바뀐 행이 1개가 아님(경쟁에서 짐) → 401 refresh_superseded
  같은 token_family 로 새 행(parent_access_no = 이전 행, auth_at 그대로) → 새 access + 새 refresh
```

유예 시간 안의 재사용은 **토큰을 내주지 않는다**(세션만 살려 둔다). 그래서 공격자가 유예를 노려도 얻는 것이 없다.

### 로그아웃 (`service.logout`) — 언제나 204

- 본문 `refreshToken` 이 있으면 그 세션 폐기(`LOGOUT`). 단, Bearer 도 같이 왔는데 회원이 다르면 남의 세션은 건드리지 않고 Bearer 쪽 세션만 폐기.
- refresh 없이 Bearer 만 있으면 그 `sid` 폐기.
- `allDevices: true` 는 Bearer 필수 → 회원의 모든 세션 폐기(`LOGOUT_ALL`) + 모든 푸시 토큰 끔.
- `deviceId` 가 오면 그 기기 푸시 토큰 끔.

### 탈퇴 (`service.withdraw`, `DELETE /api/me`)

1. 살아 있는 소셜 연결마다 연결 끊기 (실패해도 탈퇴는 계속, 결과를 `unlink_result_cd` 에 기록)
   - 카카오: `KAKAO_ADMIN_KEY` 가 있으면 `POST https://kapi.kakao.com/v1/user/unlink` (`Authorization: KakaoAK {어드민 키}`, `target_id_type=user_id&target_id={카카오 회원번호}`). 없으면 앱이 보낸 `kakaoAccessToken` 으로 Bearer 호출. 둘 다 없으면 SKIPPED.
   - 구글: 서버에 구글 토큰이 없어 SKIPPED. **앱이 `GoogleSignIn.disconnect()` 를 부른다.**
2. 연결 행: `deleted_yn=TRUE`, `oauth_id=NULL`, 이메일·이름·사진 NULL (같은 계정으로 다시 가입 가능)
3. 모든 세션 폐기(`WITHDRAW`), 모든 푸시 토큰 끔
4. 회원 행: `status_cd=WITHDRAW`, `withdraw_at`, `withdraw_type_cd=SELF`, `deleted_yn=TRUE`, 이메일·이름·전화·생일·성별·사진 NULL
5. `ct_user_login_log` 에 WITHDRAW

---

## 4. 흐름 ✅ (서버) / ⬜ (앱)

### 흐름 A — 모바일 SDK (Android·iOS 기본)

```
앱: 카카오 SDK 로그인 → OAuthToken.accessToken
    POST /api/auth/kakao {"accessToken": "...", "deviceId": "...", "deviceOs": "ANDROID"}
서버: GET kapi /v1/user/access_token_info (Bearer) → app_id == KAKAO_APP_ID ?
      GET kapi /v2/user/me?secure_resource=true (Bearer) → id 가 같은지
      (KAKAO, id) 로 회원 찾기/만들기 → 우리 토큰

앱: google_sign_in (serverClientId = 웹 클라이언트 ID) → idToken
    POST /api/auth/google {"idToken": "..."}
서버: JWKS(https://www.googleapis.com/oauth2/v3/certs, Cache-Control 동안 캐시)로 RS256 서명 확인,
      iss ∈ {accounts.google.com, https://accounts.google.com}, aud ∈ GOOGLE_CLIENT_IDS, exp/iat(오차 60초), sub,
      aud 가 여러 개면 azp ∈ GOOGLE_CLIENT_IDS → (GOOGLE, sub) 로 회원 찾기/만들기 → 우리 토큰
```

### 흐름 B — 서버 인가 코드 + PKCE + state (Flutter 웹, 예비)

```
앱: verifier = 무작위 43~128자, challenge = BASE64URL(SHA256(verifier)), appState = 무작위
    브라우저로 GET /api/auth/{kakao|google}/authorize
        ?redirect_uri=ilgeodeurim://oauth/callback   (APP_REDIRECT_URIS 에 정확히 있는 것만. 아니면 400 JSON, 리다이렉트 안 함)
        &state=appState&code_challenge=challenge&code_challenge_method=S256   (S256 만. 없거나 plain 이면 앱으로 오류)
        [&user_type=SENIOR|CHILD][&device_id=…]
서버: state(256비트)·제공자용 verifier·nonce 를 새로 만들어 ct_oauth_authorize 에 (state 는 해시, 10분)
      302 → 카카오: kauth /oauth/authorize?client_id=REST키&redirect_uri=…/api/auth/kakao/callback&response_type=code&state&code_challenge&code_challenge_method=S256
            구글:   accounts.google.com/o/oauth2/v2/auth?client_id=웹ID&redirect_uri=…&scope=openid email profile&state&nonce&code_challenge&code_challenge_method=S256&prompt=select_account
제공자 → GET /api/auth/{p}/callback?code&state   (또는 error=access_denied)
서버: state 해시로 행 찾기 + 제공자 일치 + UPDATE callback_at WHERE callback_at IS NULL AND expires_at > now (한 번만)
      코드 교환(제공자용 verifier 포함, 카카오는 client_secret, 구글은 client_secret)
        카카오: access_token → 흐름 A 와 같은 확인
        구글:   id_token → 흐름 A 와 같은 확인 + aud == 웹 ID + nonce 일치
      회원 찾기/만들기 → 1회용 로그인 코드(256비트, 2분, 해시 저장)
      302 → ilgeodeurim://oauth/callback?code=…&state=appState
      실패는 모두 302 → ilgeodeurim://oauth/callback?error=login_failed&provider=…&reason=…&message=…&state=…
앱: state == appState 확인 → POST /api/auth/token {"code","codeVerifier","redirectUri"}
서버: 코드 해시로 행 찾기, UPDATE consumed_at WHERE consumed_at IS NULL (먼저 태운다)
      만료·redirectUri 불일치·PKCE 불일치면 400 invalid_grant (코드는 이미 탔다)
      이미 쓴 코드가 다시 오면 그 코드로 낸 세션도 폐기(CODE_REPLAY)
      → 우리 토큰
```

> 카카오 PKCE: 카카오 인가 요청은 `code_challenge`/`code_challenge_method` 를 받는다. 혹시 콘솔 설정상 거부되면 `KAKAO_USE_PKCE=0` 으로 끄면 된다(state·client_secret·앱 쪽 PKCE 는 그대로).

### 시험용 가짜 제공자 (`AUTH_FAKE_PROVIDER=1` 일 때만)

- 흐름 A: `POST /api/auth/fake {"accessToken": "fake:<id>[:<이름>]"}`
- 흐름 B: `/api/auth/fake/authorize` 가 바로 우리 콜백으로 돌아온다(`login_hint` 로 id 지정). 코드 안에 PKCE challenge 를 담아 진짜처럼 확인.
- 끄면 404. 켜져 있으면 서버 시작 로그에 경고. **운영에서는 끈다.**

---

## 5. 제공자 확인 상세 ✅ (`app/auth/providers.py`, `app/auth/oidc.py`)

| | 카카오 | 구글 |
|---|---|---|
| 앱이 보내는 것 | access token (SDK `OAuthToken.accessToken`) | ID token (SDK `idToken`) |
| 서버 확인 | `GET https://kapi.kakao.com/v1/user/access_token_info` → `app_id == KAKAO_APP_ID`, 이어 `GET /v2/user/me?secure_resource=true` → `id` 같음 | JWKS 로 RS256 서명, `alg` 가 RS256 이 아니면 거절(알고리즘 바꿔치기 방지), `kid` 필수 |
| 회원 ID | `id` (숫자 → 문자열) | `sub` |
| 이메일 | `kakao_account.email`. `is_email_valid && is_email_verified` 일 때만 확인된 것으로 | `email`, `email_verified == true` 일 때만 |
| 이름·사진 | `kakao_account.profile.nickname/profile_image_url` (없으면 `properties.*`), `is_default_image` 면 사진 없음 | `name`, `picture` |
| 설정 안 됨 | `KAKAO_APP_ID` 없으면 503 `kakao_not_configured` | `GOOGLE_CLIENT_IDS` 없으면 503 `google_not_configured` |
| 제공자 장애 | 5xx·연결 실패 → 502 | JWKS 실패 → 예전 키로 버팀, 그것도 없으면 503 |
| 키 회전 | — | 모르는 `kid` 면 JWKS 를 다시 받되 60초에 한 번만 |
| 연결 끊기 | `/v1/user/unlink` (어드민 키 또는 사용자 토큰) | 앱 `disconnect()` |

모든 제공자 HTTP 는 `deps.get_http`(요청마다 `httpx.AsyncClient`, 제한 8초)로 나간다. 테스트는 `app.dependency_overrides[get_http]` 로 `httpx.MockTransport` 를 넣는다. 로그에는 토큰·이메일을 남기지 않고 사유 코드만.

---

## 6. API 계약

공통 오류 모양(기존 `/api/analyze` 와 같음): `{"error": {"code": "refresh_reused", "userMessage": "다시 로그인해 주세요."}}`. 401 에는 `WWW-Authenticate: Bearer error="invalid_token"`. 토큰 응답에는 `Cache-Control: no-store`.

### 토큰 응답 (로그인·`/token`·`/refresh` 공통)

```json
{
  "tokenType": "Bearer",
  "accessToken": "eyJ…",
  "accessTokenExpiresIn": 900,
  "refreshToken": "Q2x…",
  "refreshTokenExpiresIn": 5184000,
  "isNewUser": true,                // 로그인·/token 에만 (refresh 응답에는 없음)
  "user": {
    "userNo": 42,
    "userType": "SENIOR",           // SENIOR | CHILD
    "name": "박영감",
    "email": null,                  // 확인된 이메일만
    "profileImageUrl": "https://…",
    "providers": ["KAKAO"]          // KAKAO | GOOGLE | FAKE
  }
}
```

### ✅ `POST /api/auth/{provider}` — provider ∈ kakao, google, fake (그 밖은 422)

```json
// 요청
{"accessToken": "카카오 토큰",        // kakao, fake
 "idToken": "구글 ID 토큰",           // google
 "deviceId": "설치 ID(선택, ≤100)", "deviceOs": "ANDROID|IOS|WEB (선택)",
 "userType": "SENIOR|CHILD (선택, 처음 가입할 때만 반영)"}
```
200 토큰 응답 · 400 `token_missing` · 401 `kakao_token_invalid` `kakao_app_mismatch` `kakao_id_mismatch` `id_token_*` · 403 `user_inactive` · 502 `kakao_unavailable` · 503 `*_not_configured` `jwks_unavailable`

### ✅ `GET /api/auth/{provider}/authorize` · `GET /api/auth/{provider}/callback`

§4 흐름 B. 둘 다 302. authorize 의 `redirect_uri` 가 허용 목록에 없을 때만 400 JSON(`invalid_redirect_uri`).
앱으로 가는 오류 `reason`: `invalid_state`, `invalid_code_challenge`, `cancelled`, `provider_error`, `kakao_code_rejected`, `google_code_rejected`, `id_token_bad_nonce`, `*_not_configured`, …

### ✅ `POST /api/auth/token`

```json
{"grantType": "authorization_code", "code": "딥링크의 code", "codeVerifier": "앱이 만든 verifier",
 "redirectUri": "ilgeodeurim://oauth/callback", "deviceId": "…", "deviceOs": "…"}
```
200 토큰 응답 · 400 `invalid_grant` · 403 `user_inactive`

### ✅ `POST /api/auth/refresh`

```json
{"refreshToken": "…", "deviceId": "(선택)"}
```
200 토큰 응답(isNewUser 없음) · 401 `invalid_refresh` `refresh_revoked` `refresh_superseded` `refresh_reused` `refresh_expired` `user_inactive`

### ✅ `POST /api/auth/logout` — Bearer 선택

```json
{"refreshToken": "(선택)", "allDevices": false, "deviceId": "(선택)"}
```
204 (본문 없어도 됨) · 401 `login_required`(allDevices 인데 Bearer 없음) / Bearer 가 틀렸을 때

### ✅ `DELETE /api/me` — Bearer 필수

```json
// 본문 선택
{"kakaoAccessToken": "카카오 SDK 의 현재 토큰 (어드민 키가 없을 때 연결 끊기에 씀)"}
// 200
{"ok": true, "unlinked": {"KAKAO": "OK"}}       // OK | FAILED | SKIPPED
```

### ⬜ `GET /api/me` — Bearer 필수 (Stage 2)

```json
{"userNo": 42, "userType": "SENIOR", "name": "박영감", "email": null, "profileImageUrl": "…",
 "providers": ["KAKAO"], "createdAt": "2026-11-17T03:00:00Z"}
```
구현: `auth: AuthContext = Depends(current_auth)`, `db = Depends(get_session)` → `routes.user_json(auth.user, await service.providers_of(db, auth.user.user_no))` + `createdAt`(ISO, UTC). 401 은 `current_auth` 가 처리.

### ⬜ `POST /api/me/push-token` — Bearer 필수 (Stage 2)

```json
{"pushToken": "FCM/APNs 토큰(≤500)", "platform": "ANDROID|IOS|WEB", "deviceId": "(선택)"}
```
204. AsOne `insertOrUpdatePushToken` 처럼: 같은 `(user_no, push_token)` 이면 `active_yn=TRUE, platform_cd, device_id, updated_at` 만 갱신 (PostgreSQL `ON CONFLICT (user_no, push_token) DO UPDATE`, SQLite 도 SQLAlchemy `sqlite.insert(...).on_conflict_do_update` 로 같은 동작). 그리고 같은 토큰을 가진 **다른 회원** 행은 `active_yn=FALSE` (AsOne `deactivateOtherDevicesWithSameToken`). `platform_cd` 는 대문자로 저장.

### ⬜ `/api/analyze` 선택 인증 (Stage 2)

환경변수 `AUTH_REQUIRED_FOR_ANALYZE` (기본 끔). `auth: AuthContext | None = Depends(optional_auth)` 를 붙이고, 켜져 있는데 `auth is None` 이면 `_err(401, "login_required", "로그인해 주세요.")`. `optional_auth` 는 토큰이 없으면 DB 를 열지 않으므로 끈 상태에서는 지금과 똑같이 동작한다. 토큰이 틀리면(있는데 무효) 플래그와 상관없이 401(`AuthError` 처리기).

### 오류 코드 → 앱 동작

| code | 앱 동작 |
|---|---|
| `token_expired` (access) | refresh 한 번 → 원래 요청 다시 |
| `refresh_superseded` | 1초 기다렸다가 저장소에서 토큰 다시 읽기. 바뀌었으면 그걸로, 안 바뀌었으면 한 번만 다시 refresh |
| `invalid_token` `session_revoked` `user_inactive` `refresh_*` `invalid_refresh` `login_required` | 저장된 토큰 지우고 로그인 화면 |
| 네트워크 오류 | 토큰은 그대로 두고 "인터넷 연결을 확인해 주세요" |

---

## 7. 환경변수 (서버)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | (없음 → `sqlite+aiosqlite:///./ilgeodeurim.db`) | `postgresql://user:pw@host:5432/db` 도 받는다(asyncpg 로 바꿔 씀) |
| `DB_AUTO_CREATE` | 끔 | `1` 이면 Postgres 에서도 모델로 표 생성 (평소엔 `db/migrate.py`) |
| `DB_NULL_POOL` | 끔 | `1` 이면 연결 풀 없음 (테스트용) |
| `JWT_SECRET` | (없으면 임시 키 + 경고) | **운영 필수.** 32바이트 이상. 예: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `ilgeodeurim` / `ilgeodeurim-app` | |
| `ACCESS_TOKEN_TTL_MIN` | `15` | |
| `REFRESH_TOKEN_TTL_DAYS` | `60` | |
| `SESSION_MAX_DAYS` | `365` | |
| `REFRESH_REUSE_GRACE_S` | `30` | |
| `MAX_SESSIONS_PER_USER` | `5` | `0` 이면 제한 없음 |
| `OAUTH_STATE_TTL_S` / `LOGIN_CODE_TTL_S` | `600` / `120` | |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | 콜백 주소 `{이것}/api/auth/{p}/callback` 의 앞부분. 운영은 https |
| `APP_REDIRECT_URIS` | `ilgeodeurim://oauth/callback` | 쉼표 목록, 정확히 일치. 첫 번째가 기본 실패 주소 |
| `KAKAO_APP_ID` | — | 카카오 앱 ID(숫자). **모바일 카카오 로그인에 필수** (토큰의 app_id 확인) |
| `KAKAO_REST_API_KEY` | — | 서버 흐름(인가 코드)용 |
| `KAKAO_CLIENT_SECRET` | — | 콘솔에서 Client Secret 을 켰으면 |
| `KAKAO_ADMIN_KEY` | — | 탈퇴 시 연결 끊기(서버만 보관, 앱에 넣지 말 것) |
| `KAKAO_REDIRECT_URI` / `GOOGLE_REDIRECT_URI` | (PUBLIC_BASE_URL 로 만듦) | 직접 지정할 때 |
| `KAKAO_USE_PKCE` | `1` | |
| `KAKAO_SCOPE` | (없음 → 콘솔 동의항목 기본) | 예: `profile_nickname,profile_image` |
| `GOOGLE_CLIENT_IDS` | — | 받을 ID 토큰 aud 목록: 웹·Android·iOS 클라이언트 ID 쉼표로 (`GOOGLE_CLIENT_ID` 도 받음) |
| `GOOGLE_WEB_CLIENT_ID` | (`GOOGLE_CLIENT_IDS` 첫 번째) | 서버 흐름·앱 `serverClientId` |
| `GOOGLE_CLIENT_SECRET` | — | 서버 흐름용 (웹 클라이언트) |
| `AUTH_FAKE_PROVIDER` | 끔 | `1` 이면 가짜 제공자 (시험만) |
| `TRUST_PROXY_HEADERS` | 끔 | `1` 이면 `X-Forwarded-For` 를 IP 로 (Cloud Run 등 프록시 뒤에서만) |
| ⬜ `AUTH_REQUIRED_FOR_ANALYZE` | 끔 | Stage 2 |

---

## 8. Flutter 화면·흐름 ⬜ (Stage 2)

Flutter 가 이 PC 에 없다. `flutter analyze` 로 확인하지 못했다고 README·보고에 적을 것.

### 패키지 (`app/pubspec.yaml`)

- `kakao_flutter_sdk_user` (최신 안정판), `google_sign_in` (7.x 는 API 가 6.x 와 다르다: `GoogleSignIn.instance.initialize(serverClientId: …)` → `authenticate()` → `account.authentication.idToken`. 쓰는 버전의 README 를 확인하고 맞춰 쓸 것), `flutter_secure_storage`.
- 웹 서버 흐름을 하면 `url_launcher` (같은 창 이동) — 선택.

### dart-define (`lib/config.dart`)

| 이름 | 설명 |
|---|---|
| `KAKAO_NATIVE_APP_KEY` | 카카오 네이티브 앱 키 (앱에 들어가도 되는 키) |
| `GOOGLE_SERVER_CLIENT_ID` | 구글 **웹** 클라이언트 ID (ID 토큰 aud 가 이것이 됨) |
| `GOOGLE_IOS_CLIENT_ID` | iOS 클라이언트 ID (iOS 만) |
| `REQUIRE_LOGIN` | `true` 면 로그인 화면에 '나중에' 없음 (기본 false — 지금처럼 로그인 없이도 쓸 수 있게) |
| `SHOW_TEST_LOGIN` | `true` 면 '시험 로그인' 버튼 (서버 `AUTH_FAKE_PROVIDER=1` 과 함께) |

### 파일

- `lib/models/auth_session.dart`: `AuthUser {userNo, userType, name, email, profileImageUrl, providers}`, `AuthTokens {accessToken, accessExpiresAt(DateTime, 응답의 ExpiresIn 으로 계산), refreshToken, refreshExpiresAt}`, `fromJson`.
- `lib/services/token_store.dart`: `flutter_secure_storage` 래퍼. 키 `auth.access`, `auth.accessExp`, `auth.refresh`, `auth.refreshExp`, `auth.user`(JSON), `auth.deviceId`(처음 실행 때 무작위 UUID 를 만들어 계속 씀). Android `encryptedSharedPreferences` 옵션, iOS `first_unlock` 접근성.
- `lib/services/auth_service.dart`:
  - `abstract class AuthService { AuthUser? get user; Stream/ChangeNotifier; Future<void> loginKakao(); loginGoogle(); loginTest(); Future<String?> accessToken(); Future<void> logout(); Future<void> withdraw(); }`
  - `HttpAuthService(serverUrl, store)`:
    - `loginKakao`: `isKakaoTalkInstalled()` 면 `UserApi.instance.loginWithKakaoTalk()`, 실패(취소 제외)·미설치면 `loginWithKakaoAccount()` → `POST /api/auth/kakao {accessToken, deviceId, deviceOs}`.
    - `loginGoogle`: `idToken` → `POST /api/auth/google {idToken, deviceId, deviceOs}`. idToken 이 null 이면 serverClientId 설정 문제로 안내.
    - `accessToken()`: 만료 60초 전이면 refresh. **refresh 는 한 번에 하나만**(진행 중인 `Future` 를 공유). §6 오류 표대로 처리. 새 토큰은 저장 후 돌려준다.
    - `logout`: `POST /api/auth/logout {refreshToken, deviceId}` + Bearer (실패해도 계속) → 저장소 지움 → `UserApi.instance.logout()`(카카오, 무시 가능 오류), `GoogleSignIn.instance.signOut()`.
    - `withdraw`: 카카오 연결이면 `TokenManagerProvider.instance.manager.getToken()` 의 accessToken 을 `kakaoAccessToken` 으로 → `DELETE /api/me` → 구글 연결이면 `disconnect()` → 저장소 지움.
  - `MockAuthService` (USE_MOCK): 0.5초 뒤 가짜 사용자(`userNo: 0, name: '시험 사용자', providers: ['KAKAO' 또는 'GOOGLE']`)로 로그인, 저장소에 표시만. 서버·키 없이 화면이 끝까지 돈다. `accessToken()` 은 null.
- `lib/services/analysis_service.dart`: `HttpAnalysisService` 에 `Future<String?> Function()? accessToken` 을 받아 있으면 `Authorization: Bearer` 헤더. 401 `token_expired` 면 refresh 후 **요청을 새로 만들어** 한 번 더(멀티파트는 다시 보낼 수 없으므로 만드는 함수를 따로).
- `lib/screens/login_screen.dart`:
  - 바탕 한지 `AppColors.canvas`, 위쪽에 앱 이름 `읽어드림`(`AppText.display`, 먹색)과 한 줄 `서류를 찍으면 쉽게 읽어 드려요`(`AppText.body`, `inkSub`). 글은 이 두 줄과 버튼뿐.
  - 버튼 높이 64 (기존 `minimumSize: Size.fromHeight(64)` 와 같게), 가로 꽉 차게, 간격 `Space.s16`, 모서리 `Radii.r12`.
  - **카카오 버튼** (카카오 로그인 디자인 가이드): 바탕 `#FEE500`, 왼쪽에 카카오 말풍선 심볼(검정 `#000000`, 공식 리소스 그대로 — developers.kakao.com 의 로그인 버튼 리소스에서 받아 `app/assets/brand/` 에), 글 `카카오 로그인`(또는 `카카오로 시작하기`) 색 `#000000` 85%, 모서리 12. 심볼·색을 바꾸지 않는다.
  - **구글 버튼** (Google Identity 브랜딩 가이드, 밝은 테마): 바탕 `#FFFFFF`, 테두리 1px `#747775`, 글 `Google 계정으로 로그인` 색 `#1F1F1F`, 왼쪽에 공식 4색 "G" 로고(가이드 페이지의 공식 파일, 직접 그리지 말 것). 가이드는 글꼴로 Roboto Medium 을 권하지만 앱 전체 글꼴(IBM Plex Sans KR)을 써도 된다고 판단해 둔다 — 걱정되면 Roboto 를 추가.
  - `SHOW_TEST_LOGIN` 이면 회청(`accentSoft`) 바탕 `시험 로그인` 버튼.
  - `REQUIRE_LOGIN` 이 아니면 맨 아래 텍스트 버튼 `나중에 할게요` (홈으로).
  - 진행 중에는 버튼 대신 큰 진행 표시와 `로그인하는 중이에요`. 실패는 버튼 위 주홍(`warnBg/warnText`) 한 줄 상자에 서버 `userMessage`(없으면 `로그인하지 못했어요. 다시 해 주세요.`). 사용자가 취소하면 아무 말 없이 원래 화면.
  - 화면 읽기 프로그램용 `Semantics(label: '카카오로 로그인')` 등.
- `lib/main.dart`: `AuthService` 를 `AppConfig.useMock ? MockAuthService() : HttpAuthService(...)` 로 만들고 `KakaoSdk.init(nativeAppKey: …)`(키 있을 때만). 시작 때 저장된 토큰이 있으면 홈, 없고 처음이면 로그인 화면(나중에 를 누르면 `auth.skipped=true` 저장 후 다시 묻지 않음). `AppScope` 에 auth 를 같이 넣는다.
- 홈 머리글에 계정 버튼(Phosphor 사용자 아이콘) → 바텀시트: 이름·로그인 제공자, `로그아웃` (확인 대화상자), `회원 탈퇴` (주홍, 확인 대화상자 `탈퇴하면 기록이 모두 지워져요`). 로그인 안 했으면 `로그인하기`.
- 플랫폼 설정 (README 에도 적기):
  - Android `AndroidManifest.xml`: 카카오 `com.kakao.sdk.flutter.AuthCodeCustomTabsActivity` intent-filter `kakao{NATIVE_APP_KEY}://oauth`, `<queries>` 에 카카오톡 패키지. 키는 `manifestPlaceholders` 로 (build.gradle.kts).
  - iOS `Info.plist`: `LSApplicationQueriesSchemes` (`kakaokompassauth`, `kakaolink`), URL 스킴 `kakao{NATIVE_APP_KEY}`, 구글 `GIDClientID`, `GIDServerClientID`, 역순 클라이언트 ID URL 스킴.
- `app/test/`: `AuthTokens.fromJson`·만료 계산, `MockAuthService` 로그인/로그아웃, 갱신 한 번만(single-flight) 단위 테스트 (`http` 의 `MockClient` 사용).

---

## 9. 파일별 작업 목록

### ✅ Stage 1 (끝남)

| 파일 | 내용 |
|---|---|
| `server/db/migrations/V0001__ct_member.sql` | 6개 표 + 인덱스 + 한국어 주석 |
| `server/db/migrate.py` | V*.sql 순서대로 한 번씩 적용, `sy_schema_migration` 기록, 체크섬 경고 |
| `server/app/db.py` | 비동기 엔진(asyncpg / aiosqlite), `UTCDateTime`, `utcnow`, `get_session`, `session_scope`, SQLite 자동 생성 |
| `server/app/auth/models.py` | 표 모델 |
| `server/app/auth/config.py` | `AuthSettings` (환경변수) |
| `server/app/auth/errors.py` | `AuthError`, 오류 응답 처리기 |
| `server/app/auth/tokens.py` | access JWT 발급·검증, refresh 생성, SHA-256 |
| `server/app/auth/pkce.py` | S256, verifier/challenge 형식 |
| `server/app/auth/oidc.py` | JWKS 캐시, 구글 ID 토큰 검증 |
| `server/app/auth/providers.py` | 카카오·구글·가짜 제공자 (확인, 인가 주소, 코드 교환, 연결 끊기) |
| `server/app/auth/redirect.py` | 앱으로 돌아가는 주소 (AsOne OAuthClientRedirect) |
| `server/app/auth/service.py` | 가입·연결, 세션 발급·제한, 회전·재사용 탐지, 인증, 로그아웃, 탈퇴, 인가 코드 흐름 |
| `server/app/auth/deps.py` | `get_http`, `providers_dep`, `client_meta`, `current_auth`, `optional_auth` |
| `server/app/auth/routes.py` | 위 엔드포인트, `install(app)` |
| `server/app/main.py` | `auth_routes.install(app)`, CORS 에 DELETE |
| `server/requirements.txt` | SQLAlchemy[asyncio], aiosqlite, asyncpg, PyJWT[crypto], cryptography, greenlet |
| `server/tests/conftest.py` | 임시 DB, 가짜 카카오·구글 HTTP, 시험 RSA 키, `TEST_DATABASE_URL` 로 Postgres 실행 |
| `server/tests/test_auth_*.py` | §10 |

### ⬜ Stage 2 (할 일)

| 파일 | 내용 |
|---|---|
| `server/app/auth/routes.py` | `GET /api/me`, `POST /api/me/push-token` 추가 (§6 계약. service 함수는 새로 `service.register_push_token` 하나만) |
| `server/app/main.py` | `AUTH_REQUIRED_FOR_ANALYZE` (§6) |
| `server/tests/test_auth_me.py` | `GET /api/me`, 푸시 토큰 upsert·다른 회원 끄기, analyze 플래그 끔/켬/틀린 토큰 |
| `docker-compose.yml` (저장소 루트) | `postgres:17-alpine` (`POSTGRES_USER/PASSWORD/DB=ilgeo/ilgeo/ilgeodeurim`, 포트 5432, 볼륨, healthcheck `pg_isready`), 선택으로 `server` 서비스(`DATABASE_URL`, `JWT_SECRET`, `AUTH_FAKE_PROVIDER=1`, 시작 전 `python db/migrate.py`) |
| `server/.env.example` | §7 변수 목록 (값은 비움, 실제 키 금지) |
| `README.md` | 로그인 절(아래), 서버 환경변수 표에 §7 추가, API 계약에 인증 엔드포인트, "다음에 할 일"의 인증 항목 갱신 |
| `app/pubspec.yaml`, `app/lib/config.dart`, `app/lib/main.dart` | §8 |
| `app/lib/models/auth_session.dart`, `app/lib/services/token_store.dart`, `app/lib/services/auth_service.dart` | §8 |
| `app/lib/screens/login_screen.dart`, 홈 계정 시트 | §8 |
| `app/lib/services/analysis_service.dart` | Bearer + 401 재시도 |
| `app/android/...AndroidManifest.xml`, `build.gradle.kts`, `app/ios/Runner/Info.plist` | §8 플랫폼 설정 |
| `app/assets/brand/` | 카카오 심볼, 구글 G 로고 (공식 파일) |
| `app/test/auth_test.dart` | §8 |

### ⬜ README 한국어 출시 안내에 꼭 들어갈 것 (Stage 2)

**카카오 디벨로퍼스** (developers.kakao.com)
1. 내 애플리케이션 → 애플리케이션 추가 (앱 이름 `읽어드림`, 아이콘)
2. 앱 키: 네이티브 앱 키(→ 앱 `KAKAO_NATIVE_APP_KEY`), REST API 키(→ 서버 `KAKAO_REST_API_KEY`), 어드민 키(→ 서버 `KAKAO_ADMIN_KEY`, 절대 앱에 넣지 않음), 앱 ID(→ 서버 `KAKAO_APP_ID`)
3. 플랫폼: Android — 패키지명 `com.ilgeodeurim.ilgeodeurim`, 키 해시(디버그·릴리스·Play 앱 서명 키 각각, `keytool -exportcert -alias … | openssl sha1 -binary | openssl base64` 또는 SDK `KakaoSdk.origin`), iOS — 번들 ID (`app/ios/Runner.xcodeproj` 의 `PRODUCT_BUNDLE_IDENTIFIER`), Web — 사이트 도메인
4. 카카오 로그인 활성화 ON, Redirect URI 에 `{PUBLIC_BASE_URL}/api/auth/kakao/callback` (서버 흐름 쓸 때)
5. 동의항목: 닉네임·프로필 사진(선택 동의 권장). 이메일은 필수로 하지 않음(비즈 앱 심사 필요, 어르신 이메일 없음)
6. 보안: Client Secret 사용하면 코드 생성 후 `KAKAO_CLIENT_SECRET`
7. (선택) 연결 끊기 웹훅은 아직 안 받음

**Google Cloud Console** (console.cloud.google.com)
1. 프로젝트 만들기 → OAuth 동의 화면(앱 이름, 지원 이메일, 범위 `openid email profile`, 게시 상태 '프로덕션'으로)
2. 사용자 인증 정보 → OAuth 클라이언트 ID 3개
   - 웹 애플리케이션: 승인된 리디렉션 URI `{PUBLIC_BASE_URL}/api/auth/google/callback` → 클라이언트 ID 는 서버 `GOOGLE_WEB_CLIENT_ID` + 앱 `GOOGLE_SERVER_CLIENT_ID`, 비밀번호는 서버 `GOOGLE_CLIENT_SECRET`
   - Android: 패키지명 + SHA-1 (디버그 키스토어, 릴리스 업로드 키, **Play Console 앱 서명 키** 모두)
   - iOS: 번들 ID → 앱 `GOOGLE_IOS_CLIENT_ID`, Info.plist `GIDClientID` + 역순 ID URL 스킴
3. 서버 `GOOGLE_CLIENT_IDS` 에 세 ID 모두 쉼표로

**서버**: `JWT_SECRET`(긴 무작위), `DATABASE_URL`(Postgres), `python db/migrate.py`, `PUBLIC_BASE_URL`(https), `APP_REDIRECT_URIS`, `AUTH_FAKE_PROVIDER` 끄기, 프록시 뒤면 `TRUST_PROXY_HEADERS=1`.

---

## 10. 테스트

`cd server && .venv\Scripts\python -m pytest -q` (Windows) — 86개 통과(기존 12 + 새 74).
Postgres 로도: `TEST_DATABASE_URL=postgresql://ilgeo:ilgeo@localhost:5432/ilgeodeurim` (먼저 `db/migrate.py`) — 같은 86개 통과 확인함.

### ✅ 있는 테스트

- `test_auth_tokens.py`: access JWT 발급·클레임, 만료/다른 키/aud/iss/`alg=none`/typ≠access/쓰레기 거절, PKCE RFC 7636 부록 B 벡터, 돌아갈 주소 허용 목록·인코딩, 구글 ID 토큰 정상·캐시, aud/iss/만료/미래 iat/위조 서명(같은 kid)/azp/sub 없음/HS256 바꿔치기/형식 오류 거절, nonce, JWKS 모르는 kid 재조회 60초 제한·키 회전, JWKS 장애 시 예전 키·503, 설정 없음 503
- `test_auth_login.py`: 카카오 가입→재로그인 같은 회원, app_id 먼저 확인, DB 에 토큰 원문 없음, 로그 SIGNUP/LOGIN, 확인된 이메일 저장·userType, **다른 앱 토큰 거절**(회원 정보 조회 전), 잘못된 토큰 401·장애 502·빈 요청 400, 설정 없음 503, 구글 로그인(웹·안드로이드 aud), 남의 aud 거절, **같은 이메일이어도 제공자 다르면 합치지 않음**, 가짜 제공자 켜짐/꺼짐, 모르는 제공자 422, `app.main` 에 라우터가 붙었는지
- `test_auth_session.py`: 회전(새 쌍, 같은 sid, parent·auth_at), 유예 안 재사용은 세션 유지, **유예 밖 재사용은 세션 전체 폐기 + 아직 안 끝난 access 도 거절 + 다른 기기 세션은 유지 + 로그**, 모르는/너무 긴/만료 refresh, 세션 최대 수명, refresh 만료가 세션 최대를 안 넘음, Bearer 형식, 로그아웃(세션·access·기기 푸시 끔, 반복·모르는 토큰도 204), Bearer 만으로 로그아웃, 남의 refresh 로 남의 세션 못 끊음, 모든 기기 로그아웃, 세션 수 제한
- `test_auth_code_flow.py`: 가짜 제공자로 끝까지, state 한 번만·위조·없음·만료, redirect_uri 허용 목록(400 JSON), 앱 PKCE 필수(없음/plain/형식), 틀린 verifier 면 코드 소멸, redirectUri 불일치, **코드 재사용 시 낸 세션 폐기**, 로그인 코드 만료, 제공자 취소, state 가 제공자에 묶임, 구글 서버 흐름(인가 주소 파라미터, 토큰 요청에 client_secret·code_verifier, nonce), nonce 불일치, 카카오 서버 흐름, 카카오 코드 거절, 설정 없음이면 앱으로 오류
- `test_auth_withdraw.py`: 어드민 키로 카카오 연결 끊기(헤더·본문), 개인정보 지움·연결 소멸·세션·푸시 끔, 남은 토큰 무효, 같은 카카오로 다시 가입하면 새 회원, 사용자 토큰으로 끊기, 자격 없으면 SKIPPED, 카카오 실패에도 탈퇴 완료, 구글 SKIPPED, 로그인 필요
- `test_auth_schema.py`: SQL 마이그레이션과 모델의 표·컬럼·유니크 인덱스 일치, timestamp 는 모두 timestamptz

보안 테스트가 진짜로 잡는지 확인하려고 재사용 탐지·카카오 app_id 확인·nonce 확인·PKCE 확인·세션 폐기 확인을 하나씩 일부러 끄고 돌려 보았다 — 다섯 경우 모두 테스트가 실패했다.

### ⬜ Stage 2 가 더할 테스트

- 서버: `GET /api/me`(정상, 토큰 없음 401, 탈퇴 후 401), `POST /api/me/push-token`(새로, 같은 토큰 다시 → 한 행, 다른 회원의 같은 토큰 끔, 플랫폼 대문자), `/api/analyze`: 플래그 끔+토큰 없음 200(기존 테스트 그대로), 플래그 켬+토큰 없음 401, 켬+정상 토큰 200, 틀린 토큰 401
- 앱: §8 `app/test/auth_test.dart`

---

## 11. 남은 위험·주의

- 요청 수 제한(rate limit)이 없다. 로그인·refresh 엔드포인트에 IP·회원별 제한을 배포 때 붙일 것 (Cloud Armor, 또는 slowapi).
- `ct_user_access` 가 refresh 마다 한 행씩 늘어난다(활성 회원 하루 수십 행). 오래된 행 정리 작업이 필요하다(§2).
- 카카오 PKCE 파라미터는 실제 카카오 서버로 시험하지 못했다(키 없음). 문제가 있으면 `KAKAO_USE_PKCE=0`.
- 구글 ID 토큰 aud 는 앱이 `serverClientId` 를 웹 클라이언트 ID 로 넣었을 때 웹 ID 가 된다. Android/iOS ID 도 `GOOGLE_CLIENT_IDS` 에 함께 넣어 두면 어느 쪽이든 받는다.
- 시험용 `AUTH_FAKE_PROVIDER=1` 이 운영에서 켜지면 누구나 아무 계정으로 로그인한다. 배포 설정에서 반드시 끈다.
- Windows 에서 Postgres 비동기 드라이버는 asyncpg 를 쓴다(psycopg 비동기는 Windows 기본 이벤트 루프와 맞지 않음).
