# 읽어드림 3단계 설계 — 자동 촬영·품질 검사, 공유 메뉴·사진첩, 가족 연결(자녀가 대신 보내기)

✅ = 3단계 A 에서 끝남 (서버, 시험 포함) · ⬜ = 3단계 B 에서 할 일 (대부분 Flutter 앱)

## 0. 한눈에

| 기능 | 서버 | 앱 |
|---|---|---|
| 1. 자동 촬영 + 품질 검사 | ✅ `app/quality.py`. AI 를 부르기 전에 막고 `photo_*` 코드로 알려 줌 | ⬜ OS 스캐너 유지, 기기에서 같은 지표로 먼저 검사, 큰 '다시 찍기' 화면 + '그래도 보내기' |
| 2. 공유 메뉴·사진첩 | (같은 `/api/analyze`) | ⬜ `receive_sharing_intent` (Android SEND/SEND_MULTIPLE, iOS Share Extension), 사진 여러 장 고르기 |
| 3. 가족 연결 | ✅ 초대·수락·끊기, 서류 보관·권한, 대신 보내기, 나누기, 푸시(FCM v1 + 가짜), 감사 기록 | ⬜ 가족 화면, 6자리 번호 화면, 한 번 눌러 수락, '자녀가 보냄' 표시, '자녀에게 보내기', 푸시 받기, 서버 동기화 |

세 입구(카메라 스캐너·공유 메뉴·사진첩)는 모두 같은 흐름으로 들어간다:

```
사진 bytes 목록 ─▶ 기기 품질 검사 ─(문제)─▶ 다시 찍기 화면 ─(그래도 보내기)─┐
                         │ 통과                                              │
                         ▼                                                   ▼
               누구 서류? (나 / 연결된 어르신)  ──▶  POST /api/analyze (save)  또는  /api/family/links/{id}/analyze
                                                         │ 서버 품질 검사(느슨) → AI → 결과(글)만 보관
                                                         ▼
                                                  결과 화면 · 기기 저장소 · (어르신에게 푸시)
```

## 1. 원칙

- **사진은 어디에도 저장하지 않는다.** 서버는 요청 동안 메모리에서만 다루고(`analysis.analyze` 의 `finally` 에서 비움) DB 에는 AI 가 정리한 글만 둔다. 시험 `test_uploaded_images_are_never_stored` 가 SQLite 파일을 통째로 뒤져 사진 속 표시 문자열이 없는지 확인한다. 앱도 공유·스캐너로 받은 임시 파일을 분석 뒤 지운다(⬜).
- **키는 코드·저장소에 없다.** FCM 서비스 계정은 `FCM_SERVICE_ACCOUNT_FILE`(경로) 또는 `FCM_SERVICE_ACCOUNT_JSON`(시크릿). `google-services.json` · `GoogleService-Info.plist` · `*.p8` 은 `.gitignore`. 실제 키가 없으니 기본은 푸시 끔(기록만), 시험은 `FakePushSender`.
- **로그인 코드는 다시 쓰지 않았다.** 바꾼 곳은 두 군데뿐: `db._ensure` 가 가족 모델도 등록, `DELETE /api/me` 가 끝에 `on_user_withdrawn` 을 부름.
- AsOne 식 표 규칙(V0001 과 같음): 접두사 `ct_`, PK `<이름>_no`, `_cd`/`_yn`, UTC `TIMESTAMPTZ`, 감사 컬럼, 한국어 COMMENT.
- 어르신 화면은 말이 짧고 글씨가 크다. 오류의 `userMessage` 는 그대로 보여 줄 수 있는 문장이다.

## 2. 스키마 ✅ (`server/db/migrations/V0002__ct_family_document.sql`, 모델 `app/family/models.py`)

전문(COMMENT 포함)은 마이그레이션 파일. SQLite 는 모델로 바로 만들고, Postgres 는 `python db/migrate.py`. `tests/test_auth_schema.py` 가 SQL 과 모델의 컬럼·유일 색인 이름이 같은지 확인한다.

```sql
CREATE TABLE ct_family_link (            -- 어르신(SENIOR) ↔ 자녀(CHILD)
    family_link_no BIGSERIAL PRIMARY KEY,
    senior_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    child_user_no  BIGINT NOT NULL REFERENCES ct_user(user_no),
    senior_label VARCHAR(30),            -- 자녀가 어르신을 부르는 이름 (엄마)
    child_label  VARCHAR(30),            -- 어르신이 자녀를 부르는 이름 (큰딸)
    status_cd VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE / UNLINKED
    invite_no BIGINT, linked_at TIMESTAMPTZ NOT NULL,
    unlinked_at TIMESTAMPTZ, unlinked_by_user_no BIGINT, unlink_reason_cd VARCHAR(30),  -- SELF / WITHDRAW
    created_at, created_by, updated_at, updated_by,
    CONSTRAINT ck_ct_family_link_not_self CHECK (senior_user_no <> child_user_no));
CREATE UNIQUE INDEX ux_ct_family_link_pair_active ON ct_family_link (senior_user_no, child_user_no) WHERE status_cd = 'ACTIVE';

CREATE TABLE ct_family_invite (          -- 30분, 한 번만
    invite_no BIGSERIAL PRIMARY KEY,
    inviter_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    inviter_role_cd VARCHAR(20) NOT NULL,              -- 받는 사람은 반대 역할
    invitee_label VARCHAR(30),
    code_hash CHAR(64) NOT NULL,                       -- HMAC-SHA256(JWT_SECRET, "family-invite:"+번호)
    link_token_hash CHAR(64) NOT NULL,                 -- SHA-256(256비트 링크 토큰)
    status_cd VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING/ACCEPTED/CANCELLED/EXPIRED
    expires_at TIMESTAMPTZ NOT NULL, accepted_user_no BIGINT, accepted_at TIMESTAMPTZ, family_link_no BIGINT,
    created_at, updated_at);
CREATE UNIQUE INDEX ux_ct_family_invite_code_pending ON ct_family_invite (code_hash) WHERE status_cd = 'PENDING';
CREATE UNIQUE INDEX ux_ct_family_invite_token ON ct_family_invite (link_token_hash);

CREATE TABLE ct_document (               -- AI 결과(글)만. 사진 없음
    document_no BIGSERIAL PRIMARY KEY,
    document_uid VARCHAR(40) NOT NULL,                 -- 앱과 주고받는 ID doc_…, 전체 유일
    owner_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),   -- 자녀가 보낸 것도 어르신 것
    sender_user_no BIGINT, family_link_no BIGINT, sender_label VARCHAR(30),
    source_cd VARCHAR(20) NOT NULL DEFAULT 'SELF',     -- SELF / FAMILY / IMPORT
    doc_type_cd, title, one_liner, amount BIGINT, due_date DATE,
    warnings JSONB NOT NULL DEFAULT '[]', details JSONB NOT NULL DEFAULT '[]',
    model_cd, page_count INTEGER, owner_seen_at TIMESTAMPTZ,   -- '새로 온 서류' 표시
    created_at, created_by, updated_at, updated_by,            -- updated_at = 동기화 기준
    deleted_yn BOOLEAN NOT NULL DEFAULT FALSE, deleted_at);    -- 지우면 내용 비우고 ID 만(묘비)
CREATE UNIQUE INDEX ux_ct_document_uid ON ct_document (document_uid);

CREATE TABLE ct_document_todo (document_no → ct_document, todo_uid, title, due_date, detail,
    done_yn, remind_yn, sort_order, done_at, done_by_user_no, created_at, updated_at);
CREATE UNIQUE INDEX ux_ct_document_todo_uid ON ct_document_todo (document_no, todo_uid);

CREATE TABLE ct_document_share (document_no → ct_document, family_link_no → ct_family_link,
    shared_by_user_no, shared_to_user_no, revoked_yn, revoked_at, created_at);
CREATE UNIQUE INDEX ux_ct_document_share_active ON ct_document_share (document_no, shared_to_user_no) WHERE revoked_yn = FALSE;

CREATE TABLE ct_push_log (user_no, push_token_no, event_cd, document_no, family_link_no,
    sender_cd FCM/FAKE/NONE, result_cd SENT/FAILED/INVALID_TOKEN/NO_TOKEN/DISABLED, message_id, error_cd, created_at);
    -- 알림 문구는 남기지 않는다

CREATE TABLE ct_family_log (actor_user_no, event_cd, family_link_no, invite_no, document_no,
    target_user_no, success_yn, fail_reason, ip_address, created_at);
    -- INVITE_CREATE/CANCEL/ACCEPT/FAIL, LINK_LABEL/UNLINK, DOC_SEND/SHARE/UNSHARE/DELETE, ACCESS_DENIED
    -- 번호·토큰 원문은 남기지 않는다. (actor, event, created_at)·(ip, event, created_at) 색인은 맞히기 제한용
```

푸시 토큰은 이미 있는 `ct_user_push_token`(V0001)을 쓴다.

## 3. 권한 규칙 ✅ (`app/family/documents.py`, `app/family/service.py`)

연결은 `ACTIVE` 이고 **두 사람 다 활성 회원**일 때만 산다. 역할은 연결마다 정해진다(한 사람이 어떤 연결에선 자녀, 다른 연결에선 어르신일 수 있다). `ct_user.user_type_cd` 는 초대 때 기본 역할을 고르는 데만 쓴다.

| 하는 일 | 서류 주인 | 연결된 자녀 (보냈거나 나눠 받음) | 그 밖 |
|---|---|---|---|
| 서류 보기 | ✅ | ✅ 읽기만 (`access: FAMILY`, `owner.label`) | 404 + `ACCESS_DENIED` 감사 |
| 할 일 바꾸기·열어 봄·지우기 | ✅ | 403 `owner_only` (+ 감사) | 404 |
| 자녀에게 나누기·거두기 | ✅ (그 연결의 어르신일 때) | 403 `owner_only` | 404 |
| 대신 보내기 `/links/{id}/analyze` | — | 그 연결의 **자녀**만. 어르신이면 403 `not_child` | 404 `link_not_found` |
| 연결 이름 바꾸기 | 자기 쪽 이름만 | 자기 쪽 이름만 | 404 |
| 연결 끊기 | 어느 쪽이든 | 어느 쪽이든 | 404 |

- **없는 것과 못 보는 것을 구별해 주지 않는다**(둘 다 404). 남의 연결·서류 번호를 넣어 보는 일을 막는다.
- **AI 를 부르기 전에** 권한·하루 한도를 확인한다(`check_can_send` → commit → 분석). AI 가 끝난 뒤 `store_sent` 가 연결을 **다시** 확인한다(그 사이 끊겼을 수 있음).
- 연결을 끊으면 그 연결로 나눈 것은 모두 거둔다(`revoked_yn`). 자녀가 보낸 서류는 어르신 것으로 남고 자녀는 더 못 본다. 다시 연결해도 예전 나눔은 살아나지 않는다.
- 탈퇴(`on_user_withdrawn`): 연결 모두 끊음(`WITHDRAW`), 기다리는 초대 취소, **내 서류·할 일·나눔은 지움**(개인정보), 내가 남에게 보낸 서류는 남기되 `sender_label` 을 지움(앱은 '자녀'로 표시).
- 한도: 연결 수 자녀 10·어르신 4(`family_limit`), 대신 보내기 자녀→어르신 하루 30(`send_limit`, AI 비용 보호).

## 4. 초대 흐름 ✅ (서버) / ⬜ (앱)

누가 먼저 해도 된다. 보통은 자녀가 만들고 어르신이 받는다.

1. 초대하는 사람: `POST /api/family/invites {"myRole": "CHILD", "label": "엄마"}` → 6자리 번호(`123 456` 으로 크게), 30분 타이머, 카톡·문자 공유 버튼(`shareText` 에 https 링크 + 번호). 새 초대를 만들면 예전 초대는 취소된다(사람마다 하나).
2. 받는 사람:
   - 링크를 누르면 `https://{PUBLIC_BASE_URL}/f/{token}` → 앱이 있으면 App Links/Universal Links 로 바로 앱(⬜ assetlinks·AASA), 없으면 '앱에서 열기' 페이지(`ilgeodeurim://family/join?t=` 버튼). 이 페이지는 DB 를 보지 않는다(토큰이 맞는지 알려 주지 않음).
   - 또는 앱 '가족 연결 → 번호 넣기'에 6자리 (띄어쓰기·하이픈 괜찮음).
3. 앱이 `POST /api/family/invites/preview` 로 **누가 보낸 초대인지**(이름·사진·내 역할)를 크게 보여 주고, 버튼 하나 **[연결하기]** → `POST /accept`. 이때 상대를 부를 이름은 선택(비우면 '부모님'/'자녀').
4. 초대한 사람에게 `FAMILY_LINKED` 푸시("엄마와 연결됐어요.") — 모르는 사람이 수락했으면 바로 끊을 수 있게.

보안:
- 번호는 `secrets.randbelow` 6자리, **기다리는 초대들 사이에서만** 유일(부분 유일 색인). 저장은 HMAC(키 = `JWT_SECRET`)이라 DB 가 새도 100만 가지를 바로 대입할 수 없다. 링크 토큰은 256비트, SHA-256 저장.
- 한 번만: 수락은 `UPDATE … WHERE status='PENDING' AND expires_at > now` 원자적 선점. 동시에 두 명이 눌러도 한 명만.
- 맞히기 제한: 15분 동안 틀림 사람별 10회, IP별 30회 → 429 `too_many_attempts` (맞는 번호여도). 틀림은 `INVITE_FAIL` 로 기록. 6자리 × 30분 × 10회면 한 사람이 맞힐 확률은 약 1/10만.
- 자기 초대 수락 400 `invite_self`, 이미 연결(역할을 거꾸로 해도) 409 `already_linked`, 초대한 사람이 탈퇴·정지면 무효.

## 5. 푸시 설계 ✅ (서버) / ⬜ (앱)

**서버** (`app/push/`)
- `PushSender` 프로토콜 하나에 구현 둘: `FcmPushSender`(FCM HTTP v1), `FakePushSender`(보낸 것을 `sent` 에 쌓음, 시험·개발).
- 고르기: `PUSH_PROVIDER=fcm|fake|none`. 비우면 서비스 계정이 있으면 fcm, 없으면 **none**(보내지 않고 `DISABLED` 로 기록). `fcm` 인데 키가 없으면 시작할 때 오류.
- FCM v1: google-auth 없이 PyJWT 로 서비스 계정 JWT(RS256, scope `firebase.messaging`) → `oauth2.googleapis.com/token` → access token 을 만료 1분 전까지 재사용. 401 이면 한 번 새로 받아 다시. Android `priority HIGH`, 채널 `family`; APNs `apns-priority 10`, sound default.
- 죽은 토큰: `UNREGISTERED`, `SENDER_ID_MISMATCH`, HTTP 404, `INVALID_ARGUMENT`+`message.token` 위반 → `ct_user_push_token.active_yn=false`. 그 밖 실패(429/5xx)는 `FAILED` 로 기록만(재시도 큐는 B 이후 필요하면).
- `notify_user` 는 본 요청이 commit 된 **뒤에** 부르고, 기기당 8초 제한·예외를 삼켜 **푸시 실패가 요청을 실패시키지 않는다.** 기기 최대 10개, 결과는 기기마다 `ct_push_log` 1행.
- 잠금 화면 개인정보: 알림 문구에 **제목·금액·병명을 넣지 않는다.** 종류만("큰딸이 병원 안내를 보냈어요. 눌러서 확인해 주세요."). 내용은 앱을 열어 로그인된 API 로 받는다.

| event | 받는 사람 | title / body | data |
|---|---|---|---|
| `DOC_RECEIVED` | 어르신 | 자녀가 서류를 보냈어요 / {자녀}이/가 {종류}을/를 보냈어요. 눌러서 확인해 주세요. | type, documentId, linkId |
| `DOC_SHARED` | 자녀 | {어르신}이/가 서류를 보냈어요 / {종류}을/를 같이 봐 달래요. 눌러서 확인해 보세요. | type, documentId, linkId |
| `FAMILY_LINKED` | 초대한 사람 | 가족 연결이 됐어요 / {상대}와/과 연결됐어요. | type, linkId |

**켜는 법 (실제 키가 생기면, 코드 수정 없음)**
1. Firebase 콘솔 → 프로젝트 만들기(Google Cloud 프로젝트 재사용 가능) → Android 앱 `com.ilgeodeurim.ilgeodeurim` 등록 → `google-services.json` 을 `app/android/app/` 에(깃 제외). iOS 앱 같은 번들 ID → `GoogleService-Info.plist` 를 `app/ios/Runner/`(깃 제외). 또는 `flutterfire configure`.
2. iOS: Apple Developer → Keys → APNs 인증 키(.p8) 만들기 → Firebase 프로젝트 설정 → Cloud Messaging → APNs 인증 키 업로드(Key ID, Team ID). Xcode Runner 에 Push Notifications, Background Modes → Remote notifications.
3. 서버: Firebase 프로젝트 설정 → 서비스 계정 → 새 비공개 키(JSON) → 서버 밖 안전한 곳(또는 Secret Manager) → `FCM_SERVICE_ACCOUNT_FILE=/secrets/…json` (또는 `FCM_SERVICE_ACCOUNT_JSON` 에 base64). `PUSH_PROVIDER` 는 비워 두면 자동으로 fcm. 키 권한은 최소(Firebase Cloud Messaging API Admin).
4. 확인: 앱에서 로그인 → `POST /api/me/push-token` → 자녀 계정으로 대신 보내기 → `ct_push_log.result_cd = SENT`.

**앱** ⬜: `firebase_core` 5.2 + `firebase_messaging` 17.x. 로그인 뒤·`onTokenRefresh` 때 `AuthService.registerPushToken`(이미 있음). Android 채널 `family`(중요도 높음), Android 13+ 알림 권한은 이미 있는 흐름 재사용. 알림을 누르면(`getInitialMessage` 콜드 / `onMessageOpenedApp` 웜) `data.type` 따라 `documentId` 화면으로. 앱이 켜져 있으면 `onMessage` → 화면 위 큰 띠 + 목록 새로 고침. `USE_MOCK` 이거나 Firebase 설정 파일이 없으면 `NoopPushService`(앱이 죽지 않게 `Firebase.initializeApp` 실패를 삼킴).

## 6. 품질 검사 ✅ (서버) / ⬜ (앱)

**지표** (`app/quality.py`, 앱 `lib/services/photo_quality.dart` 도 **같은 방법**): 흑백으로 바꾸고 긴 변 1000px 로 줄인 뒤 가장자리 3px 를 잘라 8×8 칸으로 나눔.

| 지표 | 계산 | 서버 기준(막음) | 앱 기준(묻기) |
|---|---|---|---|
| 크기 | 원본 가로·세로 | 짧은 변 < 400 또는 긴 변 < 600 → `photo_small` | 같음 |
| 흐림 `sharpness` | 칸마다 라플라시안(0,1,0/1,−4,1/0,1,0) 분산, 글씨 칸(표준편차>10) 중 상위 10% 값 | < 30 → `photo_blurry` | < 90 |
| 어두움 `mean` | 평균 밝기 | < 40 → `photo_dark` | < 55 |
| 과노출·반사 `clipped` | 250 이상 화소 비율 | > 0.95 이고 글씨 칸 < 5% → `photo_bright` | 평균 > 240 이고 > 0.85 |
| 빈 사진 `content` | 글씨 칸 비율 | < 0.02 → `photo_blank` | < 0.05 |
| 잘림 `edgeSides` | 가장자리 칸이 글씨로 꽉 찬 변 수 | 쓰지 않음 | 스캐너가 잘라 낸 사진만, ≥ 3 이면 약한 안내 |

보정 근거 (`server/samples` 다섯 장): 원본 선명도 2,300~3,000, 가우스 흐림 반지름 2 → 60~80(아직 읽힘), 4 → 약 6(못 읽음). 밝기 ×0.15 → 평균 약 30(못 읽음), ×0.3 → 약 62(읽힘). 서버는 '정말 못 읽는 사진'만 막고(돈 절약), 앱은 더 엄격하게 보되 어르신이 **그래도 보내기**를 고를 수 있다. 앱이 '그래도 보내기'로 보낸 사진도 서버 기준에 걸리면 422 가 온다(이때는 다시 찍기만).

- 서버: 사진을 열 수 없으면(HEIC 등) 검사를 건너뛰고 AI 에 맡긴다. 6천만 화소 넘으면 압축 폭탄으로 413. 검사는 `asyncio.to_thread`. `QUALITY_CHECK=0` 으로 끔. 걸리면 `422 {"error": {"code": "photo_blurry", "userMessage": "2번째 사진: 사진이 흔들렸어요…", "page": 2, "problems": [...]}}` — **AI 를 부르지 않는다.**
- 앱 ⬜: `image` 패키지로 `compute()`(isolate) 안에서 계산. 공유·사진첩으로 받은 사진도 같은 검사. 잘림(`edgeSides`)은 OS 스캐너가 이미 테두리를 찾아 자르므로 약한 안내만. 사진첩·공유 사진은 잘림 검사를 하지 않는다(여백 없는 사진이 많아 오탐).

## 7. API 계약 ✅

공통: Bearer 필수(아니면 401 `login_required`/`invalid_token`/`token_expired`), 응답 `Cache-Control: no-store`, 오류 모양 `{"error": {"code", "userMessage"}}`. ID 는 숫자 `linkId`·`inviteId`, 서류는 문자열 `doc_…`, 시각은 UTC `…Z`.

### `POST /api/analyze` (바뀐 점)
- multipart `images` + 선택 `save=true`. 로그인 + `save` → 내 서류로 보관하고 응답에 서류 필드(`source:"SELF"`, `seen`, `access:"OWNER"`, `sentBy:null` …) + `"saved": true`. 로그인 없이 `save` → `"saved": false`(분석은 됨).
- 새 오류 422 `photo_small|photo_dark|photo_bright|photo_blank|photo_blurry` (+ `page`, `problems`).

### 초대
| 요청 | 응답 | 오류 |
|---|---|---|
| `POST /api/family/invites {"myRole"?: "SENIOR"\|"CHILD", "label"?: "엄마"}` | 201 `{inviteId, code:"123456", myRole, expiresAt, expiresInSeconds:1800, appLink:"ilgeodeurim://family/join?t=…", webLink:"https://…/f/…", shareText}` | 503 `invite_busy`(드묾) |
| `DELETE /api/family/invites/{inviteId}` | 204 | 404 `invite_invalid` (남의 것·이미 끝난 것) |
| `POST /api/family/invites/preview {"code"\|"token"}` | `{inviter:{name, profileImageUrl}, inviterRole, yourRole, expiresAt, alreadyLinked}` | 400 `invite_missing`/`invite_self`, 404 `invite_invalid`, 429 `too_many_attempts` |
| `POST /api/family/invites/accept {"code"\|"token", "label"?}` | `{link}` | 위 + 409 `already_linked`/`family_limit` |

`link` = `{linkId, myRole, member:{role, name, label, profileImageUrl}, linkedAt}`. `label` 은 **내가 상대를 부르는 이름**(없으면 '부모님'/'자녀').

### 가족
| 요청 | 응답 | 오류 |
|---|---|---|
| `GET /api/family` | `{links:[link…], pendingInvite:{inviteId, myRole, expiresAt}\|null}` | |
| `PATCH /api/family/links/{linkId} {"label"}` | `{link}` | 404 `link_not_found` |
| `DELETE /api/family/links/{linkId}` | 204 | 404 |
| `POST /api/family/links/{linkId}/analyze` multipart `images` | 201 서류(`access:"FAMILY"`, `source:"FAMILY"`, `sentBy:{linkId,label}`, `owner:{label}`, `seen:false`) + `pushed`(보낸 기기 수) | 404 `link_not_found`, 403 `not_child`, 429 `send_limit`, `/api/analyze` 의 모든 오류(422 `photo_*` 포함). 권한 오류면 AI 를 부르지 않음 |
| `GET /api/family/documents` | `{documents:[…]}` 자녀 화면: 연결된 어르신들 서류 중 내가 보냈거나 나눠 받은 것 | |

### 서류
| 요청 | 응답 | 오류 |
|---|---|---|
| `GET /api/documents?since=ISO` | `{documents:[…], deleted:["doc_…"], serverTime}`. since 없으면 살아 있는 것 전부(최대 1000) | |
| `POST /api/documents` (기기 저장본: `id?, docType, title, oneLiner, amount, dueDate, todos[{id,title,dueDate,detail,done,remind}], warnings, details, model, createdAt`) | 201 새로 / 200 이미 있음(같은 주인·같은 id). 남의 id 와 겹치면 새 id | 422 형식 |
| `GET /api/documents/{id}` | 서류 | 404 `document_not_found` |
| `DELETE /api/documents/{id}` | 204 (묘비: 내용 비우고 id 만 → 다른 기기가 `deleted` 로 앎) | 403 `owner_only`, 404 |
| `PATCH /api/documents/{id}/todos/{todoId} {"done"?, "remind"?}` | 할 일 | 403, 404 `todo_not_found` |
| `POST /api/documents/{id}/seen` | 204 | 403, 404 |
| `POST /api/documents/{id}/shares {"linkIds"?: [..]}` (없으면 내가 어르신인 모든 연결) | `{sharedTo:[{linkId, label, new, pushed}]}` 다시 눌러도 중복·중복 푸시 없음 | 403 `not_senior`/`owner_only`, 404, 409 `no_family` |
| `DELETE /api/documents/{id}/shares/{linkId}` | 204 | 403, 404 |
| `GET /f/{token}` | HTML '앱에서 열기' (CSP, no-store, no-referrer, noindex) | 404 모양이 틀린 토큰 |

서류 JSON: `{id, docType, title, oneLiner, amount, dueDate, todos, warnings, details, model, createdAt, updatedAt, source, sentBy, seen, access, owner?}`. 지운 서류(since 동기화)는 `deleted` 목록에만.

## 8. 앱 흐름·화면 ⬜ (3단계 B)

**찍기 (어르신)**
1. 홈 큰 버튼 **[서류 찍기]** → `cunning_document_scanner` 3.1(`scanDocuments`, Android ML Kit Document Scanner·iOS VisionKit `VNDocumentCameraViewController`, 자동 테두리·자동 셔터). **유지한다**: 2026-11 최신(3.1.0), 두 OS 의 공식 스캐너를 감싸고, 시험용 가짜 플랫폼(`CunningDocumentScannerPlatform.instance`)이 있다. 갤러리 가져오기는 끔(사진첩은 따로).
2. 기기 품질 검사 → 문제가 있으면 **다시 찍기 화면**: 위에 찍은 사진 썸네일 + 문제별 그림(흔들림·어두움·반사·작음·잘림, `widgets/illustrations.dart` 에 추가) + 큰 글씨 한 문장 + 버튼 두 개 **[다시 찍기]**(먹색, 크게) / [그래도 보내기](테두리). 여러 장이면 "2번째 사진"이라고 말하고 그 장만 다시 찍기. 음성 읽기(`speech.dart`) 버튼.
3. 서버 422 `photo_*` 도 같은 화면(이때는 '그래도 보내기' 없음).

**공유 메뉴·사진첩**
- 다른 앱(카톡·갤러리·문자)에서 공유 → 읽어드림 → 사진 목록을 받아 같은 흐름. 콜드 스타트 `getInitialMedia()`, 웜 `getMediaStream()`, 처리 뒤 `reset()`. 로그인 전에 들어와도 잃지 않게 메모리에 들고 있다가 홈이 뜨면 처리.
- 홈 작은 버튼 [사진첩에서 고르기] → `image_picker` `pickMultiImage(limit: 5)`.
- PDF(공유): 서버는 사진만 받으므로 **기기에서 쪽마다 JPEG 로 그려서**(`pdfrx`, 최대 5쪽, 150dpi) 같은 흐름. 어렵다면 B 의 마지막.
- 연결된 어르신이 있는 **자녀**라면 분석 전에 "누구 서류인가요? [내 서류] [엄마 서류]" (어르신이 한 명이면 버튼 둘).

**가족 화면** (홈 머리글 → 계정 시트 → [가족 연결])
- 연결 목록(이름·부르는 이름·끊기). [가족 초대하기] → 역할 확인("나는 자녀예요 / 부모예요") → **6자리 번호를 아주 크게**(`123 456`), 남은 시간, [카톡으로 보내기](시스템 공유 `shareText`), [번호 읽어 주기]. 화면을 열어 둔 동안 3초마다 `GET /api/family` 로 연결됐는지 확인.
- [번호 넣기] → 숫자 키패드 6칸 → 미리 보기(보낸 사람 이름·사진 크게) → **[연결하기]** 한 번.
- 링크로 들어오면(`app_links` 7.2: `ilgeodeurim://family/join?t=` 와 `https://…/f/{token}`) 바로 미리 보기 → [연결하기]. 로그인이 안 돼 있으면 로그인 뒤 이어서.

**받은 서류 (어르신)**
- 목록·결과 화면에 **'자녀가 보냄'** 띠(예: "큰딸이 보냄", `sentBy.label`), 안 본 것(`seen:false`)은 맨 위·점 표시. 열면 `POST /seen`.
- 결과 화면 **[자녀에게 보내기]**(지금 자리만 있음) → 연결된 자녀가 없으면 "가족을 먼저 연결해 주세요" + [가족 연결]; 한 명이면 바로, 여럿이면 고르기 → `POST /shares` → "큰딸에게 보냈어요".

**자녀 화면**
- [부모님 서류] 탭: `GET /api/family/documents`. 읽기만(할 일 체크 없음). 위에 [엄마 대신 찍어 보내기].

**동기화** (`SyncedDocumentRepository`, 기존 `DocumentRepository` 를 감쌈)
- 로그인 + 서버 모드일 때만. 화면은 언제나 **기기 저장본**을 먼저 보여 준다(오프라인 OK).
- 처음 로그인하면 기기에만 있던 서류를 `POST /api/documents` 로 올림(같은 id 라 여러 번 올려도 하나).
- 앱 시작·포그라운드·푸시 받을 때 `GET /api/documents?since=마지막 serverTime` → 합치기(서버 `updatedAt` 이 더 새로우면 서버 것), `deleted` 는 기기에서도 지우고 알림 취소.
- 할 일 체크·지우기·열어 봄은 기기에 먼저 반영하고 **보낼 일 큐**(shared_preferences)에 넣어 온라인일 때 보냄. 404 면 큐에서 버림.
- 분석은 로그인 상태면 `save=true` 로(서버에 바로 보관). 알림 예약은 지금처럼 기기가 한다(자녀가 보낸 서류도 받으면 예약).
- `USE_MOCK`: `MockFamilyService`(가짜 번호 `123456` 으로 바로 연결, 가짜 서류 하나), `NoopPushService`, 동기화 끔. 로그아웃: 기기 저장본은 그대로 두고(지금 동작) 큐만 비움.

## 9. 플랫폼 설정 ⬜ (3단계 B)

**패키지** (2026-11 확인): `receive_sharing_intent` 1.9.0 (Flutter 3.38+, iOS 는 SwiftPM 만, SceneDelegate 필요), `firebase_core` 5.2.0, `firebase_messaging` 17.x, `app_links` 7.2.2, `image` (품질 계산), `pdfrx` (PDF). `share_handler` 0.0.25 는 15개월째 멈춰 있어 쓰지 않는다.

**Android** (`android/app/src/main/AndroidManifest.xml`)
```xml
<activity android:name=".MainActivity" android:launchMode="singleTask" ...>
  <intent-filter>
    <action android:name="android.intent.action.SEND" />
    <category android:name="android.intent.category.DEFAULT" />
    <data android:mimeType="image/*" />
  </intent-filter>
  <intent-filter>
    <action android:name="android.intent.action.SEND_MULTIPLE" />
    <category android:name="android.intent.category.DEFAULT" />
    <data android:mimeType="image/*" />
  </intent-filter>
  <intent-filter>  <!-- PDF 는 기기에서 사진으로 바꿔 보낸다 -->
    <action android:name="android.intent.action.SEND" />
    <category android:name="android.intent.category.DEFAULT" />
    <data android:mimeType="application/pdf" />
  </intent-filter>
  <intent-filter>  <!-- 초대 링크 (커스텀 스킴) -->
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="ilgeodeurim" android:host="family" />
  </intent-filter>
  <intent-filter android:autoVerify="true">  <!-- App Links: https://{도메인}/f/… -->
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="https" android:host="${appLinkHost}" android:pathPrefix="/f/" />
  </intent-filter>
</activity>
```
- `singleTask` 여야 웜 스타트 공유가 새 화면을 겹쳐 띄우지 않는다. 카카오 콜백 스킴(`kakao…`)과 겹치지 않는지 확인.
- 서버에 `/.well-known/assetlinks.json`(패키지 + 릴리스·Play 서명 SHA-256). `appLinkHost` 는 `build.gradle` manifestPlaceholders.
- FCM: `com.google.gms.google-services` 플러그인(설정 파일이 있을 때만 적용), 기본 채널 메타데이터 `com.google.firebase.messaging.default_notification_channel_id = family`.

**iOS**
- Share Extension 타깃 `ShareExtension`(Xcode → New Target → Share Extension), `ShareViewController: RSIShareViewController`. Info.plist `NSExtensionActivationRule`: `NSExtensionActivationSupportsImageWithMaxCount = 5`, `NSExtensionActivationSupportsFileWithMaxCount = 1`(PDF). 앱과 확장 둘 다 App Group `group.com.ilgeodeurim.ilgeodeurim`, Runner Info.plist `AppGroupId`, URL 스킴 `ShareMedia-$(PRODUCT_BUNDLE_IDENTIFIER)`. 확장 배포 대상 = 앱과 같게. Runner 를 SceneDelegate 로(1.9.0 요구).
- Associated Domains `applinks:{도메인}` + 서버 `/.well-known/apple-app-site-association` (`/f/*`). URL 스킴 `ilgeodeurim` 은 이미 있음(OAuth).
- Push Notifications·Background Modes(remote-notification) capability. 문서 스캐너는 `NSCameraUsageDescription`(있음).
- Windows PC 에는 Xcode 가 없으므로 iOS 확장은 Mac 에서 만들고 확인해야 한다.

## 10. 파일별 작업 목록

### ✅ 3단계 A (끝남, 서버)
| 파일 | 내용 |
|---|---|
| `server/db/migrations/V0002__ct_family_document.sql` | 표 7개 + 색인·COMMENT |
| `server/app/family/models.py` | 위 표의 SQLAlchemy 모델 |
| `server/app/family/config.py` | `FAMILY_*` 설정 |
| `server/app/family/errors.py` | `FamilyError`(= `AuthError` 모양) |
| `server/app/family/service.py` | 초대 만들기·취소·미리 보기·수락(원자적), 맞히기 제한, 연결 목록·이름·끊기, 탈퇴 정리, 감사 |
| `server/app/family/documents.py` | 서류 보관·가져오기·동기화·권한·할 일·지우기(묘비)·나누기·대신 보내기 |
| `server/app/family/notify.py` | 푸시 문구(잠금 화면에 내용 없음, 한국어 조사) |
| `server/app/family/routes.py` | 위 API 전부 + `/f/{token}` |
| `server/app/push/` | `PushSender`, `FakePushSender`, `FcmPushSender`, 설정, `notify_user` |
| `server/app/quality.py` | 품질 지표·기준·문구 |
| `server/app/analysis.py` | `/api/analyze` 에서 떼어 낸 공통 분석(읽기→품질→AI→검증), 두 분석 경로가 같이 씀 |
| `server/app/main.py` | 가족 라우트, `save`, PATCH CORS |
| `server/app/auth/routes.py` | 탈퇴 끝에 `on_user_withdrawn` (한 줄) |
| `server/app/db.py` | 가족 모델 등록 (한 줄) |
| `server/requirements.txt`, `.env.example`, `README.md`, `.gitignore` | pillow, 새 환경변수, 푸시 켜는 법, 키 파일 제외 |

### ⬜ 3단계 B (앱 — Flutter 가 있는 PC 에서)
| 파일 | 할 일 |
|---|---|
| `app/pubspec.yaml` | `receive_sharing_intent: ^1.9.0`, `firebase_core: ^5.2.0`, `firebase_messaging: ^17.0.0`, `app_links: ^7.2.2`, `image`, `pdfrx`, (`share_plus` 초대 공유) |
| `lib/services/photo_quality.dart` (새) | §6 지표를 isolate 에서, 서버와 같은 계산. 앱 기준 상수 |
| `lib/services/capture_flow.dart` (새) | 스캐너·공유·사진첩 → 품질 → 대상 고르기 → 분석. 한 곳 |
| `lib/screens/retake_screen.dart` (새) | 다시 찍기 / 그래도 보내기, 문제별 그림 |
| `lib/widgets/illustrations.dart` | 흔들림·어두움·반사·작음·잘림 그림 |
| `lib/services/share_intake.dart` (새) | `receive_sharing_intent` 콜드·웜, `reset()`, 임시 파일 지우기, PDF→JPEG |
| `lib/services/image_source_io.dart` · `_web.dart` | `pickMultiImage(limit: 5)` |
| `lib/services/scanner.dart` | 그대로 (가져오기 끔 확인) |
| `lib/services/analysis_service.dart` | `save` 필드, `analyzeFor(linkId)`, `photo_*` 오류를 타입으로 (`PhotoQualityException(code, page)`) |
| `lib/services/family_service.dart` (새) | 초대·미리 보기·수락·목록·이름·끊기·가족 서류. `HttpFamilyService` / `MockFamilyService` |
| `lib/services/push_service.dart` (새) | `FirebasePushService` / `NoopPushService`, 토큰 등록, 누르면 이동 |
| `lib/services/deep_links.dart` (새) | `app_links`: `family/join?t=`, `/f/{token}` (기존 OAuth 콜백과 함께) |
| `lib/services/document_repository.dart` | `SyncedDocumentRepository` + 보낼 일 큐, 머지 규칙 |
| `lib/models/document_result.dart` | `source`, `sentBy`, `seen`, `access`, `ownerLabel`, `updatedAt` (+ JSON) |
| `lib/state/app_store.dart` | 가족 상태, 동기화 시점, 공유로 들어온 사진, 새 서류 표시 |
| `lib/screens/family_screen.dart`, `invite_code_screen.dart`, `join_screen.dart` (새) | §8 가족 화면 |
| `lib/screens/result_screen.dart` | '자녀가 보냄' 띠, [자녀에게 보내기] 실제 동작 |
| `lib/screens/history_screen.dart`, `home_screen.dart` | 새 서류 점, 사진첩 버튼, 자녀용 '부모님 서류' |
| `lib/screens/account_sheet.dart` | [가족 연결] 들어가기 |
| `lib/main.dart` | Firebase 초기화(실패해도 계속), 공유·링크 구독 |
| `android/…/AndroidManifest.xml`, `build.gradle` | §9 인텐트 필터, App Links, google-services(있을 때만) |
| `ios/Runner/*`, `ios/ShareExtension/*` (새) | §9 Share Extension, App Group, SceneDelegate, Associated Domains, Push |
| 서버 `/.well-known/assetlinks.json`, `/apple-app-site-association` | 배포 도메인·서명값이 정해지면 (서버 쪽 작은 일) |

## 11. 테스트

### ✅ 있는 테스트 (`server\.venv` 에서 `python -m pytest -q` — 163개 통과)
- `tests/test_quality.py`: 선명한 사진 통과(JPEG·PNG), 흐림·어두움·작음·하얀·빈 사진 잡기, 약한 흐림은 서버 통과, 못 여는 사진 건너뜀, 여러 장이면 몇 번째인지, 환경변수 기준, 엔드포인트가 **AI 를 부르지 않고** 422, 몇 번째 사진, 디버그 지표, `QUALITY_CHECK=0`, 압축 폭탄 413.
- `tests/test_family_invite.py`: 자녀가 초대·어르신이 수락(번호 띄어쓰기), 번호·토큰이 DB 에 원문으로 없음(HMAC), 미리 보기, 어르신이 초대·자녀가 링크 토큰으로 수락, 기본 역할, 한 번만, 만료, 새 초대가 예전 것 취소, 남이 취소 못 함, 자기 초대, 이미 연결(역할 거꾸로도), 맞히기 제한(사람별·IP별, 맞는 번호도 막힘), 잘못된 입력, 연결 수 한도, 탈퇴한 초대자, 양쪽 끊기·다시 연결, 남의 연결 못 건드림, 이름은 내 쪽만, 로그인 필요, `/f/` 페이지, `FAMILY_LINKED` 푸시, 감사 기록.
- `tests/test_family_documents.py`: `save` 보관·비로그인은 저장 안 함, 가져오기 중복 없음·남의 id 못 덮음·이상한 id, `since` 동기화·묘비, 남은 404 + 감사, **대신 보내기**(주인은 어르신, '큰딸' 표시, 푸시 문구에 내용 없음, seen, 자녀는 읽기만), 어르신은 대신 못 보냄, 남·끊긴 연결은 404 이고 **AI 안 부름**, 하루 한도, 나쁜 사진은 아무것도 안 남김, 푸시 토큰 없어도 보관, **자녀에게 보내기**(여러 자녀, 중복 없음, 거두기), 나누기 규칙, 지우면 나눔도 거둠, 끊으면 접근 끊김·다시 연결해도 안 살아남, 어르신 탈퇴 시 서류 삭제, 자녀 탈퇴 시 이름만 지움, **사진이 DB 파일에 없음**.
- `tests/test_push.py`: 기기마다 보내고 기록, `NO_TOKEN`·`DISABLED`, 죽은 토큰 끄기·실패해도 계속, 발송기 예외·시간 초과도 요청을 깨지 않음, FCM 서비스 계정 JWT 서명·클레임·v1 본문, 토큰 재사용, 401 재시도, 오류 코드 7가지 매핑, OAuth 실패, 서비스 계정 검사, 설정으로 고르기(파일·base64·없음·fake·none).
- 기존 92개 그대로 통과. `TEST_DATABASE_URL=postgresql://…` 로 Postgres 에서도 돌 수 있다(이 PC 에서는 SQLite 로만 돌림).

### ⬜ 3단계 B 가 더할 테스트
- 서버: (선택) Postgres 로 V0002 적용 후 전체 테스트, `assetlinks`/AASA 응답.
- 앱 `flutter test`: `photo_quality` 가 서버와 같은 값(같은 시험 사진으로 ±5%), 다시 찍기 화면(그래도 보내기 → 분석으로), `capture_flow` 세 입구가 같은 흐름, 공유 콜드·웜(가짜 스트림), `SyncedDocumentRepository` 머지·묘비·큐 재전송·오프라인, `MockFamilyService` 로 가족 화면 위젯 시험, 푸시 데이터 → 올바른 화면, `USE_MOCK` 에서 Firebase 없이 시작.
- 실제 기기: Android 13+/iOS 17+ 스캐너, 카톡·갤러리 공유(1장·여러 장·PDF), 앱 꺼진 상태에서 공유, 링크로 수락, 푸시(잠금 화면 문구 확인).

## 12. 남은 위험·주의

- **Flutter 가 이 PC 에 없다.** 앱 작업(B)은 `flutter analyze`·기기 시험이 되는 곳에서. iOS 확장은 Mac 필요.
- 맞히기 제한은 DB 감사 기록으로 센다(여러 서버여도 맞음). 로그인·refresh 요청 수 제한은 아직 없다(인증 남은 일).
- 푸시 재시도 큐가 없다. FCM 이 잠깐 실패하면 그 알림은 없지만 서류는 남고, 앱이 열릴 때 동기화로 보인다.
- `since` 동기화는 서버 시계 기준이다. 앱은 자기 시계가 아니라 응답의 `serverTime` 을 저장해야 한다.
- 서버 품질 기준은 샘플 5장과 합성 사진으로 맞췄다. 실제 어르신 사진 20~30장으로 앱·서버 기준을 다시 맞출 것(`DEBUG_USAGE=1` 응답의 `debug.quality`).
- HEIC 는 서버 Pillow 가 못 연다 → 검사를 건너뛰고 AI 에 맡긴다. 앱은 스캐너·`image_picker` 가 JPEG 로 주는지 확인(⬜).
- 웹 앱은 공유 메뉴·푸시·스캐너가 없다. 가족 화면·번호 넣기는 웹에서도 되게.
