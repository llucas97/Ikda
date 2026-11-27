# 읽다 Rust 전환 계획

이 문서는 전환 **계획**이다. 앱과 서버 소스를 Rust로 바꾸지 않으며, 키·토큰·서비스 계정 JSON은 여기 적지 않는다.

조사 기준은 이 저장소의 Flutter 앱(`app/`), FastAPI 서버(`server/`), `docs/setup.md`, `docs/api.md`, `docs/dev-notes.md`, `docs/auth-plan.md`, `docs/phase3-plan.md`다. `docs/med-photo-alarm-plan.md`는 저장소에 없다. 기한 알림은 앱이 기기에서 예약하고, 가족 알림은 서버가 FCM으로 보낸다.

**권장안은 A, 서버만 Rust로 옮기는 것이다.** 앱은 Flutter로 둔다. 근거는 [2장](#2-전환-범위-옵션-비교)에 있다.

---

## 1. 현재 구조 요약

### 언어와 배포 형태

| 구분 | 지금 | 근거 |
|---|---|---|
| 앱 | Flutter / Dart `>=3.9`, Android·iOS·Web | `app/pubspec.yaml` |
| 패키지·번들 | `com.ilgeodeurim.ilgeodeurim` | `docs/setup.md` |
| 서버 | Python, FastAPI `0.163` + Uvicorn, Pydantic 2, SQLAlchemy 2.1 async | `server/requirements.txt`, `server/app/main.py` |
| DB | PostgreSQL 17이 운영 목표. 개발·테스트는 SQLite 파일도 가능 | `docker-compose.yml`, `server/app/db.py` |
| 스키마 | `server/db/migrations/V0001`–`V0003` SQL. 적용 이력은 `sy_schema_migration` | `server/db/migrate.py` |
| 로컬 실행 | Compose는 Postgres. 서버 프로필은 `python:3.12-slim`에서 기동 시 `pip install` | `docker-compose.yml` |
| 운영 목표 | Cloud Run + HTTPS. **Dockerfile, Cloud Run 서비스, CI 워크플로는 아직 없다** | `docs/dev-notes.md` 배포 항목, `TRUST_PROXY_HEADERS` 주석 |

서버 애플리케이션은 `server/app` 약 4,800줄(42개 모듈)이다. 테스트는 13개 파일, 테스트 함수 145개다. 개발 노트는 2026-11에 163개 통과로 적혀 있으므로, 착수 전에 `pytest --collect-only`로 기준 개수를 다시 고정한다. 앱 Dart는 `app/lib`와 `app/test` 합쳐 약 7,100줄이다.

### 서버 모듈

| 모듈 | 하는 일 | 대략적인 줄 수 |
|---|---|---|
| `app/main.py` | `/health`, `POST /api/analyze`, App Links / Universal Links, CORS | 107 |
| `app/analysis.py`, `quality.py`, `router.py`, `schema.py`, `prompt.py`, `usage.py`, `clock.py` | 사진 수신, 품질 검사, 모델 라우팅, JSON 계약, 지시문, 서울 날짜 | 약 530 |
| `app/providers/` | fake / Gemini / Anthropic. 키 이름은 환경변수 | 약 310 |
| `app/auth/` | 카카오·구글 로그인, PKCE, HS256 액세스 JWT, refresh 회전, 탈퇴 | 약 1,700. `service.py` 498, `providers.py` 301 |
| `app/family/` | 초대, 관계, 서류 보관·동기화, 대신 보내기, 나누기 | 약 1,900. `service.py` 522, `documents.py` 436 |
| `app/push/` | FCM HTTP v1, 가짜 발송, 죽은 토큰 비활성 | 약 300 |
| `app/db.py`, `db/migrate.py`, `db/migrations/*.sql` | 연결, UTC, 마이그레이션 590줄 | — |

표는 `ct_` 접두사, PK는 `<이름>_no`, 시각은 `TIMESTAMPTZ`, 부분 유니크 인덱스가 있다. 예: 활성 가족 쌍, 대기 중 초대 코드. 사진은 DB에 넣지 않고 요청 메모리에서만 다룬다.

### 앱이 서버 밖에 두고 있는 것

앱은 AI 키를 갖지 않는다. 사진 바이트를 서버로 올리고 JSON을 그린다. 서버로 옮길 이유가 없는 기능은 아래에 있다.

- 문서 스캐너 (`cunning_document_scanner`, Android ML Kit / iOS VisionKit)
- 음성 읽기 (`flutter_tts`)
- 기한 로컬 알림 (`flutter_local_notifications`, 하루 전·당일 아침 9시, 지금 구현은 Asia/Seoul)
- 카카오 SDK, 구글 로그인, 보안 저장소 (`flutter_secure_storage`)
- FCM 수신 (`firebase_messaging`), 다른 앱에서 사진·PDF 받기, 공유, 딥링크
- PDF를 JPEG로 그리기 (`pdfrx`), 웹은 파일을 고른다
- 화면, 큰 글씨, IBM Plex Sans KR, Phosphor 아이콘
- 사진 품질 **사전** 검사 (`app/lib/services/photo_quality.dart`). 서버 `quality.py`와 같은 지표이고, 앱 기준이 더 엄격하다. 사용자는 ‘그래도 보내기’를 고를 수 있다

### 외부 HTTP

| 대상 | 용도 | 코드 |
|---|---|---|
| Gemini `generateContent` | 분류 + 구조화 JSON. 기본 공급자 | `providers/gemini.py` |
| Anthropic Messages | 도구 호출로 JSON, 지시문 캐시 | `providers/anthropic.py` |
| 카카오 토큰·사용자·연결 끊기 | 로그인, 탈퇴 | `auth/providers.py` |
| 구글 JWKS, 토큰, 사용자 | ID 토큰 RS256, 인가 코드 흐름 | `auth/oidc.py`, `auth/providers.py` |
| `oauth2.googleapis.com` + FCM v1 | 서비스 계정 JWT(RS256)로 푸시 | `push/fcm.py` |

모델 이름, 타임아웃, 에스컬레이션 종류(`medicine`, `contract`)는 환경변수다. 실측(2026-11-16)으로 보통 서류는 5–10초, 분류 실패 시 좋은 모델부터 다시 시도한다. 앱의 분석 타임아웃은 90초다.

### 앱이 실제로 의존하는 HTTP 계약

계약의 기준은 **지금 서버 동작 + 앱 파서 + pytest**다. `docs/api.md`는 일부 오류 코드와 엔드포인트가 코드보다 뒤에 있다. 예를 들어 구현은 `no_image`, `too_many`, `too_large`, `bad_type`, `ai_failed`이고, API 문서는 `no_images`, `too_many_images`, `image_too_large`, `invalid_image`, `ai_error`로 적혀 있다. `PATCH /api/family/links/{id}/permissions`와 인가 코드 흐름(`authorize` / `callback` / `POST /api/auth/token`)도 문서보다 코드가 앞이다.

앱이 분기하는 값은 좁다.

- 본인 분석은 **200**, 자녀가 대신 보내는 `POST /api/family/links/{id}/analyze`는 **201** (`analysis_service.dart`)
- `401`이고 `error.code == token_expired`이면 액세스 토큰을 한 번 갱신하고 같은 요청을 다시 보낸다
- `error.code`가 `photo_`로 시작하면 다시 찍기만 허용하고 ‘그래도 보내기’가 없다
- 그 밖에는 `error.userMessage`를 그대로 보여 준다
- 성공 JSON의 `id`, `title`은 필수다. `docType`, `oneLiner`, `amount`, `dueDate`, `todos`, `warnings`, `details`, `source`, `sentBy`, `seen`, `access`를 읽는다
- 로그인 응답은 `accessToken`, `accessTokenExpiresIn`, `refreshToken`, `refreshTokenExpiresIn`, `user`가 있어야 한다

시각은 UTC이며 `+00:00`을 `Z`로 바꾼 ISO 8601이다 (`documents.iso_utc`). 날짜는 `YYYY-MM-DD`. 키 이름은 camelCase다.

### 엔드포인트 목록 (구현 기준)

인증·내 정보

- `POST /api/auth/{kakao|google|fake}`
- `GET /api/auth/{provider}/authorize`, `GET /api/auth/{provider}/callback`
- `POST /api/auth/token`, `POST /api/auth/refresh`, `POST /api/auth/logout` (204)
- `GET /api/me`, `DELETE /api/me`, `POST /api/me/push-token` (204)

가족·서류

- `POST /api/family/invites` (201), `DELETE /api/family/invites/{inviteId}` (204)
- `POST /api/family/invites/preview`, `POST /api/family/invites/accept`
- `GET /api/family`
- `PATCH /api/family/links/{linkId}`, `PATCH /api/family/links/{linkId}/permissions`
- `DELETE /api/family/links/{linkId}` (204)
- `POST /api/family/links/{linkId}/analyze` (201)
- `GET /api/family/documents`
- `GET /api/documents`, `POST /api/documents` (201 또는 200), `GET|DELETE /api/documents/{id}`
- `PATCH /api/documents/{id}/todos/{todoId}`
- `POST /api/documents/{id}/seen` (204)
- `POST /api/documents/{id}/shares`, `DELETE /api/documents/{id}/shares/{linkId}` (204)
- `GET /f/{token}` HTML (CSP, `no-store`, `no-referrer`, `noindex`)

기타

- `GET /health` → `{"ok": true, "provider": "..."}`
- `GET /.well-known/assetlinks.json`
- `GET /.well-known/apple-app-site-association`, `GET /apple-app-site-association`
- `POST /api/analyze` (200). multipart 필드 이름은 `images`, 선택 필드 `save`

오류 봉투는 `{"error": {"code", "userMessage", ...}}`다. 품질 실패는 `page`, `problems`가 더 붙는다. 토큰·가족 응답은 `Cache-Control: no-store`. CORS 메서드는 GET, POST, PATCH, DELETE다.

---

## 2. 전환 범위 옵션 비교

작업량은 일정(며칠, 몇 주)이 아니라 **무엇을 다시 쓰는지**로 적는다. 난이도는 그 줄 수와 플랫폼 연동의 곱이다.

### A. 서버만 Rust

예: `axum` + `tokio` + `tower-http`, DB는 `sqlx`. `actix-web`으로 바꿔도 아래 모듈 경계는 같다. 이 계획의 기본 프레임워크는 axum이다.

| | |
|---|---|
| 장점 | AI 키, JWT, 가족 권한, 사진 바이트가 있는 프로세스만 바꾼다. 기존 앱은 `SERVER_URL` 하나로 그대로 동작한다. Cloud Run에 올릴 첫 이미지가 아직 없으므로, 운영에 Python 이미지를 올렸다가 걷어낼 일이 없다. 콜드 스타트와 이미지 크기가 줄고, 요청마다 사진을 메모리에만 두는 경로를 소유권으로 표현하기 좋다. pytest가 계약 테스트로 남아 있다. |
| 단점 | 인증(refresh 회전, PKCE, JWKS)과 가족 트랜잭션을 동작까지 같게 맞춰야 한다. Pillow와 Rust `image`의 픽셀 수치가 완전히 같지 않을 수 있다. 서버 언어가 둘인 동안 로컬 개발 방법이 잠시 갈린다. |
| 난이도 | 중. 줄 수는 크지 않고, 위험한 파일은 `auth/service.py`, `family/service.py`, `family/documents.py`로 모인다. |
| 위험 | 중. 토큰·해시·상태 코드를 어기면 이미 깔린 개발 빌드가 로그인과 분석에서 멈춘다. 운영 트래픽은 아직 없다. |
| 작업량 | 서버 약 4,800줄과 SQL 590줄, 테스트 13파일. 화면과 플러그인은 그대로다. |

### B. 앱 핵심 로직만 Rust (`flutter_rust_bridge`)

후보 로직은 `photo_quality.dart`와 날짜 파싱, 서류 JSON 검증 정도다. 분석·로그인·가족은 이미 서버에 있다.

| | |
|---|---|
| 장점 | 앱과 서버의 품질 지표를 한 구현으로 모을 수 있다. UI와 카카오·스캐너·FCM은 Dart에 남는다. |
| 단점 | 앱은 Android, iOS, **Web**을 모두 만든다. 브리지는 NDK, iOS 정적 라이브러리, 웹은 wasm 빌드를 추가한다. 맞추고 싶은 품질 검사는 이미 서버에 있고, 앱 쪽은 기준만 더 엄격한 약 200줄이다. 브리지 코드와 빌드 실패가 그 줄 수보다 크다. 서버의 Cloud Run 이득은 생기지 않는다. |
| 난이도 | 중. 로직은 작고, 툴체인이 어렵다. |
| 위험 | 중. 웹 빌드와 스토어 빌드가 한 언어 더 의존한다. 서버 API는 그대로라 데이터 손실 위험은 작다. |
| 작업량 | 순수 함수는 작다. Android·iOS·Web 빌드 사슬을 새로 얹고 유지하는 일이 대부분이다. |

### C. 앱까지 전부 Rust (Dioxus / Tauri 모바일 등)

| | |
|---|---|
| 장점 | 언어가 하나로 줄면 장기적으로 빌드 종류가 줄 수 있다. 아직 스토어 출시 전이라 패키지 이름을 유지한 채 다시 짤 여지는 있다. |
| 단점 | 지금 앱의 가치는 화면과 OS 연동에 있다. 문서 스캐너, 카카오 SDK, 구글 로그인, FCM, 로컬 알림, 공유 시트, 키체인, TTS, PDF 래스터는 Flutter 플러그인으로 붙어 있다. Dioxus·Tauri 모바일은 이 조합을 대체하는 안정된 계층이 아니다. 어르신용 큰 글씨, 한글 서체, 세 플랫폼을 다시 맞추는 일은 서버 이식과 별개의 제품 재작성이다. |
| 난이도 | 상. |
| 위험 | 상. 로그인·촬영·알림·가족 딥링크가 동시에 흔들린다. 서버 계약이 맞아도 앱을 배포해야 사용자가 만난다. |
| 작업량 | 앱 약 7,100줄과 네이티브 연동 전부. 서버 이식과 더하면 저장소에서 가장 큰 재작성이다. |

### 권장안과 근거

**A를 권장한다.**

1. 비밀, 사진 바이트, 권한 판정, AI 비용이 있는 곳은 서버다. Rust를 넣을 이유가 있는 곳과 같다.
2. 앱이 지켜야 할 조건은 HTTP 계약이다. A는 그 계약을 유지하고 앱 릴리스를 요구하지 않는다.
3. B가 공유할 만한 순수 로직은 품질 검사뿐이고, 서버를 A로 옮긴 뒤에도 Dart 쪽에 남겨 둘 수 있다. 지표가 어긋나 버그가 되면 그때 함수 하나만 공유하면 된다. 지금 브리지를 도입하는 비용이 더 크다.
4. C는 스캐너·카카오·FCM·로컬 알림을 다시 만드는 일이다. 읽다의 다음 할 일(기기 시험, Cloud Run, 로그인 마무리)과 겹치면 출시가 밀린다.
5. 운영 Cloud Run이 아직 없다. 첫 HTTPS 배포의 프로세스를 Rust로 두면, 살아 있는 Python 서비스에서 트래픽을 쪼개는 일을 피할 수 있다. 그 전까지 개발용 Python 서버는 끄지 않는다.

B와 C는 이 계획의 범위 밖이다. A가 끝난 뒤 품질 지표를 한 곳으로 모을 필요가 확인되면 B를 다시 연다.

---

## 3. 권장안 기준 모듈 매핑

크레이트 버전은 구현 시점에 안정판을 고르고 `Cargo.lock`에 고정한다. 이 문서에 버전을 박지 않는다.

| 지금 | Rust |
|---|---|
| FastAPI, Uvicorn, CORS | `axum`, `tokio`, `tower-http` (cors, trace, timeout, request body limit) |
| `python-multipart` | `axum` multipart. 필드 이름 `images`, `save` 유지. 기본 본문 한도는 50MB 근처로 올린다 (사진 5장 × 10MB + 여유). |
| Pydantic 모델, camelCase | `serde` / `serde_json`. 키 이름은 지금 문자열 그대로 (`docType`, `oneLiner`, `userMessage`, `accessTokenExpiresIn`). |
| SQLAlchemy async, `asyncpg` | `sqlx` + Postgres. 쿼리는 기존 SQL의 부분 인덱스·`WHERE status_cd`를 그대로 쓴다. 표는 ORM으로 다시 만들지 않는다. |
| SQLite `create_all` | Rust 서버의 대상은 Postgres다. SQLite 방언(부분 인덱스 표기, JSONB, `BIGSERIAL`)을 한 번 더 옮기지 않는다. 로컬은 이미 있는 Compose Postgres를 쓴다. |
| `db/migrate.py` | 같은 `V*.sql`과 `sy_schema_migration`(version, checksum)을 읽는 작은 러너. `sqlx migrate`의 다른 이력 표를 새로 만들지 않는다. 이미 적용된 파일은 체크섬이 같으면 건너뛰고, 내용이 바뀌면 지금처럼 경고만 하고 새 V 파일을 요구한다. |
| `httpx` | `reqwest`, rustls. Gemini, Anthropic, 카카오, 구글, FCM. |
| PyJWT HS256 액세스 토큰 | `jsonwebtoken`. 헤더 `typ`은 `at+jwt`. 클레임은 `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`, `jti`, `sid`, `typ=access`, `utype`. 검증 여유 10초. 알고리즘은 HS256만 허용. |
| refresh, 초대 코드, PKCE | `sha2`, `hmac`, `base64`, `rand`. refresh 원문은 저장하지 않고 SHA-256 hex만 저장한다. 초대 번호는 `HMAC-SHA256(JWT_SECRET, "family-invite:"+번호)`. 링크 토큰은 SHA-256 hex. PKCE는 S256만, `plain`은 거절. |
| 구글 JWKS, FCM 서비스 계정 RS256 | `jsonwebtoken`의 RSA. JWKS는 Cache-Control과 최소 재조회 간격을 지금 `JwksCache`와 같게. FCM 범위는 `https://www.googleapis.com/auth/firebase.messaging`. |
| Pillow 품질 검사 | `image` (jpeg, png, webp). 알고리즘 계약: 긴 변 1000px 흑백, 8×8 칸, 라플라시안, 상한 60MP에서 413 `too_large`. HEIC는 매직 바이트로 받고, 디코드가 안 되면 품질 검사를 건너뛴 뒤 AI로는 그대로 보낸다 (지금 Pillow와 같은 분기). |
| 환경변수 | 이름과 기본값은 `server/.env.example`과 각 `config.py`를 그대로 둔다. 값은 코드에 넣지 않는다. |
| 로그 | `tracing`. 사진 바이트, Authorization, refresh, 서비스 계정 PEM은 로그에 남기지 않는다. 제공자 오류는 지금처럼 앞부분만. |
| pytest | 아래 검증 방법. 비즈니스 규칙을 주석으로만 옮기지 않고 테스트로 고정한다. |
| fake AI, fake 푸시, `AUTH_FAKE_PROVIDER` | 개발·테스트용으로 유지. 운영 기본은 끈다. |

지시문(`prompt.py`)과 관계 코드(`relations.py`의 `RELATION_CODES`, 반대말, 조사 처리)는 문자열 계약이다. 푸시 제목·본문은 잠금 화면에 나가므로 서류 제목과 금액을 넣지 않는 지금 문구를 유지한다.

### API 호환을 유지하는 방법

기존 앱 바이너리가 서버만 바뀐 뒤에도 동작하게 하려면 아래를 지킨다.

1. **경로, 메서드, 상태 코드**를 위 목록과 같게 둔다. 특히 분석 200과 대신 보내기 201, 삭제·로그아웃·푸시 등록의 204 빈 본문.
2. **JSON 키 이름**을 바꾸지 않는다. 성공 본문에서 앱이 필수로 캐스팅하는 키(`id`, `title`, 토큰 필드, `user`)를 빼지 않는다. `null`을 생략하는 정리는, 골든 응답과 앱 파서가 둘 다 통과한 뒤에만 한다.
3. **오류 코드는 구현을 기준으로 유지**한다. 문서에 적힌 다른 철자로 고치지 않는다. 문서를 코드에 맞추는 수정은 별도이고, 앱이 읽는 `photo_*`, `token_expired`, `userMessage`는 유지한다.
4. **토큰은 양쪽에서 통하게** 만든다. 전환 중에 발급 주체가 바뀌어도 같은 `JWT_SECRET`, 같은 `iss`/`aud`, 같은 refresh 해시로 검증된다. 이미 발급된 refresh 행(`ct_user_access.refresh_token_hash`)을 버리지 않는다.
5. **DB 스키마를 마이그레이션으로 유지**한다. Rust용 표를 새로 만들지 않는다. 부분 유니크 인덱스 이름을 포함해 `tests/test_auth_schema.py`가 보는 계약을 통과시킨다.
6. **개인정보 규칙**을 유지한다. 사진과 토큰 원문은 디스크·로그·DB에 없다. 푸시 데이터는 `type`, `documentId`, `linkId`처럼 지금 키만 보낸다.
7. **한 데이터베이스에 쓰는 프로세스는 하나**다. 인증 회전과 초대 수락을 Python과 Rust가 동시에 쓰면 재사용 탐지와 유니크 인덱스가 서로 다른 구현을 때린다. 병행은 읽기 비교나 스테이징 복제본에서 하고, 공유 DB의 쓰기는 경로 묶음 단위로 한쪽에만 둔다.

앱 변경이 필요해 보이는 순간(필드 추가가 아니라 필드 의미 변경, 상태 코드 변경) 그 항목은 전환 실패로 보고 Python 구현을 유지한다.

---

## 4. 단계별 마이그레이션 순서

각 단계가 끝나도 앱 소스는 그대로다. Python 서버는 해당 단계의 검증이 끝나기 전까지 개발용 기본 서버로 둔다.

### 0. 계약 고정

- `pytest --collect-only`로 개수를 적고, 현재 스위트를 기준선으로 저장한다.
- 대표 요청의 상태 코드·헤더·본문을 골든 파일로 남긴다. AI 본문은 `server/samples/results/*.json`을 재사용하고, 로그인·초대·동기화는 기존 테스트가 기대하는 JSON을 추출한다.
- `docs/api.md`와 코드가 다른 오류 코드·누락 엔드포인트를 표로 적고, **호환 기준은 코드**라고 못 박는다. 문서 수정은 이 전환과 섞지 않는다.
- 멀티파트, 204, `Cache-Control`, CORS 메서드를 골든에 포함한다.

검증: 골든 재생이 현재 Python 서버에서 통과한다.

### 1. 러스트 프로세스 뼈대

- 워크스페이스 하나. 실행 파일은 HTTP 서버, 보조 파일은 마이그레이션 러너.
- `GET /health`와 오류 봉투, CORS, 환경변수 로딩, `PORT`(없으면 8000).
- 요청 본문 한도, 트레이싱, 사진·인증 헤더를 로그에서 빼는 필터.
- Dockerfile과 로컬 기동. 동작은 Python과 같게 두고, 아직 라우트는 `/health`와 정적 well-known만 둔다.

검증: `curl`로 `/health`. 이미지가 Cloud Run에서 기동해 같은 JSON을 주는지 스테이징에서 확인. 트래픽은 앱이 보지 않는 주소로만.

### 2. 스키마 러너

- 기존 `V*.sql`을 빈 Postgres에 적용하고, 다시 실행하면 적용 파일이 없게 한다.
- 체크섬이 다른 이미 적용된 파일은 실패로 삼지 않고 경고한다 (지금 `migrate.py`와 동일).
- 스키마 테스트가 보는 표·열·부분 인덱스를 조회하는 읽기 전용 검사를 둔다.

검증: Compose Postgres에 러너를 적용한 뒤, 기존 Python 서버가 그 DB로 pytest를 통과한다. 러너가 표를 지우거나 다시 만들면 실패다.

### 3. 인증 (쓰기 전환의 첫 묶음)

순서: 검증 전용 → 로그인 발급 → refresh 회전·재사용 탐지 → 로그아웃·탈퇴 → 인가 코드·PKCE.

- Python이 서명한 액세스 토큰을 Rust가 받아들이고, Rust가 서명한 토큰을 Python이 받아들이는 교차 테스트를 먼저 둔다. 비밀은 테스트 대역이며 저장소에 커밋하지 않는다.
- refresh 해시, 유예(`REFRESH_REUSE_GRACE_S`), 세션 상한, 탈퇴 시 카카오 연결 끊기 분기를 테스트로 고정한다.
- 이 묶음의 쓰기를 공유 DB에서 양쪽이 하지 않는다. 스테이징에서 인증 경로의 업스트림을 Rust로 바꿀 때 로그인부터 탈퇴까지 한 번에 옮긴다.

검증: `test_auth_*.py` 시나리오를 Rust 프로세스에 HTTP로 재생. 가짜 제공자(`AUTH_FAKE_PROVIDER`)로 앱 로그인 화면 스모크.

### 4. 서류와 가족

읽기를 먼저 한다. `GET /api/documents`, `GET /api/documents/{id}`, `GET /api/family`, `GET /api/family/documents`.

그 다음 쓰기를 한 묶음으로 옮긴다. 초대 생성·미리보기·수락·취소, 연결 수정·권한·끊기, 서류 업로드·묘비 삭제·할 일·seen·나누기, `since` 동기화와 `deleted` 목록.

초대 HMAC과 실패 횟수 제한, 하루 대신 보내기 한도, 주인만 삭제, 자녀만 대신 보내기를 기존 테스트와 같은 코드로 유지한다.

검증: `test_family_*.py` HTTP 재생. 앱에서 초대 번호, 수락, 서류 목록 동기화.

### 5. 분석 파이프라인

- 매직 바이트, 장수, 크기, 빈 파일, 품질 코드(`photo_blurry` 등)와 `page`/`problems`.
- fake 공급자로 분류 → 에스컬레이션 → 폴백 순서 (`router.py`의 재시도 상태 코드).
- 품질 수치는 샘플 이미지로 Python과 비교한다. 허용 오차를 숫자로 적고, 오차를 넘으면 임계값을 조용히 바꾸지 않고 구현을 맞춘다.
- Gemini·Anthropic 호출 형식(스키마, 시스템 지시문, thinking 설정, 도구 호출)을 녹화된 요청으로 비교한다. 유료 API를 양쪽에서 두 번 부르는 그림자 시험은 하지 않는다. 실호출 확인은 샘플 소수로, 키는 환경에서만 읽는다.

검증: `test_api.py`, `test_quality.py`. 앱이 200/201과 `photo_*`를 지금처럼 처리하는지.

### 6. 푸시

- 가짜 발송기로 수신 대상, 죽은 토큰 비활성, `ct_push_log`.
- 문구에 제목·금액이 없는지.
- FCM 실호출은 스테이징 비밀로 한 번. 프로젝트 ID와 비공개 키는 로그에 남기지 않는다.

검증: `test_push.py`. 기기 수신은 이미 개발 노트에 있는 실기기 시험에 포함한다.

### 7. 링크용 HTML과 앱 링크

- `GET /f/{token}` 헤더와 앱 딥링크 스킴 `ilgeodeurim://family/join?t=`.
- `assetlinks.json`은 `ANDROID_CERT_SHA256`이 있을 때만 지문을 채운다. `apple-app-site-association`의 팀 ID는 `APPLE_TEAM_ID`.

검증: 헤더 골든. 잘못된 토큰은 404.

### 8. 병행과 전환

운영 서비스가 아직 없으므로 기본 전환은 이렇다.

1. 스테이징 Postgres는 하나다. 쓰는 서버는 단계 3 이후 항상 하나다.
2. 개발자의 기본 `SERVER_URL`은 스위트가 끝날 때까지 Python이다.
3. 0–7의 HTTP 재생이 한 Rust 바이너리에서 통과하면, 그 바이너리를 스테이징의 유일한 API로 둔다.
4. 앱은 `SERVER_URL`만 스테이징 주소로 바꿔 로그인, 분석, 가족, 푸시를 손으로 확인한다.
5. 첫 운영 Cloud Run 배포를 그 이미지로 한다. Python 이미지 태그를 롤백용으로 같이 빌드해 둔다.
6. 운영에서 한 릴리스 동안 이상 없으면 Python 서버 프로세스를 기본 경로에서 내린다. SQL과 pytest 원본은 바로 지우지 않는다.

이미 Python이 운영에 올라가 있다면, 같은 공개 URL 뒤에 Rust를 두고 **아직 안 옮긴 경로만** Python으로 프록시한다. Cloud Run 하나에는 경로 분기가 없으므로 프록시는 Rust 프로세스 안에 둔다. 인증 쓰기와 가족 쓰기는 프록시로 잘게 쪼개지 않고 묶음째 옮긴다. 내부 업스트림 주소만 환경변수로 받고, 그 값도 문서에 실주소를 박지 않는다.

검증 방법 요약

| 방법 | 언제 |
|---|---|
| 기존 pytest 시나리오를 Rust에 HTTP로 재생 | 묶음이 끝날 때마다. 테스트가 ASGI `TestClient`에 묶여 있으면 하네스만 HTTP로 바꾼다. 기대값과 단언은 유지한다. |
| 토큰 교차 검증 | 인증 묶음 |
| 샘플 이미지 품질 수치 비교 | 분석 묶음 |
| 스키마 테스트가 같은 DB를 통과 | 러너 적용 직후 |
| 앱 스모크 (`SERVER_URL`만 변경) | 스테이징 단일 서버가 된 뒤 |
| 롤백 | 이전 컨테이너 이미지로 트래픽을 되돌리고, DB는 전진 전용 마이그레이션이라 스키마를 내리지 않는다 |

---

## 5. 배포 변경점

### 컨테이너와 Cloud Run

지금은 운영 이미지가 없다. Compose의 서버 프로필은 기동할 때마다 `pip install`을 한다. Rust 배포는 다단계 빌드로 바꾼다.

- 빌드 스테이지: 공식 Rust 이미지에서 `--release` 빌드.
- 런타임 스테이지: `ca-certificates`가 있는 얇은 이미지. Gemini·구글·카카오·FCM이 TLS로 나가기 때문이다. 비루트 사용자. 셸과 컴파일러는 넣지 않는다.
- 프로세스는 `0.0.0.0:$PORT`에 바인드한다. Cloud Run이 `PORT`를 주입한다. 로컬 기본은 8000이라 앱 문서의 `localhost:8000`이 유지된다.
- 헬스는 `GET /health`. 스타트업에 DB 마이그레이션을 넣지 않고, 배포 잡이 러너를 먼저 돌리게 한다. 실패한 마이그레이션 위에 새 태스크가 뜨지 않게 한다.
- `TRUST_PROXY_HEADERS`는 Cloud Run에서만 켠다. 꺼진 상태에서는 `X-Forwarded-For`를 클라이언트 IP로 믿지 않는다 (지금 `auth/deps.py`와 같음).

이미지 크기와 빌드 시간은 이 저장소에서 측정한 값이 아니다. 같은 종류의 서비스에서 보이는 범위를 계획용으로만 적는다.

- 런타임 이미지는 Python slim에 Pillow·cryptography·SQLAlchemy를 넣은 경우보다 작아지는 쪽이 보통이다. Rust 바이너리와 CA 번들 기준으로 수십 MB대가 흔하고, Python 이미지는 의존 휠 때문에 수백 MB가 되기 쉽다. 구현 후 실제 `docker image` 크기를 적고 이 문장의 범위를 고친다.
- 클린 `cargo build --release`는 수분이다. `sqlx`, `reqwest`, `image`가 대부분이다. CI 캐시(레지스트리·git·target) 없이 매 커밋을 클린 빌드하면 Python `pip install`보다 느리다. 캐시가 있으면 이후 빌드는 짧아진다. 기동 시간은 인터프리터와 패키지 임포트가 없으므로 Python보다 짧다. 사용자 체감은 여전히 AI 5–10초가 지배한다.
- 요청 제한 시간은 120초에서 시작한다. 앱은 90초에 포기하고, 서버 기본 Gemini 타임아웃은 45초이며 폴백 체인이 그 뒤를 잇기 때문이다. Cloud Run 기본 300초 안에 있다. 측정 후 조정한다.
- 메모리는 1Gi, 동시성은 8에서 시작한다. 요청마다 사진이 최대 5×10MB이고 디코드 버퍼가 더 붙는다. 기본 동시성 80은 이 서비스에 과하다. 숫자 역시 측정 전 가설이다.
- 최소 인스턴스는 0으로 시작해도 된다. 출시 전이고, 콜드 스타트보다 AI 지연이 크다. 기한 알림은 서버 크론이 아니라 기기 로컬 알림이라 서버가 깨어 있을 필요가 없다.
- CPU는 요청 처리 중에만 있어도 된다. 응답을 돌려준 뒤 백그라운드 작업이 없다. FCM과 DB 커밋은 응답 전에 끝난다.

### 환경변수와 비밀

이름만 유지하고 값은 Secret Manager(또는 Cloud Run이 연결하는 비밀 저장소)에서 주입한다. 이미지, 소스, 이 문서, 이슈, 로그에 값을 넣지 않는다.

운영에서 비밀인 것:

- `JWT_SECRET` (32바이트 이상, HS256). 전환 중 Python과 Rust가 같은 값을 써야 토큰이 통한다.
- `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`
- `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_ADMIN_KEY`, `KAKAO_APP_ID`
- `GOOGLE_CLIENT_SECRET`, `GOOGLE_WEB_CLIENT_ID`, `GOOGLE_CLIENT_IDS`
- `DATABASE_URL`
- `FCM_SERVICE_ACCOUNT_JSON` 또는 `FCM_SERVICE_ACCOUNT_FILE`이 가리키는 파일. 비공개 키 파일은 비밀 볼륨으로 마운트하고 이미지에 `COPY`하지 않는다.
- `ANDROID_CERT_SHA256` (앱 링크 지문. 공개 값이지만 저장소에 추측해 적지 않는다.)

비밀이 아닌 설정은 지금과 같은 이름을 쓴다. `AI_PROVIDER`, 모델 이름, `GEMINI_TIMEOUT_S`, `ESCALATE_TYPES`, `CORS_ORIGINS`, `PUBLIC_BASE_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`, TTL, `QUALITY_*`, `FAMILY_*`, `MAX_IMAGES`, `MAX_IMAGE_MB`, `PUSH_PROVIDER`, `AUTH_REQUIRED_FOR_ANALYZE`, `DEBUG_USAGE`, `AUTH_FAKE_PROVIDER`, `TRUST_PROXY_HEADERS`, `APPLE_TEAM_ID`.

운영 기본값: `AUTH_FAKE_PROVIDER` 끔, `DEBUG_USAGE` 끔, `AI_PROVIDER`는 fake가 아니어야 한다. `CORS_ORIGINS`는 실제 출처만. `PUBLIC_BASE_URL`은 https.

`docker-compose.yml`의 서버 프로필에는 로컬 전용 JWT 자리표시자가 들어 있다. Compose의 DB 계정과 비밀번호도 로컬 전용이다. 그 값들을 운영 비밀로 복사하지 않는다.

앱 쪽 키(`KAKAO_NATIVE_APP_KEY`, `google-services.json`, `GoogleService-Info.plist`)는 이번 서버 전환의 대상이 아니다. 지금 `.gitignore` 규칙을 유지한다.

---

## 6. 위험 요소와 미결정 사항

### 위험

| 위험 | 이유 | 완화 |
|---|---|---|
| 토큰 불일치 | 헤더 `typ`, 클레임, 여유 초, refresh 해시가 하나라도 다르면 앱은 `token_expired` 갱신 한 번 뒤에 로그아웃된다 | 3단계 교차 검증을 통과하기 전에는 인증 쓰기를 옮기지 않는다 |
| 이중 쓰기 | 회전·초대 수락·묘비 삭제를 두 프로세스가 하면 재사용 탐지와 유니크 인덱스가 사용자에게 오류로 보인다 | 공유 DB의 쓰기는 항상 한쪽. 프록시를 쓰더라도 묶음 단위 |
| 품질 수치 차이 | `image` 크레이트의 리샘플·라플라시안이 Pillow와 비트 단위로 같지 않으면 같은 사진이 앱에서는 통과하고 서버에서 `photo_*`가 될 수 있다 | 샘플로 오차를 측정하고, 임계값을 몰래 느슨하게 하지 않는다. 알고리즘을 맞춘다 |
| 문서와 코드의 어긋남 | API 문서를 기준으로 오류 코드를 ‘고치면’ 오히려 앱과 pytest가 깨진다 | 호환 기준은 구현과 테스트. 문서 정리는 별도 변경 |
| 본문 한도·타임아웃 | axum 기본 한도와 Cloud Run 기본 동시성은 10MB 사진 5장에 맞지 않는다 | 1단계에 한도·타임아웃·동시성 가설을 설정으로 넣고 측정 |
| HEIC | 매직 바이트는 허용하지만 디코더가 없으면 품질 검사를 건너뛴다. 동작을 바꾸면 아이폰 사진이 갑자기 거절된다 | 지금과 같이 건너뛴다 |
| 마이그레이션 이력 분리 | `sqlx migrate` 기본 표를 쓰면 이미 적용된 V1–V3를 다시 실행할 수 있다 | `sy_schema_migration`만 사용 |
| 비밀 유출 | 디버그 응답, 패닉 로그, 이미지 ENV | `DEBUG_USAGE` 운영 끔. 로그 필터. 비밀은 마운트 |
| 푸시 문구 회귀 | 조사 처리(`josa`)가 틀리면 잠금 화면 문장이 어색해진다. 개인정보가 들어가면 지금 정책이 깨진다 | 문구 테스트. 제목·금액 금지 유지 |
| 첫 배포와 기능 미완이 겹침 | 개발 노트의 미완(요청 수 제한, 세션 청소, 실기기 스캐너)을 이식 중에 같이 넣으면 계약이 움직인다 | 이식은 동작 유지. 요청 수 제한은 전환 뒤 별도 작업 |

### 미결정

착수 전에 정하면 되는 것과, 측정 뒤에 정해도 되는 것을 나눈다.

착수 전

- Rust 서버 크레이트의 디렉터리 이름 (`server-rs/` 등). 기존 `server/` Python은 롤백과 테스트 기준선으로 남긴다.
- 스테이징 GCP 프로젝트와 Secret Manager. 이 저장소에는 프로젝트 ID가 없다.
- 첫 운영 배포 전에 Python Cloud Run을 만들지 말지. 이 계획의 기본은 **만들지 않고** Rust를 첫 운영 프로세스로 두는 것이다. Python을 먼저 운영에 올리기로 하면 8장의 프록시 경로를 쓴다.
- 품질 수치의 허용 오차. 샘플을 돌려 보기 전에는 숫자를 정하지 않는다.
- pytest 하네스를 HTTP로 바꾸는 작업을 어느 커밋에 둘지. 제품 코드와 분리한다.

측정 뒤

- 메모리, 동시성, 요청 제한 시간, 최소 인스턴스. 5장의 가설을 시작값으로 둔다.
- 실제 이미지 크기와 클린 빌드 시간. CI 캐시 위치(Cloud Build 또는 다른 빌더). 저장소에 CI가 아직 없다.
- Postgres 연결 방식(Cloud SQL 커넥터, 소켓, 비공개 IP). `DATABASE_URL` 형식만 같으면 서버 코드 계약은 같다.

하지 않기로 한 것

- 앱을 Dioxus·Tauri로 다시 쓰기
- `flutter_rust_bridge`를 이 전환에 포함하기
- SQLite 지원을 Rust 서버에 다시 구현하기
- 스키마를 ORM으로 재생성하기
- 오류 코드를 API 문서 철자에 맞추기
- 전환 PR에 요청 수 제한, 프롬프트 수정, 화면 수정을 섞기

이 문서의 상태: 계획만 확정한다. 구현 착수는 위 ‘착수 전’ 항목이 정해진 뒤다.
