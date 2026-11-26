# 읽다 설정 가이드

앱과 서버를 실제 환경에서 실행하기 위한 상세 설정 방법입니다.

## 목차

- [앱 설정 옵션 (dart-define)](#앱-설정-옵션-dart-define)
- [카카오 로그인 설정](#카카오-로그인-설정)
- [구글 로그인 설정](#구글-로그인-설정)
- [Firebase 푸시 알림 설정](#firebase-푸시-알림-설정)
- [Android 설정](#android-설정)
- [iOS 설정](#ios-설정)
- [출시 전 체크리스트](#출시-전-체크리스트)

---

## 앱 설정 옵션 (dart-define)

앱 실행 시 `--dart-define` 플래그로 전달하는 설정값입니다. 코드에 직접 넣지 않습니다.

```bash
flutter run \
  --dart-define=SERVER_URL=http://localhost:8000 \
  --dart-define=KAKAO_NATIVE_APP_KEY=your_native_key \
  --dart-define=GOOGLE_SERVER_CLIENT_ID=your_web_client_id.apps.googleusercontent.com
```

### 필수 및 선택 옵션

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SERVER_URL` | (없음) | 분석 서버 주소. 없으면 가짜 분석·가짜 로그인 모드 |
| `USE_MOCK` | `SERVER_URL` 없으면 `true` | `true`면 서버 주소가 있어도 가짜 분석·가짜 로그인 |
| `KAKAO_NATIVE_APP_KEY` | (없음) | 카카오 네이티브 앱 키. 있을 때만 카카오 로그인 초기화 |
| `GOOGLE_SERVER_CLIENT_ID` | (없음) | 구글 **웹** 클라이언트 ID (ID 토큰 aud로 사용) |
| `GOOGLE_IOS_CLIENT_ID` | (없음) | 구글 iOS 클라이언트 ID |
| `REQUIRE_LOGIN` | `false` | `true`면 로그인 화면에 '나중에' 버튼 없음 |
| `SHOW_TEST_LOGIN` | `false` | `true`면 '시험 로그인' 버튼 표시 (서버 `AUTH_FAKE_PROVIDER=1`과 함께) |
| `SEED_DEMO` | `false` | `true`이고 가짜 모드면 예시 서류 2건과 가족 2명 자동 생성 |

### Android 로컬 설정

카카오 스킴은 `app/android/local.properties`에 설정합니다:

```bash
cd app/android
cp local.properties.example local.properties
```

`local.properties` 파일:
```properties
# 카카오 네이티브 앱 키 (kakao+숫자 형식의 URL 스킴 생성용)
kakao.native.app.key=your_native_app_key_here

# 초대 링크 App Links 호스트 (기본: ilgeodeurim.example, 실제 도메인으로 변경)
app.link.host=yourdomain.com
```

> **주의**: `local.properties`는 `.gitignore`에 포함되어 있으므로 git에 올라가지 않습니다.

---

## 카카오 로그인 설정

[Kakao Developers](https://developers.kakao.com) 콘솔에서 설정합니다.

### 1. 애플리케이션 만들기

1. **내 애플리케이션** → **애플리케이션 추가하기**
2. 앱 이름: `읽다`
3. 앱 아이콘 업로드

### 2. 앱 키 확인 및 설정

**요약 탭**에서 각 키를 확인하고 아래와 같이 설정합니다:

| 키 종류 | 용도 | 설정 위치 |
|---------|------|-----------|
| **네이티브 앱 키** | 앱에서 카카오 SDK 초기화 | 앱 `KAKAO_NATIVE_APP_KEY`, Android `local.properties` |
| **REST API 키** | 서버 인가 코드 흐름 | 서버 `KAKAO_REST_API_KEY` |
| **Admin 키** | 탈퇴 시 연결 끊기 (절대 앱에 넣지 말 것) | 서버 `KAKAO_ADMIN_KEY` |
| **앱 ID** (숫자) | 다른 카카오 앱 토큰 거부용 | 서버 `KAKAO_APP_ID` |

### 3. 플랫폼 설정

**플랫폼 탭**:

- **Android**
  - 패키지명: `com.ilgeodeurim.ilgeodeurim`
  - 키 해시 3개 등록:
    - 디버그 키스토어
    - 릴리스 업로드 키
    - Play Console 앱 서명 키
  - 키 해시 생성 명령:
    ```bash
    keytool -exportcert -alias androiddebugkey -keystore ~/.android/debug.keystore \
      | openssl sha1 -binary | openssl base64
    ```
  - 또는 앱에서 `KakaoSdk.origin`으로 확인 가능

- **iOS**
  - 번들 ID: `com.ilgeodeurim.ilgeodeurim` (Xcode Runner 프로젝트의 `PRODUCT_BUNDLE_IDENTIFIER`)

- **Web** (서버 인가 코드 흐름 사용 시)
  - 사이트 도메인 등록

### 4. 카카오 로그인 활성화

**제품 설정 > 카카오 로그인**:

1. **활성화 설정 상태**: ON
2. **Redirect URI** (서버 흐름 사용 시):
   - `{PUBLIC_BASE_URL}/api/auth/kakao/callback`
   - 예: `https://api.example.com/api/auth/kakao/callback`

### 5. 동의항목 설정

**제품 설정 > 카카오 로그인 > 동의항목**:

- **닉네임**: 선택 동의 (권장)
- **프로필 사진**: 선택 동의 (권장)
- **이메일**: 필수로 하지 않음 (어르신은 이메일이 없는 경우가 많고, 필수 동의는 비즈 앱 심사 필요)

### 6. 보안 설정 (선택)

**제품 설정 > 카카오 로그인 > 보안**:

- **Client Secret**: 활성화하면 서버 `KAKAO_CLIENT_SECRET`에 설정
- **Code 발급 방식**: PKCE 사용 (기본)
  - 콘솔에서 거부되면 서버 `KAKAO_USE_PKCE=0`

---

## 구글 로그인 설정

[Google Cloud Console](https://console.cloud.google.com)에서 설정합니다.

### 1. 프로젝트 만들기

1. **프로젝트 선택** → **새 프로젝트**
2. 프로젝트 이름 입력

### 2. OAuth 동의 화면 설정

**API 및 서비스 > OAuth 동의 화면**:

1. **User Type**: 외부
2. 앱 이름: `읽다`
3. 사용자 지원 이메일
4. 범위: `openid`, `email`, `profile`
5. **게시 상태**: 프로덕션으로 변경

### 3. OAuth 클라이언트 ID 만들기

총 3개의 클라이언트 ID를 만들어야 합니다.

#### (1) 웹 애플리케이션 클라이언트

**API 및 서비스 > 사용자 인증 정보 > 사용자 인증 정보 만들기 > OAuth 클라이언트 ID**:

- 애플리케이션 유형: **웹 애플리케이션**
- 승인된 리디렉션 URI: `{PUBLIC_BASE_URL}/api/auth/google/callback`
  - 예: `https://api.example.com/api/auth/google/callback`

생성 후:
- **클라이언트 ID** → 서버 `GOOGLE_WEB_CLIENT_ID`, 앱 `GOOGLE_SERVER_CLIENT_ID`
- **클라이언트 보안 비밀** → 서버 `GOOGLE_CLIENT_SECRET` (절대 앱에 넣지 말 것)

#### (2) Android 클라이언트

- 애플리케이션 유형: **Android**
- 패키지명: `com.ilgeodeurim.ilgeodeurim`
- SHA-1 지문 3개:
  - 디버그 키스토어
  - 릴리스 업로드 키
  - **Play Console 앱 서명 키** (중요!)

SHA-1 생성:
```bash
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey
```

#### (3) iOS 클라이언트

- 애플리케이션 유형: **iOS**
- 번들 ID: `com.ilgeodeurim.ilgeodeurim`

생성 후:
- **클라이언트 ID** → 앱 `GOOGLE_IOS_CLIENT_ID`, iOS `Info.plist`의 `GIDClientID`
- **역순 클라이언트 ID** (URL 스킴):
  - `123456-abc.apps.googleusercontent.com` → `com.googleusercontent.apps.123456-abc`
  - `Info.plist`의 `REVERSED_IOS_CLIENT_ID`로 설정

### 4. 서버 설정

서버 `.env` 파일:
```bash
# 웹, Android, iOS 클라이언트 ID를 모두 쉼표로
GOOGLE_CLIENT_IDS=web_client_id.apps.googleusercontent.com,android_client_id.apps.googleusercontent.com,ios_client_id.apps.googleusercontent.com

# 웹 클라이언트 ID (서버 흐름 및 앱 serverClientId)
GOOGLE_WEB_CLIENT_ID=web_client_id.apps.googleusercontent.com

# 웹 클라이언트 보안 비밀
GOOGLE_CLIENT_SECRET=your_web_client_secret
```

---

## Firebase 푸시 알림 설정

Firebase Cloud Messaging (FCM)을 사용하여 푸시 알림을 보냅니다.

### 1. Firebase 프로젝트 만들기

1. [Firebase Console](https://console.firebase.google.com) 접속
2. **프로젝트 추가** (기존 Google Cloud 프로젝트 재사용 가능)
3. 프로젝트 이름 입력

### 2. 앱 등록

#### Android 앱 추가

1. **프로젝트 설정** → **내 앱**에서 **Android 앱 추가**
2. 패키지명: `com.ilgeodeurim.ilgeodeurim`
3. `google-services.json` 다운로드
4. 파일을 `app/android/app/` 에 저장
5. **이 파일은 `.gitignore`에 포함되어 git에 올라가지 않습니다**

#### iOS 앱 추가

1. **iOS 앱 추가**
2. 번들 ID: `com.ilgeodeurim.ilgeodeurim`
3. `GoogleService-Info.plist` 다운로드
4. Xcode에서 Runner 타겟에 추가 (파일 복사, 타겟 체크)
5. **이 파일도 `.gitignore`에 포함됩니다**

### 3. iOS APNs 인증 키 설정

1. [Apple Developer](https://developer.apple.com) → **Certificates, Identifiers & Profiles** → **Keys**
2. **새 키 만들기** (APNs 체크)
3. `.p8` 파일 다운로드 및 Key ID 기록
4. Firebase Console → **프로젝트 설정** → **Cloud Messaging**
5. **APNs 인증 키** 업로드 (Key ID, Team ID 함께 입력)

### 4. 서버 서비스 계정 설정

1. Firebase Console → **프로젝트 설정** → **서비스 계정**
2. **새 비공개 키 생성** 클릭
3. JSON 파일 다운로드
4. 파일을 서버 외부 안전한 위치에 저장 (예: `C:\secrets\`, `/etc/secrets/`)
5. 서버 `.env`:
   ```bash
   FCM_SERVICE_ACCOUNT_FILE=/path/to/ilgeodeurim-firebase-adminsdk.json
   # 또는 Cloud Run 등에서는 JSON 원문이나 base64로:
   # FCM_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
   ```

> **주의**: 서비스 계정 JSON 파일은 절대 git에 올리지 않습니다.

---

## Android 설정

### 필수 권한 (`AndroidManifest.xml`)

앱에 이미 포함되어 있습니다:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
```

### 카카오 로그인 Activity

`AndroidManifest.xml`에 이미 설정되어 있습니다:

```xml
<activity
    android:name="com.kakao.sdk.flutter.auth.AuthCodeHandlerActivity"
    android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data
            android:host="oauth"
            android:scheme="kakao${kakaoNativeAppKey}" />
    </intent-filter>
</activity>

<queries>
    <package android:name="com.kakao.talk" />
</queries>
```

### FCM 설정

`google-services.json`이 `app/android/app/`에 있으면 `build.gradle`이 자동으로 플러그인을 적용합니다.

알림 채널은 앱 코드에서 `family` 채널(이름: "가족 알림")로 생성됩니다.

### 최소 SDK 버전

```gradle
minSdk 24
```

### cleartext 트래픽 허용 (개발용)

실제 폰에서 http:// 주소를 쓰려면 `AndroidManifest.xml`:

```xml
<application
    android:usesCleartextTraffic="true">
```

**배포 시 반드시 제거하고 https만 사용하세요.**

---

## iOS 설정

### 카카오 로그인 URL 스킴

`Info.plist`에 이미 설정되어 있습니다:

```xml
<key>LSApplicationQueriesSchemes</key>
<array>
    <string>kakaokompassauth</string>
    <string>kakaolink</string>
</array>

<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>kakao${KAKAO_NATIVE_APP_KEY}</string>
        </array>
    </dict>
</array>
```

### 구글 로그인 설정

`Info.plist`:

```xml
<key>GIDClientID</key>
<string>your_ios_client_id.apps.googleusercontent.com</string>

<key>GIDServerClientID</key>
<string>your_web_client_id.apps.googleusercontent.com</string>

<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>com.googleusercontent.apps.your-reverse-client-id</string>
        </array>
    </dict>
</array>
```

### 카메라 및 사진 권한

`Info.plist`에 이미 설정되어 있습니다:

```xml
<key>NSCameraUsageDescription</key>
<string>서류를 촬영하려면 카메라 권한이 필요합니다.</string>

<key>NSPhotoLibraryUsageDescription</key>
<string>사진을 선택하려면 사진 라이브러리 권한이 필요합니다.</string>
```

### 푸시 알림 설정

Xcode Runner 타겟 → **Signing & Capabilities**:

1. **Push Notifications** capability 추가
2. **Background Modes** capability 추가 → **Remote notifications** 체크

`AppDelegate.swift`에 알림 delegate가 이미 구현되어 있습니다.

### ATS 예외 (개발용)

http:// 주소를 쓰려면 `Info.plist`:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

**배포 시 반드시 제거하고 https만 사용하세요.**

---

## 출시 전 체크리스트

### 보안

- [ ] 실제 키는 모두 환경변수나 `.env` 파일로만 설정 (코드에 포함 금지)
- [ ] `server/.env`는 `.gitignore`에 포함됨 확인
- [ ] `google-services.json`, `GoogleService-Info.plist`는 `.gitignore`에 포함됨 확인
- [ ] FCM 서비스 계정 JSON은 git 저장소 외부에 보관
- [ ] 서버 `AUTH_FAKE_PROVIDER=0` (가짜 로그인 끄기)
- [ ] 서버 `JWT_SECRET`을 32바이트 이상 무작위 값으로 설정

### 서버

- [ ] `PUBLIC_BASE_URL`을 https 주소로 변경
- [ ] `DATABASE_URL`을 프로덕션 Postgres로 설정
- [ ] `python db/migrate.py`로 마이그레이션 적용
- [ ] `CORS_ORIGINS`를 실제 앱 주소로 좁히기
- [ ] `DEBUG_USAGE=0` (디버그 정보 끄기)
- [ ] 프록시 뒤에서는 `TRUST_PROXY_HEADERS=1`

### 앱

- [ ] Android cleartext 트래픽 허용 제거
- [ ] iOS ATS 예외 제거
- [ ] `--dart-define=SERVER_URL`을 프로덕션 주소로
- [ ] 릴리스 빌드 키 해시를 카카오·구글 콘솔에 등록
- [ ] Play Console 앱 서명 키 SHA-1/SHA-256도 등록

### 테스트

- [ ] 실제 기기에서 카카오 로그인 동작 확인
- [ ] 실제 기기에서 구글 로그인 동작 확인
- [ ] Android 13+ 기기에서 알림 권한 요청 및 수신 확인
- [ ] iOS에서 푸시 알림 수신 확인
- [ ] 문서 스캐너 동작 확인
- [ ] 가족 연결 흐름 완전히 테스트

### 모니터링

- [ ] AI 사용량 및 비용 모니터링 설정
- [ ] 서버 로그 및 에러 추적 설정
- [ ] FCM 전송 성공률 모니터링
