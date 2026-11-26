# 읽다

서류(고지서·약봉투·병원 안내문·계약서·관공서 서류)를 찍으면 쉬운 말로 정리하고, 할 일과 기한을 알려 주는 어르신용 앱.

```
ilda/
├── app/          Flutter 앱 (Android · iOS · Web)
├── server/       분석 서버 (Python FastAPI)
├── docs/         인증·기능 계획 문서
├── screenshots/  웹 빌드 + 가짜 AI 서버로 끝까지 돌려 본 화면
└── shots/        추가 화면 기록
```

## 설정 (API 키는 저장소에 넣지 마세요)

서버 비밀 값은 `server/.env.example`을 복사해 `server/.env`에만 채웁니다. `.env`는 git에 올리지 않습니다.

```bash
cd server
cp .env.example .env   # Windows: copy .env.example .env
# GEMINI_API_KEY, JWT_SECRET 등 필요한 값만 채우세요.
```

앱 쪽 키는 코드에 넣지 않고 `--dart-define`으로 넘깁니다. Android 카카오 스킴은 `app/android/local.properties.example`을 `local.properties`로 복사해 채웁니다.

```bash
cd app
flutter run --dart-define=SERVER_URL=http://localhost:8000 \
  --dart-define=KAKAO_NATIVE_APP_KEY=카카오_네이티브_앱키 \
  --dart-define=GOOGLE_SERVER_CLIENT_ID=구글_웹_클라이언트_ID
```

변수 목록은 아래 표를 보세요.

## 빠르게 실행하기

### 1) 서버

```bash
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# API 키 없이 (가짜 AI — 앱↔서버 흐름 시험용)
AI_PROVIDER=fake uvicorn app.main:app --host 0.0.0.0 --port 8000

# Postgres (저장소 루트). 표는 마이그레이션으로 만든다.
# docker compose up -d
# DATABASE_URL=postgresql://ilgeo:ilgeo@localhost:5432/ilgeodeurim python db/migrate.py

# 실제 AI (Gemini 추천: 싸고 빠름)
GEMINI_API_KEY=... uvicorn app.main:app --host 0.0.0.0 --port 8000

# 테스트
python -m pytest -q
```

확인: `curl localhost:8000/health` → `{"ok":true,"provider":"fake"}`

### 2) 앱

```bash
cd app
flutter pub get

# 서버 없이 화면만 (가짜 분석, 기본값)
flutter run

# 서버에 붙이기
flutter run --dart-define=SERVER_URL=http://10.0.2.2:8000      # Android 에뮬레이터 → 내 PC
flutter run --dart-define=SERVER_URL=http://192.168.0.10:8000   # 실제 폰 → 같은 와이파이의 PC
flutter run -d chrome --dart-define=SERVER_URL=http://localhost:8000

flutter analyze && flutter test
```

| dart-define | 기본값 | 설명 |
|---|---|---|
| `SERVER_URL` | (없음) | 분석 서버 주소. 없으면 가짜 분석·가짜 로그인 |
| `USE_MOCK` | SERVER_URL 이 없으면 `true` | `true`면 서버가 있어도 가짜 분석·가짜 로그인 |
| `KAKAO_NATIVE_APP_KEY` | (없음) | 카카오 네이티브 앱 키. 있을 때만 `KakaoSdk.init` |
| `GOOGLE_SERVER_CLIENT_ID` | (없음) | 구글 **웹** 클라이언트 ID (`serverClientId`, ID 토큰 aud) |
| `GOOGLE_IOS_CLIENT_ID` | (없음) | 구글 iOS 클라이언트 ID |
| `REQUIRE_LOGIN` | `false` | `true`면 로그인 화면에 '나중에' 없음 |
| `SHOW_TEST_LOGIN` | `false` | `true`면 '시험 로그인'. 서버 `AUTH_FAKE_PROVIDER=1` 과 함께 |
| `SEED_DEMO` | `false` | `true`이고 가짜 모드면 예시 서류 2건과 가족 2명을 채운다 |

Linux에서 `flutter test`를 빌드할 때 `pdfrx`(PDFium) 플러그인이 Clang을 요구할 수 있다. PDF를 JPEG로 그리는 코드는 `app/lib/services/pdf_raster_io.dart`에만 있고, `pdf_raster.dart`가 io일 때만 그 파일을 내보낸다. 웹과 `pdf_raster_stub.dart`는 `pdfrx`를 임포트하지 않는다. 앱 테스트(`app/test`)는 그 파일을 임포트하지 않지만, 플러그인 등록 때문에 리눅스 테스트 바이너리를 만들 때는 Clang이 필요하다.

```bash
sudo apt install clang cmake ninja-build libgtk-3-dev libclang-dev
```

이 PC에는 Flutter가 없어서 `flutter analyze` / `flutter test` 는 돌리지 못했다. Dart는 패키지 README(kakao_flutter_sdk_user 2.1, google_sign_in 7.2)에 맞춰 작성했다.

> 실제 폰에서 `http://` 주소를 쓰려면 Android는 cleartext 허용, iOS는 ATS 예외가 필요해요. 배포 때는 https 로 바꾸세요.

## 서버 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `AI_PROVIDER` | 자동 | `fake` / `gemini` / `anthropic`. 비우면 키 있는 쪽 → 없으면 fake |
| `GEMINI_API_KEY` | — | Google AI Studio 키 |
| `GEMINI_CLASSIFY_MODEL` | `gemini-3.5-flash-lite` | 종류 분류 (제일 쌈) |
| `GEMINI_DEFAULT_MODEL` | `gemini-3.6-flash` | 보통 서류 (3.8-flash 는 11/16 실측 때 무응답이라 3.6 으로) |
| `GEMINI_STRONG_MODEL` | `gemini-3.1-pro-preview` | 약·계약서 (유료 등급 키 필요) |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.6-flash,gemini-3.5-flash-lite` | 앞 모델이 429/403/404/5xx/시간 초과면 차례로 |
| `GEMINI_THINKING_LEVEL` | `low` | Gemini 3 생각 수준 (minimal/low/medium/high) |
| `GEMINI_TIMEOUT_S` | `45` | 모델 호출 한 번 제한 시간 |
| `ANTHROPIC_API_KEY` | — | Claude 키 (정확도 우선일 때) |
| `ANTHROPIC_CLASSIFY_MODEL` / `_DEFAULT_MODEL` | `claude-haiku-5-5` | |
| `ANTHROPIC_STRONG_MODEL` | `claude-sonnet-5-5` | 약·계약서 |
| `ESCALATE_TYPES` | `medicine,contract` | 좋은 모델로 올릴 서류 종류 |
| `MAX_IMAGES` / `MAX_IMAGE_MB` | `5` / `10` | 업로드 제한 |
| `CORS_ORIGINS` | `*` | 웹 앱 주소 (배포 땐 좁히기) |
| `DEBUG_USAGE` | (끔) | `1`이면 응답에 `debug`(분류 결과, 걸린 시간, 모델별 토큰 수) 추가. 운영에선 끄기 |
| `ANTHROPIC_FALLBACK_MODELS` | (없음) | Claude 대체 모델 목록 |
| `DATABASE_URL` | (없으면 SQLite 파일) | `postgresql://user:pw@host:5432/db` 도 받는다 (asyncpg) |
| `DB_AUTO_CREATE` | 끔 | `1`이면 Postgres에서도 모델로 표 생성. 평소엔 `python db/migrate.py` |
| `JWT_SECRET` | (없으면 임시 키 + 경고) | **운영 필수.** 32바이트 이상 |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `ilgeodeurim` / `ilgeodeurim-app` | access JWT |
| `ACCESS_TOKEN_TTL_MIN` | `15` | |
| `REFRESH_TOKEN_TTL_DAYS` | `60` | 쓸 때마다 다시 60일 |
| `SESSION_MAX_DAYS` | `365` | 이 기간이 지나면 다시 로그인 |
| `REFRESH_REUSE_GRACE_S` | `30` | 이 안의 재사용은 세션을 유지(토큰은 안 줌) |
| `MAX_SESSIONS_PER_USER` | `5` | `0`이면 제한 없음 |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | 콜백 주소의 앞부분. 운영은 https |
| `APP_REDIRECT_URIS` | `ilgeodeurim://oauth/callback` | 쉼표 목록, 정확히 일치 |
| `KAKAO_APP_ID` | — | 카카오 앱 ID(숫자). 모바일 카카오 로그인에 필수 |
| `KAKAO_REST_API_KEY` | — | 서버 인가 코드 흐름 |
| `KAKAO_CLIENT_SECRET` | — | 콘솔에서 Client Secret을 켰으면 |
| `KAKAO_ADMIN_KEY` | — | 탈퇴 때 연결 끊기. **앱에 넣지 말 것** |
| `KAKAO_USE_PKCE` | `1` | 카카오가 PKCE를 거부하면 `0` |
| `GOOGLE_CLIENT_IDS` | — | 웹·Android·iOS 클라이언트 ID, 쉼표 |
| `GOOGLE_WEB_CLIENT_ID` | (`GOOGLE_CLIENT_IDS` 첫 번째) | 서버 흐름·앱 `serverClientId` |
| `GOOGLE_CLIENT_SECRET` | — | 웹 클라이언트 비밀번호. 서버만 |
| `AUTH_FAKE_PROVIDER` | 끔 | `1`이면 가짜 로그인. **운영에서 끄기** |
| `AUTH_REQUIRED_FOR_ANALYZE` | 끔 | `1`이면 `POST /api/analyze`에 로그인 필요 |
| `TRUST_PROXY_HEADERS` | 끔 | `1`이면 `X-Forwarded-For`를 IP로. 프록시 뒤에서만 |
| `QUALITY_CHECK` | `1` | `0`이면 서버 사진 품질 검사 끔 |
| `QUALITY_BLUR_MIN` / `QUALITY_DARK_MEAN` | `30` / `40` | 흐림(라플라시안 분산)·어두움(평균 밝기) 기준. 정말 못 읽는 사진만 막는 값 |
| `QUALITY_MIN_SHORT_SIDE` / `_LONG_SIDE` | `400` / `600` | 사진이 이보다 작으면 다시 찍기 |
| `FAMILY_INVITE_TTL_MIN` | `30` | 초대 번호 유효 시간(분) |
| `FAMILY_FAIL_LIMIT` / `_IP` | `10` / `30` | 15분 동안 번호 틀림 허용 수(사람별/IP별). 넘으면 429 |
| `FAMILY_MAX_CHILDREN` / `_SENIORS` | `10` / `4` | 한 사람이 가질 수 있는 연결 수 |
| `FAMILY_SEND_DAILY_LIMIT` | `30` | 자녀 한 명이 어르신 한 분에게 하루에 대신 보낼 수 있는 수 |
| `PUSH_PROVIDER` | 자동 | `fcm` / `fake` / `none`. 비우면 서비스 계정이 있으면 fcm, 없으면 보내지 않고 기록만 |
| `FCM_SERVICE_ACCOUNT_FILE` | — | Firebase 서비스 계정 JSON 파일 경로 (`GOOGLE_APPLICATION_CREDENTIALS` 도 받음). **깃에 올리지 말 것** |
| `FCM_SERVICE_ACCOUNT_JSON` | — | 파일 대신 JSON 원문 또는 base64 (Cloud Run 시크릿) |
| `FCM_PROJECT_ID` | (서비스 계정의 값) | |

빈 예시는 `server/.env.example`. 모델 이름은 2026년 11월 기준 공식 문서 이름이에요. 바뀌면 환경변수로만 바꾸면 돼요.

## API 계약

`POST /api/analyze` — multipart, 필드 이름 `images` (여러 장이면 같은 이름으로 여러 번)

```json
{
  "id": "doc_ab12...",
  "docType": "bill",          // bill | medicine | hospital | contract | government | other
  "title": "한국전력 전기요금 고지서",
  "oneLiner": "이번 달 전기요금 32,400원을 11월 25일까지 내시면 돼요.",
  "amount": 32400,            // 원 단위 정수, 없으면 null
  "dueDate": "2026-11-25",    // 대표 기한, 없으면 null
  "todos": [{"id": "t_..", "title": "전기요금 내기", "dueDate": "2026-11-25", "detail": "은행, 편의점..."}],
  "warnings": ["기한이 지나면 연체료가 붙어요."],
  "details": ["청구 금액: 32,400원", "사용량: 285kWh"],
  "model": "gemini:gemini-3.8-flash"
}
```

실패: `{"error": {"code": "unreadable", "userMessage": "글씨가 잘 안 보여요. ..."}}` — 앱은 `userMessage` 를 그대로 보여 줘요.
(400 사진 없음/너무 많음, 413 너무 큼, 415 사진 아님, 422 글씨 안 보임, 502 AI 실패)

사진 품질이 나쁘면 AI 를 부르기 **전에** 422 로 돌려준다: `code` 가 `photo_blurry` / `photo_dark` / `photo_bright` / `photo_blank` / `photo_small`, 그리고 `"page": 2, "problems": [...]` (몇 번째 사진인지).

`save=true`(폼 필드)이고 로그인했으면 결과를 내 서류로 보관하고 `"saved": true` 와 서류 필드(`source`, `seen` …)를 더해 준다. 사진은 보관하지 않는다.

`AUTH_REQUIRED_FOR_ANALYZE=1` 이면 토큰 없이 401 `login_required`. 토큰이 있는데 틀리면 플래그와 상관없이 401.

가족·서류 (자세한 계약은 `docs/phase3-plan.md`, 전부 Bearer):

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| POST | `/api/family/invites` | 초대 만들기 → 6자리 번호(30분, 한 번만) + 앱 링크 + https 링크 |
| POST | `/api/family/invites/preview` · `/accept` | 번호나 링크 토큰으로 누가 보냈는지 보기 · 한 번 눌러 수락 |
| DELETE | `/api/family/invites/{id}` | 초대 취소 |
| GET | `/api/family` | 내 가족 목록, 기다리는 초대 |
| PATCH · DELETE | `/api/family/links/{id}` | 부르는 이름·관계 바꾸기 · 연결 끊기(어느 쪽이든, 양쪽 매핑을 소프트 삭제) |
| PATCH | `/api/family/links/{id}/permissions` | 대표가 보기·대신 보내기·지우기·알림을 켠다 |
| POST | `/api/family/links/{id}/analyze` | 자녀가 어르신 대신 찍어 보내기 → 어르신 서류로 보관 + 푸시 |
| GET | `/api/family/documents` | 자녀 화면: 보냈거나 나눠 받은 서류 |
| GET · POST | `/api/documents` | 내 서류 (`?since=` 동기화, 지운 것은 `deleted`) · 기기 저장본 올리기 |
| GET · DELETE | `/api/documents/{id}` | 한 건 보기(주인·볼 수 있는 가족) · 지우기(주인·보낸 사람·can_delete_yn) |
| PATCH | `/api/documents/{id}/todos/{todoId}` | 할 일 다 함·알림 (주인 또는 can_edit_yn) |
| POST | `/api/documents/{id}/seen` | 열어 봄 (주인) |
| POST · DELETE | `/api/documents/{id}/shares[/{linkId}]` | 자녀에게 보내기 · 거두기 |
| GET | `/f/{token}` | 카톡·문자로 받은 초대 링크 → '앱에서 열기' 페이지 |
| GET | `/.well-known/assetlinks.json` · `/.well-known/apple-app-site-association` | 앱 링크 확인. SHA-256·팀 ID 가 없으면 빈 목록 |

로그인 (자세한 계약은 `docs/auth-plan.md`):

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| POST | `/api/auth/{kakao\|google\|fake}` | SDK 토큰 → 우리 access(15분) + refresh(60일) |
| GET | `/api/auth/{provider}/authorize` · `/callback` | 인가 코드 + PKCE + state → 앱 딥링크에 1회용 코드 |
| POST | `/api/auth/token` | 1회용 코드 + code_verifier → 우리 토큰 |
| POST | `/api/auth/refresh` | 회전. 재사용이면 그 세션 전체 폐기 |
| POST | `/api/auth/logout` | 204. 세션 폐기 |
| GET | `/api/me` | 내 정보 (Bearer) |
| POST | `/api/me/push-token` | 푸시 토큰 등록·갱신 (Bearer, 204) |
| DELETE | `/api/me` | 탈퇴. 카카오 연결 끊기 시도 후 개인정보 삭제 |

## 지금까지 된 것

**앱**
- 이름 `읽다` (홈 머리글, 앱 제목, Android 라벨, iOS 표시 이름, 웹 제목/manifest). 패키지·번들 ID 는 아직 `com.ilgeodeurim.ilgeodeurim`. 스토어에 올리기 전에 바꿀 수 있다
- 디자인: 먹색 `#1F1D1A` + 종이 `#FFFDF8` + 형광 노랑 `#F2C230` (아이콘과 맞춤). 노랑은 밑줄·촬영 버튼·고른 칸에만 쓴다
- 사진 받기: 모바일은 문서 스캐너(cunning_document_scanner 3.x, 최대 5장), 웹은 사진 파일 고르기(image_picker)
- `HttpAnalysisService`: 사진을 multipart 로 서버에 올리고 JSON 을 받아 화면에 표시. 금액·기한은 서버가 준 `amount`/`dueDate` 를 그대로 씀(글에서 숫자 긁어내기 없앰)
- 저장: 서류와 할 일(완료·알림 여부 포함)을 기기에 저장 → 껐다 켜도 유지 (shared_preferences, 웹은 localStorage). 사진은 저장하지 않음
- 알림: 기한 **하루 전 아침 9시**, **당일 아침 9시** (한국 시간). 분석 직후 자동 예약, '하루 전 알림' 버튼으로 끄고 켬, '다 했어요'·서류 지우기 때 취소. 권한은 처음 알림을 맞출 때 요청(Android 13+, iOS). 웹은 알림 없음
- 지난 서류에서 열면 '지우기' 버튼 (할 일·알림 함께 삭제)
- 로그인: 카카오·구글 버튼(공식 심볼·G 로고), 안전한 토큰 저장, 만료 전 자동 갱신, 로그아웃·탈퇴. `USE_MOCK` 이면 키 없이 가짜 로그인. Flutter가 이 PC에 없어 `flutter analyze`는 아직 못 돌림
- Android: minSdk 24, desugaring, 알림 수신기·재부팅 복원, 카카오 로그인 액티비티·카카오톡 쿼리, 권한(INTERNET, CAMERA, POST_NOTIFICATIONS, RECEIVE_BOOT_COMPLETED)
- iOS: NSCameraUsageDescription, NSPhotoLibraryUsageDescription, 알림 delegate

**서버**
- FastAPI `POST /api/analyze`, `GET /health`
- 공급자 교체: fake / Gemini / Anthropic (환경변수)
- 모델 라우팅: 싼 모델로 종류 분류 → 약·계약서는 좋은 모델, 나머지는 기본 모델
- 구조화 출력: Gemini `responseJsonSchema`, Claude 강제 도구 호출(+지시문 캐싱)
- 결과 검증·정리(pydantic): 날짜 형식, 금액 "32,400원" → 32400, 모르는 종류 → other
- 개인정보: 사진은 요청 동안 메모리에만, 디스크·로그에 안 남김. 파일 내용(매직 바이트)으로 사진인지 확인
- 사진 품질 검사(Pillow): 흐림·어두움·과노출·빈 사진·너무 작음을 AI 호출 전에 막고 몇 번째 사진인지 알려 줌. 압축 폭탄 거부
- 가족 연결(3단계 A): 6자리 초대 번호(HMAC 저장, 30분, 한 번만, 틀림 횟수 제한) + 링크, 한 번 눌러 수락, 어느 쪽이든 끊기, 감사 기록(`ct_family_log`)
- 서버 서류 보관(`ct_document` …, 결과 글만): 동기화(`since`, 지운 표시), 주인/연결된 자녀 권한, 자녀가 대신 보내기, 어르신이 자녀에게 나누기
- 푸시: FCM HTTP v1(서비스 계정 키는 환경변수 경로로), 가짜 발송기, 발송 기록(`ct_push_log`), 죽은 토큰 끄기. 잠금 화면에 제목·금액은 안 보임

## 실제 AI 시험 (2026-11-16, Gemini)

`server/samples/*.jpg` — 가짜 정보로 만든 고지서·약봉투·검사 안내문·통신 계약서·건강검진 안내.
`server/samples/results/*.json` — 실제 Gemini 응답 (`_v2` 는 지시문 고친 뒤).

다시 돌리기:
```bash
AI_PROVIDER=gemini DEBUG_USAGE=1 uvicorn app.main:app --port 8001
curl -F "images=@samples/bill.jpg;type=image/jpeg" localhost:8001/api/analyze
```

- 한 건에 5~10초, 토큰은 분류 약 1,100+10, 분석 약 1,600~1,900 입력 + 300~500 출력(생각 포함)
- 예상 원가(유료 등급, 1달러=1,450원): 보통 서류 약 4원 (2027년 정가부터 약 8원), 약·계약서를 Pro 로 보내면 약 15원
- **주의: 지금 키는 무료 등급** — Pro 는 쓸 수 없고(한도 0, 자동으로 Flash 로 대체), 무료 등급 데이터는 Google 이 서비스 개선에 쓸 수 있어 실제 어르신 서류에는 반드시 유료 등급 키를 쓸 것

## 다음에 할 일

1. **실제 키로 정확도 확인** — 실제 고지서·약봉투 사진 20~30장으로 Gemini/Claude 비교, 지시문 다듬기
2. **3단계 B** — 앱 코드는 들어갔다. 기기에서 스캐너·공유·푸시를 확인하는 일이 남았다. 설정은 아래 「3단계 B 켜기」
3. **인증 나머지** — 로그인·refresh 요청 수 제한(rate limit), 오래된 세션 행 정리. 카카오·구글 로그인 자체는 아래 출시 안내대로 키만 넣으면 된다
4. **배포** — 서버를 Cloud Run 등에 https 로, `SERVER_URL` 운영 주소, CORS 좁히기, 비용 모니터링
5. 실제 기기에서 스캐너·알림 확인 (Android 13+/iOS 권한 흐름), 앱 아이콘
6. 기기 시간대 따라가기(지금은 Asia/Seoul 고정)

## 푸시 켜기 (Firebase)

지금은 실제 키가 없어 푸시는 꺼져 있다(`PUSH_PROVIDER` 비움 → 보내지 않고 `ct_push_log` 에 `DISABLED` 로만 남김). 시험은 가짜 발송기로 돈다. 켜는 순서는 `docs/phase3-plan.md` §5:
Firebase 프로젝트 → Android·iOS 앱 등록(`google-services.json`, `GoogleService-Info.plist`, 둘 다 깃에 올리지 않음) → iOS 는 APNs 인증 키(.p8)를 Firebase 에 올림 → 서비스 계정 키 JSON 을 서버 밖 안전한 곳에 두고 `FCM_SERVICE_ACCOUNT_FILE` 로 경로만 넣는다.

## 로그인 출시 전에 할 일

키는 코드에 넣지 않는다. 서버는 `server/.env` (예시 `server/.env.example`), 앱은 `--dart-define`. 어드민 키·REST API 키·클라이언트 시크릿은 앱에 넣지 않는다. `AUTH_FAKE_PROVIDER` 는 운영에서 끈다. `JWT_SECRET` 은 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 로 만들고, Postgres에 `python db/migrate.py` 를 적용한 뒤 `PUBLIC_BASE_URL` 을 https 로 둔다. 프록시 뒤면 `TRUST_PROXY_HEADERS=1`.

Flutter가 이 PC에 없어 앱 코드는 `flutter analyze`로 확인하지 못했다.

### 카카오 디벨로퍼스 (developers.kakao.com)

1. 내 애플리케이션 → 애플리케이션 추가. 앱 이름 `읽다`, 아이콘.
2. 앱 키를 환경에 넣는다.
   - 네이티브 앱 키 → 앱 `KAKAO_NATIVE_APP_KEY`, Android `android/local.properties` 의 `kakao.native.app.key`, iOS URL 스킴 `kakao` + 키 (Info.plist 의 `kakaoNATIVE_APP_KEY` 를 치환)
   - REST API 키 → 서버 `KAKAO_REST_API_KEY`
   - 어드민 키 → 서버 `KAKAO_ADMIN_KEY` (탈퇴 시 연결 끊기. 절대 앱에 넣지 않음)
   - 앱 ID(숫자) → 서버 `KAKAO_APP_ID` (다른 카카오 앱 토큰을 거절하는 데 필요)
3. 플랫폼
   - Android: 패키지명 `com.ilgeodeurim.ilgeodeurim`. 키 해시 세 개(디버그, 릴리스, Play 앱 서명). `keytool -exportcert -alias … | openssl sha1 -binary | openssl base64` 또는 앱에서 `KakaoSdk.origin`
   - iOS: 번들 ID `com.ilgeodeurim.ilgeodeurim` (`app/ios/Runner.xcodeproj` 의 `PRODUCT_BUNDLE_IDENTIFIER`)
   - Web: 사이트 도메인 (서버 흐름을 쓸 때)
4. 카카오 로그인 활성화 ON. Redirect URI 에 `{PUBLIC_BASE_URL}/api/auth/kakao/callback` (서버 인가 코드 흐름을 쓸 때).
5. 동의항목: 닉네임·프로필 사진(선택 동의 권장). 이메일은 필수로 하지 않는다. 어르신은 이메일이 없는 경우가 많고, 이메일 필수 동의는 비즈 앱 심사가 필요하다.
6. 보안: Client Secret을 켜면 코드 생성 후 서버 `KAKAO_CLIENT_SECRET`.
7. 카카오 인가 요청은 PKCE(`code_challenge`)를 보낸다. 콘솔이 거부하면 서버 `KAKAO_USE_PKCE=0`. state·시크릿·앱 쪽 PKCE는 그대로다.
8. 연결 끊기 웹훅은 아직 받지 않는다. 탈퇴는 어드민 키 또는 앱이 넘긴 카카오 토큰으로 `unlink` 한다.

Android 매니페스트의 카카오 액티비티는 SDK 2.x 이름 `com.kakao.sdk.flutter.auth.AuthCodeHandlerActivity` 이다. iOS `Info.plist` 에는 `LSApplicationQueriesSchemes` (`kakaokompassauth`, `kakaolink`)가 있다.

### Google Cloud Console (console.cloud.google.com)

1. 프로젝트 만들기 → OAuth 동의 화면. 앱 이름, 지원 이메일, 범위 `openid` `email` `profile`. 게시 상태를 프로덕션으로.
2. 사용자 인증 정보 → OAuth 클라이언트 ID 3개.
   - 웹 애플리케이션: 승인된 리디렉션 URI `{PUBLIC_BASE_URL}/api/auth/google/callback`. 클라이언트 ID → 서버 `GOOGLE_WEB_CLIENT_ID` 와 앱 `GOOGLE_SERVER_CLIENT_ID`. 클라이언트 비밀번호 → 서버 `GOOGLE_CLIENT_SECRET`.
   - Android: 패키지명 `com.ilgeodeurim.ilgeodeurim` + SHA-1 세 개(디버그 키스토어, 릴리스 업로드 키, **Play Console 앱 서명 키**).
   - iOS: 번들 ID `com.ilgeodeurim.ilgeodeurim`. 클라이언트 ID → 앱 `GOOGLE_IOS_CLIENT_ID`, Info.plist `GIDClientID`. URL 스킴은 클라이언트 ID를 뒤집은 값 (`123-abc.apps.googleusercontent.com` → `com.googleusercontent.apps.123-abc`) 으로 Info.plist 의 `REVERSED_IOS_CLIENT_ID` 를 바꾼다. `GIDServerClientID` 는 웹 클라이언트 ID.
3. 서버 `GOOGLE_CLIENT_IDS` 에 웹·Android·iOS ID를 쉼표로 모두 넣는다. 앱이 `serverClientId` 로 웹 ID를 쓰면 ID 토큰 aud 는 웹 ID가 되고, 플랫폼 ID도 목록에 있으면 어느 쪽이든 받는다.

### 앱에서 쓰는 흐름

- 카카오: 카카오톡이 있으면 카카오톡, 취소가 아닌 실패나 미설치면 카카오계정. access token 을 `POST /api/auth/kakao`.
- 구글: `google_sign_in` 7의 `initialize(serverClientId:)` → `authenticate()` → `idToken` 을 `POST /api/auth/google`.
- 토큰은 `flutter_secure_storage` (Android EncryptedSharedPreferences, iOS Keychain `first_unlock`). access 만료 60초 전에 자동 갱신. 갱신 요청은 한 번에 하나만.
- `USE_MOCK`(서버 주소가 없으면 기본)이면 키 없이 가짜 사용자로 로그인 화면이 끝까지 돈다.
- 웹에서는 카카오 SDK 2의 네이티브 로그인과 구글 `authenticate()` 를 쓰지 않는다. 웹은 서버 인가 코드 흐름이 준비돼 있으나 앱 버튼에는 아직 연결하지 않았다.

## 3단계 B 켜기

패키지·번들 ID 는 `com.ilgeodeurim.ilgeodeurim` 그대로다. 스토어에 처음 올리기 전에 바꿀 수 있다. 앱 표시 이름은 **읽다**.

이 PC에는 Flutter가 없다. 아이콘은 `server/.venv` 의 Pillow로 `app/tooling/make_icons.py` 를 돌려 넣어 두었다. Flutter가 있는 곳에서는 `flutter pub get` 다음 `dart run flutter_launcher_icons` 로 같은 설정을 다시 만들 수 있다.

### Firebase / FCM

1. Firebase 프로젝트에 Android 앱(`com.ilgeodeurim.ilgeodeurim`)과 iOS 앱을 등록한다.
2. `google-services.json` 을 `app/android/app/` 에 둔다. 파일이 있을 때만 Gradle이 Google Services 플러그인을 켠다. 깃에 올리지 않는다.
3. `GoogleService-Info.plist` 를 Xcode의 Runner에 넣는다. 깃에 올리지 않는다.
4. iOS는 APNs 인증 키(.p8)를 Firebase에 올린다.
5. 서버 서비스 계정 JSON은 저장소 밖에 두고 `FCM_SERVICE_ACCOUNT_FILE` 만 넣는다. `PUSH_PROVIDER` 를 비우면 키가 있을 때 FCM, 없으면 보내지 않고 `DISABLED` 로 남긴다.
6. 앱은 로그인 뒤 토큰을 `POST /api/me/push-token` 으로 올린다. 채널 이름은 `가족 알림`(id `family`). Firebase 초기화가 실패하거나 `USE_MOCK` 이면 푸시를 꺼 둔다.

### Android

- `android/local.properties` 에 `app.link.host=실제도메인` (기본 `ilgeodeurim.example`). 초대 https 링크의 App Links 호스트다.
- 서버 `ANDROID_CERT_SHA256` 에 앱 서명 SHA-256(쉼표로 여러 개). `/.well-known/assetlinks.json` 이 그 값을 내려준다.
- 공유: 다른 앱에서 사진 또는 PDF를 읽다로 보낸다. 액티비티는 `singleTask` 라 이미 켜진 앱도 받는다.
- 최소 SDK 24. 알림 권한은 처음 알림을 맞출 때 묻는다.

### iOS Share Extension (Xcode, Mac)

Windows에서는 타깃을 프로젝트에 넣지 못했다. 소스만 있다.

1. Xcode에서 Runner에 Share Extension 타깃을 추가한다. 번들 ID `com.ilgeodeurim.ilgeodeurim.ShareExtension`.
2. `app/ios/ShareExtension/` 의 `ShareViewController.swift`, `Info.plist`, `ShareExtension.entitlements` 를 그 타깃에 넣는다.
3. Swift Package `receive_sharing_intent` 를 **확장 타깃**에도 연결한다. `ShareViewController` 는 `RSIShareViewController` 를 상속한다.
4. Runner와 확장 둘 다 App Group `group.com.ilgeodeurim.ilgeodeurim` 을 켠다. Runner Info.plist의 `AppGroupId` 와 URL 스킴 `ShareMedia-com.ilgeodeurim.ilgeodeurim`, `ilgeodeurim` 은 이미 있다.
5. `app/ios/Runner/Runner.entitlements` 를 Runner의 Code Signing Entitlements로 지정한다. Associated Domains의 `applinks:ilgeodeurim.example` 을 실제 도메인으로 바꾸고, 서버 `APPLE_TEAM_ID` 를 넣는다. 푸시는 development다. 출시 빌드는 production으로 바꾼다.

### 기능 세 가지를 시험하는 법

서버는 `AI_PROVIDER=fake` 로 띄운다. 앱은 `flutter run --dart-define=SERVER_URL=http://10.0.2.2:8000` (에뮬레이터). 키 없이 화면만 보려면 `--dart-define=USE_MOCK=true`. 가짜 가족 번호는 `123456`.

1. **스캔·품질.** 서류 찍기 → 문서 스캐너(갤러리 없음, 최대 5장). 흐리거나 어두우면 다시 찍기 / 그래도 보내기. 서버가 `photo_` 로 막으면 그래도 보내기는 없다. 사진첩에서 고르기는 홈의 두 번째 버튼(최대 5장).
2. **공유 메뉴.** Android: 갤러리·파일에서 사진 또는 PDF를 공유 → 읽다. 앱이 꺼져 있어도, 켜져 있어도 같은 품질 검사로 들어간다. iOS는 위 확장을 넣은 뒤에 사진 앱의 공유 시트에서 확인한다. PDF는 기기에서 JPEG 최대 5장으로 바꾼다.
3. **가족.** 자녀: 가족 → 가족 초대하기 → 나는 자녀예요 → 관계·별명 → 6자리. 부모: 번호 넣기 → 미리 보기 → 연결하기. 수락하면 양쪽 매핑이 생긴다. 부모 화면의 자녀가 보냄, 결과의 자녀에게 보내기, 대표의 권한 화면(대신 보내기·알림)을 확인한다. 푸시는 Firebase 키가 있을 때만 기기에 도착한다.

가족 표는 `ct_user_family` (V0003). 서류가 가리키는 연결은 기존의 `ct_family_link` 다. 초대 번호는 `ct_family_invite`.
