# 읽다 API 계약

서버 API 엔드포인트 및 요청/응답 형식입니다.

## 목차

- [공통 규칙](#공통-규칙)
- [분석 API](#분석-api)
- [인증 API](#인증-api)
- [사용자 API](#사용자-api)
- [가족 연결 API](#가족-연결-api)
- [서류 API](#서류-api)
- [초대 링크 웹 페이지](#초대-링크-웹-페이지)

---

## 공통 규칙

### 인증

Bearer 토큰이 필요한 엔드포인트는 헤더에 포함:

```
Authorization: Bearer eyJ...
```

### 오류 응답

모든 오류는 다음 형식으로 반환됩니다:

```json
{
  "error": {
    "code": "refresh_expired",
    "userMessage": "다시 로그인해 주세요."
  }
}
```

- `code`: 기계 가독 오류 코드
- `userMessage`: 사용자에게 그대로 보여줄 수 있는 한국어 메시지

### 캐싱

토큰 응답은 `Cache-Control: no-store`

### 시각 형식

모든 시각은 UTC ISO 8601 형식:

```
"2026-11-17T03:00:00Z"
```

---

## 분석 API

### `POST /api/analyze`

서류 사진을 업로드하여 AI 분석 결과를 받습니다.

#### 요청

**Content-Type**: `multipart/form-data`

**필드**:
- `images`: 사진 파일 (여러 장이면 같은 이름으로 여러 번, 최대 5장)
- `save` (선택): `true`면 로그인한 사용자의 서류로 보관

**예시**:
```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "images=@bill.jpg;type=image/jpeg" \
  -F "save=true" \
  -H "Authorization: Bearer eyJ..."
```

#### 응답 (200 OK)

```json
{
  "id": "doc_ab12cd34ef56...",
  "docType": "bill",
  "title": "한국전력 전기요금 고지서",
  "oneLiner": "이번 달 전기요금 32,400원을 11월 25일까지 내시면 돼요.",
  "amount": 32400,
  "dueDate": "2026-11-25",
  "todos": [
    {
      "id": "t_123456",
      "title": "전기요금 내기",
      "dueDate": "2026-11-25",
      "detail": "은행, 편의점, 인터넷뱅킹에서 낼 수 있어요."
    }
  ],
  "warnings": [
    "기한이 지나면 연체료가 붙어요."
  ],
  "details": [
    "청구 금액: 32,400원",
    "사용량: 285kWh",
    "고객번호: 1234-5678-9012"
  ],
  "model": "gemini:gemini-3.6-flash",
  "saved": true,
  "source": "SELF",
  "seen": false,
  "access": "OWNER",
  "sentBy": null,
  "owner": null,
  "createdAt": "2026-11-17T03:00:00Z",
  "updatedAt": "2026-11-17T03:00:00Z"
}
```

**필드**:
- `docType`: `bill` | `medicine` | `hospital` | `contract` | `government` | `other`
- `amount`: 금액 (원 단위 정수, 없으면 `null`)
- `dueDate`: 대표 기한 (ISO 날짜, 없으면 `null`)
- `saved`: `true`면 서버에 보관됨
- `source`: `SELF` | `FAMILY` | `IMPORT`
- `access`: `OWNER` | `FAMILY`

#### 오류

- **400**: `no_images` (사진 없음), `too_many_images` (5장 초과)
- **413**: `image_too_large` (사진이 너무 큼)
- **415**: `invalid_image` (사진 형식 아님)
- **422**: 품질 문제
  - `photo_blurry` (흐림)
  - `photo_dark` (어두움)
  - `photo_bright` (과노출)
  - `photo_blank` (빈 사진)
  - `photo_small` (너무 작음)
  
  응답 예시:
  ```json
  {
    "error": {
      "code": "photo_blurry",
      "userMessage": "2번째 사진: 사진이 흔들렸어요. 다시 찍어 주세요.",
      "page": 2,
      "problems": ["흔들림이 감지됐어요"]
    }
  }
  ```

- **502**: `ai_error` (AI 서비스 오류)

---

## 인증 API

### `POST /api/auth/kakao`

카카오 SDK 토큰으로 로그인합니다.

#### 요청

```json
{
  "accessToken": "카카오_액세스_토큰",
  "deviceId": "기기_고유_ID",
  "deviceOs": "ANDROID",
  "userType": "SENIOR"
}
```

**필드**:
- `accessToken` (필수)
- `deviceId` (선택, 최대 100자)
- `deviceOs` (선택): `ANDROID` | `IOS` | `WEB`
- `userType` (선택): `SENIOR` | `CHILD` (첫 가입 시에만 적용)

#### 응답 (200 OK)

```json
{
  "tokenType": "Bearer",
  "accessToken": "eyJ...",
  "accessTokenExpiresIn": 900,
  "refreshToken": "Q2x...",
  "refreshTokenExpiresIn": 5184000,
  "isNewUser": true,
  "user": {
    "userNo": 42,
    "userType": "SENIOR",
    "name": "박영감",
    "email": null,
    "profileImageUrl": "https://...",
    "providers": ["KAKAO"]
  }
}
```

#### 오류

- **400**: `token_missing`
- **401**: `kakao_token_invalid`, `kakao_app_mismatch`, `kakao_id_mismatch`
- **403**: `user_inactive` (정지 또는 탈퇴)
- **502**: `kakao_unavailable`
- **503**: `kakao_not_configured` (서버 설정 없음)

### `POST /api/auth/google`

구글 ID 토큰으로 로그인합니다.

#### 요청

```json
{
  "idToken": "구글_ID_토큰",
  "deviceId": "기기_고유_ID",
  "deviceOs": "ANDROID",
  "userType": "SENIOR"
}
```

#### 응답

카카오 로그인과 동일한 토큰 응답

#### 오류

- **400**: `token_missing`
- **401**: `id_token_*` (다양한 ID 토큰 오류)
- **403**: `user_inactive`
- **503**: `google_not_configured`, `jwks_unavailable`

### `POST /api/auth/refresh`

Refresh 토큰으로 새 토큰 쌍을 발급받습니다.

#### 요청

```json
{
  "refreshToken": "현재_리프레시_토큰",
  "deviceId": "기기_고유_ID"
}
```

#### 응답 (200 OK)

```json
{
  "tokenType": "Bearer",
  "accessToken": "eyJ...",
  "accessTokenExpiresIn": 900,
  "refreshToken": "새로운_리프레시_토큰",
  "refreshTokenExpiresIn": 5184000,
  "user": { /* 사용자 정보 */ }
}
```

> **주의**: `isNewUser`는 refresh 응답에 없습니다.

#### 오류

- **401**: 
  - `invalid_refresh` (잘못된 토큰)
  - `refresh_revoked` (폐기된 토큰)
  - `refresh_superseded` (다른 기기에서 이미 갱신됨, 잠시 후 재시도)
  - `refresh_reused` (재사용 감지, 세션 전체 폐기됨, 다시 로그인 필요)
  - `refresh_expired` (만료)
  - `user_inactive`

### `POST /api/auth/logout`

로그아웃합니다. Bearer 토큰은 선택입니다.

#### 요청

```json
{
  "refreshToken": "현재_리프레시_토큰",
  "allDevices": false,
  "deviceId": "기기_고유_ID"
}
```

**필드**:
- `refreshToken` (선택): 있으면 해당 세션 폐기
- `allDevices`: `true`면 모든 기기에서 로그아웃 (Bearer 필수)
- `deviceId` (선택): 푸시 토큰 비활성화

#### 응답

```
204 No Content
```

---

## 사용자 API

### `GET /api/me`

현재 로그인한 사용자 정보를 가져옵니다.

**인증**: Bearer 필수

#### 응답 (200 OK)

```json
{
  "userNo": 42,
  "userType": "SENIOR",
  "name": "박영감",
  "email": null,
  "profileImageUrl": "https://...",
  "providers": ["KAKAO"],
  "createdAt": "2026-11-01T00:00:00Z"
}
```

### `DELETE /api/me`

회원 탈퇴합니다.

**인증**: Bearer 필수

#### 요청 (선택)

```json
{
  "kakaoAccessToken": "카카오_액세스_토큰"
}
```

**필드**:
- `kakaoAccessToken`: 서버에 어드민 키가 없을 때 카카오 연결 끊기에 사용

#### 응답 (200 OK)

```json
{
  "ok": true,
  "unlinked": {
    "KAKAO": "OK",
    "GOOGLE": "SKIPPED"
  }
}
```

**unlinked 값**:
- `OK`: 연결 끊기 성공
- `FAILED`: 실패 (탈퇴는 계속 진행됨)
- `SKIPPED`: 토큰 없음

> **주의**: 구글 연결은 앱에서 `GoogleSignIn.disconnect()`를 호출해야 합니다.

### `POST /api/me/push-token`

푸시 알림 토큰을 등록하거나 갱신합니다.

**인증**: Bearer 필수

#### 요청

```json
{
  "pushToken": "FCM_또는_APNs_토큰",
  "platform": "ANDROID",
  "deviceId": "기기_고유_ID"
}
```

**필드**:
- `pushToken` (필수, 최대 500자)
- `platform` (선택): `ANDROID` | `IOS` | `WEB`
- `deviceId` (선택)

#### 응답

```
204 No Content
```

---

## 가족 연결 API

### `POST /api/family/invites`

가족 초대를 만듭니다.

**인증**: Bearer 필수

#### 요청

```json
{
  "myRole": "CHILD",
  "label": "엄마"
}
```

**필드**:
- `myRole` (선택): `SENIOR` | `CHILD` (기본값은 사용자의 `userType`)
- `label` (선택): 초대받는 사람을 부를 이름

#### 응답 (201 Created)

```json
{
  "inviteId": 123,
  "code": "123456",
  "myRole": "CHILD",
  "expiresAt": "2026-11-17T03:30:00Z",
  "expiresInSeconds": 1800,
  "appLink": "ilgeodeurim://family/join?t=abc...",
  "webLink": "https://api.example.com/f/abc...",
  "shareText": "읽다 앱으로 연결해요!\n\n초대 번호: 123 456\n또는 이 링크를 눌러 주세요: https://..."
}
```

> 같은 사람의 새 초대는 이전 초대를 자동으로 취소합니다.

### `POST /api/family/invites/preview`

초대 번호 또는 링크 토큰으로 초대한 사람을 미리 봅니다.

**인증**: Bearer 필수

#### 요청

```json
{
  "code": "123456"
}
```

또는

```json
{
  "token": "링크_토큰"
}
```

#### 응답 (200 OK)

```json
{
  "inviter": {
    "name": "김자녀",
    "profileImageUrl": "https://..."
  },
  "inviterRole": "CHILD",
  "yourRole": "SENIOR",
  "expiresAt": "2026-11-17T03:30:00Z",
  "alreadyLinked": false
}
```

#### 오류

- **400**: `invite_missing` (code 또는 token 없음), `invite_self` (자기 초대)
- **404**: `invite_invalid` (만료, 취소, 또는 이미 사용됨)
- **429**: `too_many_attempts` (맞히기 횟수 초과)

### `POST /api/family/invites/accept`

초대를 수락하고 가족 연결을 만듭니다.

**인증**: Bearer 필수

#### 요청

```json
{
  "code": "123456",
  "label": "큰딸"
}
```

또는

```json
{
  "token": "링크_토큰",
  "label": "큰딸"
}
```

**필드**:
- `label` (선택): 상대방을 부를 이름 (없으면 "부모님" 또는 "자녀")

#### 응답 (200 OK)

```json
{
  "link": {
    "linkId": 456,
    "myRole": "SENIOR",
    "member": {
      "role": "CHILD",
      "name": "김자녀",
      "label": "큰딸",
      "profileImageUrl": "https://..."
    },
    "linkedAt": "2026-11-17T03:00:00Z"
  }
}
```

#### 오류

- **400**, **404**, **429**: preview와 동일
- **409**: `already_linked` (이미 연결됨), `family_limit` (최대 연결 수 초과)

### `DELETE /api/family/invites/{inviteId}`

자신이 만든 초대를 취소합니다.

**인증**: Bearer 필수

#### 응답

```
204 No Content
```

#### 오류

- **404**: `invite_invalid` (남의 초대 또는 이미 끝난 초대)

### `GET /api/family`

내 가족 연결 목록과 대기 중인 초대를 가져옵니다.

**인증**: Bearer 필수

#### 응답 (200 OK)

```json
{
  "links": [
    {
      "linkId": 456,
      "myRole": "CHILD",
      "member": {
        "role": "SENIOR",
        "name": "박영감",
        "label": "아버지",
        "profileImageUrl": "https://..."
      },
      "linkedAt": "2026-11-01T00:00:00Z"
    }
  ],
  "pendingInvite": {
    "inviteId": 789,
    "myRole": "CHILD",
    "expiresAt": "2026-11-17T03:30:00Z"
  }
}
```

**필드**:
- `pendingInvite`: 현재 대기 중인 초대 (없으면 `null`)

### `PATCH /api/family/links/{linkId}`

연결에서 상대방을 부르는 이름을 변경합니다.

**인증**: Bearer 필수

#### 요청

```json
{
  "label": "새로운_이름"
}
```

#### 응답 (200 OK)

```json
{
  "link": { /* 업데이트된 연결 정보 */ }
}
```

### `DELETE /api/family/links/{linkId}`

가족 연결을 끊습니다. 어느 쪽에서든 끊을 수 있습니다.

**인증**: Bearer 필수

#### 응답

```
204 No Content
```

### `POST /api/family/links/{linkId}/analyze`

자녀가 어르신 대신 서류를 찍어 보냅니다.

**인증**: Bearer 필수 (자녀 계정만 가능)

#### 요청

**Content-Type**: `multipart/form-data`

**필드**:
- `images`: 사진 파일 (최대 5장)

#### 응답 (201 Created)

```json
{
  "id": "doc_xyz...",
  "docType": "bill",
  "title": "...",
  /* ... 분석 결과 ... */
  "source": "FAMILY",
  "sentBy": {
    "linkId": 456,
    "label": "큰딸"
  },
  "owner": {
    "label": "아버지"
  },
  "seen": false,
  "access": "FAMILY",
  "pushed": 2
}
```

**필드**:
- `pushed`: 푸시를 보낸 기기 수

#### 오류

- **403**: `not_child` (자녀만 가능)
- **404**: `link_not_found` (연결 없음 또는 끊김)
- **429**: `send_limit` (하루 한도 초과)
- 품질 오류는 `/api/analyze`와 동일

### `GET /api/family/documents`

자녀 화면: 보냈거나 나눠 받은 서류 목록입니다.

**인증**: Bearer 필수

#### 응답 (200 OK)

```json
{
  "documents": [
    {
      "id": "doc_...",
      "docType": "bill",
      "title": "...",
      /* ... */
      "source": "FAMILY",
      "sentBy": {
        "linkId": 456,
        "label": "나"
      },
      "owner": {
        "label": "아버지"
      },
      "seen": true,
      "access": "FAMILY"
    }
  ]
}
```

---

## 서류 API

### `GET /api/documents`

내 서류 목록을 가져옵니다.

**인증**: Bearer 필수

#### 쿼리 파라미터

- `since` (선택): ISO 시각, 이 시각 이후 업데이트된 서류만 (동기화용)

#### 응답 (200 OK)

```json
{
  "documents": [
    {
      "id": "doc_...",
      "docType": "bill",
      "title": "...",
      "oneLiner": "...",
      "amount": 32400,
      "dueDate": "2026-11-25",
      "todos": [ /* ... */ ],
      "warnings": [ /* ... */ ],
      "details": [ /* ... */ ],
      "model": "gemini:gemini-3.6-flash",
      "createdAt": "2026-11-17T03:00:00Z",
      "updatedAt": "2026-11-17T03:00:00Z",
      "source": "SELF",
      "sentBy": null,
      "seen": true,
      "access": "OWNER"
    }
  ],
  "deleted": ["doc_abc...", "doc_def..."],
  "serverTime": "2026-11-17T05:00:00Z"
}
```

**필드**:
- `deleted`: 삭제된 서류 ID 목록 (동기화용)
- `serverTime`: 다음 동기화 때 `since`로 사용할 시각

### `POST /api/documents`

기기에 저장된 서류를 서버에 올립니다.

**인증**: Bearer 필수

#### 요청

```json
{
  "id": "doc_...",
  "docType": "bill",
  "title": "...",
  "oneLiner": "...",
  "amount": 32400,
  "dueDate": "2026-11-25",
  "todos": [
    {
      "id": "t_...",
      "title": "...",
      "dueDate": "2026-11-25",
      "detail": "...",
      "done": false,
      "remind": true
    }
  ],
  "warnings": [],
  "details": [],
  "model": "gemini:gemini-3.6-flash",
  "createdAt": "2026-11-17T03:00:00Z"
}
```

#### 응답

- **201 Created**: 새로 생성됨
- **200 OK**: 같은 주인의 같은 ID가 이미 존재 (업데이트 안 함)

> 남의 ID와 겹치면 새 ID를 발급합니다.

### `GET /api/documents/{id}`

서류 하나를 가져옵니다.

**인증**: Bearer 필수

#### 응답 (200 OK)

서류 JSON (위와 동일)

#### 오류

- **404**: `document_not_found` (없거나 볼 권한 없음)

### `DELETE /api/documents/{id}`

서류를 삭제합니다.

**인증**: Bearer 필수 (주인만 가능)

#### 응답

```
204 No Content
```

> 실제로는 내용만 지우고 ID를 남겨 둡니다 (묘비). 다른 기기가 동기화할 때 `deleted` 목록으로 알 수 있습니다.

#### 오류

- **403**: `owner_only`
- **404**: `document_not_found`

### `PATCH /api/documents/{id}/todos/{todoId}`

할 일의 완료 또는 알림 상태를 변경합니다.

**인증**: Bearer 필수 (주인 또는 편집 권한 있는 가족)

#### 요청

```json
{
  "done": true,
  "remind": false
}
```

**필드**: 둘 다 선택

#### 응답 (200 OK)

업데이트된 할 일 JSON

#### 오류

- **403**: `owner_only` (편집 권한 없음)
- **404**: `todo_not_found`

### `POST /api/documents/{id}/seen`

서류를 열어봤음을 기록합니다.

**인증**: Bearer 필수 (주인만)

#### 응답

```
204 No Content
```

### `POST /api/documents/{id}/shares`

어르신이 자녀에게 서류를 나눕니다.

**인증**: Bearer 필수 (어르신 역할만)

#### 요청

```json
{
  "linkIds": [456, 789]
}
```

**필드**:
- `linkIds` (선택): 나눌 가족 연결 ID 목록 (없으면 모든 자녀에게)

#### 응답 (200 OK)

```json
{
  "sharedTo": [
    {
      "linkId": 456,
      "label": "큰딸",
      "new": true,
      "pushed": 1
    },
    {
      "linkId": 789,
      "label": "작은딸",
      "new": false,
      "pushed": 0
    }
  ]
}
```

**필드**:
- `new`: `true`면 이번에 새로 나눔, `false`면 이미 나눈 것
- `pushed`: 푸시를 보낸 기기 수

#### 오류

- **403**: `not_senior` (어르신 역할 아님), `owner_only`
- **404**: `document_not_found`
- **409**: `no_family` (연결된 가족 없음)

### `DELETE /api/documents/{id}/shares/{linkId}`

나눔을 거둡니다.

**인증**: Bearer 필수 (어르신 역할만)

#### 응답

```
204 No Content
```

---

## 초대 링크 웹 페이지

### `GET /f/{token}`

가족 초대 링크를 웹에서 열었을 때 보이는 페이지입니다.

#### 응답 (200 OK)

HTML 페이지:
- **앱이 설치된 경우**: App Links/Universal Links로 자동으로 앱이 열림
- **앱이 없는 경우**: "앱에서 열기" 버튼 (`ilgeodeurim://family/join?t={token}`)

#### 헤더

```
Content-Security-Policy: default-src 'self'
Cache-Control: no-store
Referrer-Policy: no-referrer
X-Robots-Tag: noindex
```

#### 오류

- **404**: 형식이 잘못된 토큰
