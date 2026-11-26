-- 읽어드림 DDL — V0001 회원·소셜 로그인·세션 (PostgreSQL)
--
-- AsOne docs/sql/01_ct_member.sql 의 ct_ 회원 영역을 따른다.
--   표 접두사 ct_, PK 는 <이름>_no BIGSERIAL, 코드값 _cd, 여부 _yn BOOLEAN,
--   시각은 모두 TIMESTAMPTZ(UTC 저장, 99_utc_timestamptz.sql 과 같은 이유),
--   감사 컬럼 created_at/created_by/updated_at/updated_by, 논리삭제 deleted_yn.
-- AsOne 과 다른 점(일부러):
--   - 소셜 계정을 ct_user.oauth_provider_cd/oauth_id 한 칸이 아니라 ct_user_oauth 로 뺀다.
--     한 회원에 카카오·구글을 함께 묶을 수 있고, 이메일로 회원을 찾아 붙이지 않는다(계정 탈취 방지).
--   - ct_user_access 에 토큰 원문을 두지 않는다. refresh 는 SHA-256 해시만, access 는 jti 만 둔다.
--   - 인가 코드 흐름의 state·PKCE 를 ct_oauth_authorize 에 한 번만 쓰이게 저장한다.
-- 앱 서버는 이 파일을 db/migrate.py 로 한 번 적용한다. SQLite(개발·테스트)는 모델에서 바로 만든다.

-- ct_user: 회원
CREATE TABLE IF NOT EXISTS ct_user (
    user_no BIGSERIAL PRIMARY KEY,
    user_type_cd VARCHAR(20) NOT NULL DEFAULT 'SENIOR',
    user_grade_cd VARCHAR(20) NOT NULL DEFAULT 'MEMBER',
    email VARCHAR(100),
    name VARCHAR(50),
    mobile_phone VARCHAR(20),
    birth_date DATE,
    gender_cd VARCHAR(10),
    profile_image_url VARCHAR(500),
    status_cd VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    status_reason VARCHAR(500),
    status_changed_at TIMESTAMPTZ,
    suspend_until TIMESTAMPTZ,
    withdraw_at TIMESTAMPTZ,
    withdraw_type_cd VARCHAR(20),
    join_channel_cd VARCHAR(30),
    last_login_at TIMESTAMPTZ,
    last_login_provider_cd VARCHAR(20),
    last_login_client_cd VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by BIGINT,
    deleted_yn BOOLEAN NOT NULL DEFAULT FALSE
);
COMMENT ON TABLE ct_user IS '회원';
COMMENT ON COLUMN ct_user.user_no IS '회원 고유번호 (PK, 자동증가)';
COMMENT ON COLUMN ct_user.user_type_cd IS '회원 유형 (SENIOR:어르신 / CHILD:자녀) — 가족 연결 기능에서 쓴다';
COMMENT ON COLUMN ct_user.user_grade_cd IS '사용자 등급 (MEMBER:회원 / ADMIN:어드민) — AsOne UserType 과 같은 뜻';
COMMENT ON COLUMN ct_user.email IS '회원 이메일 (소셜 제공자가 확인해 준 경우만). 회원을 찾는 키로 쓰지 않는다';
COMMENT ON COLUMN ct_user.name IS '표시 이름 (소셜 닉네임)';
COMMENT ON COLUMN ct_user.mobile_phone IS '휴대폰 번호';
COMMENT ON COLUMN ct_user.birth_date IS '생년월일';
COMMENT ON COLUMN ct_user.gender_cd IS '성별 코드 (MALE/FEMALE)';
COMMENT ON COLUMN ct_user.profile_image_url IS '프로필 사진 주소 (소셜 제공자)';
COMMENT ON COLUMN ct_user.status_cd IS '회원상태 (ACTIVE:정상 / SUSPEND:정지 / WITHDRAW:탈퇴)';
COMMENT ON COLUMN ct_user.status_reason IS '상태 변경 사유';
COMMENT ON COLUMN ct_user.status_changed_at IS '상태 최종 변경일시';
COMMENT ON COLUMN ct_user.suspend_until IS '정지 해제일시 (NULL=무기한/해당없음)';
COMMENT ON COLUMN ct_user.withdraw_at IS '탈퇴 처리일시';
COMMENT ON COLUMN ct_user.withdraw_type_cd IS '탈퇴유형 (SELF:자진 / FORCE:강제)';
COMMENT ON COLUMN ct_user.join_channel_cd IS '가입 경로 (KAKAO/GOOGLE)';
COMMENT ON COLUMN ct_user.last_login_at IS '최종 로그인 일시';
COMMENT ON COLUMN ct_user.last_login_provider_cd IS '최종 로그인 제공자 (KAKAO/GOOGLE)';
COMMENT ON COLUMN ct_user.last_login_client_cd IS '최종 로그인 클라이언트 (APP/WEB)';
COMMENT ON COLUMN ct_user.created_at IS '등록일시';
COMMENT ON COLUMN ct_user.created_by IS '등록자 회원번호';
COMMENT ON COLUMN ct_user.updated_at IS '수정일시';
COMMENT ON COLUMN ct_user.updated_by IS '수정자 회원번호';
COMMENT ON COLUMN ct_user.deleted_yn IS '논리삭제 여부 (true=삭제, 탈퇴 시 개인정보는 지운다)';

-- ct_user_oauth: 소셜 계정 연결
CREATE TABLE IF NOT EXISTS ct_user_oauth (
    oauth_no BIGSERIAL PRIMARY KEY,
    user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    oauth_provider_cd VARCHAR(20) NOT NULL,
    oauth_id VARCHAR(100),
    oauth_email VARCHAR(100),
    oauth_email_verified_yn BOOLEAN NOT NULL DEFAULT FALSE,
    oauth_name VARCHAR(100),
    oauth_picture VARCHAR(500),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    unlinked_at TIMESTAMPTZ,
    unlink_result_cd VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_yn BOOLEAN NOT NULL DEFAULT FALSE
);
COMMENT ON TABLE ct_user_oauth IS '소셜 계정 연결 (회원 1 : 제공자별 1)';
COMMENT ON COLUMN ct_user_oauth.oauth_no IS '연결 고유번호 (PK)';
COMMENT ON COLUMN ct_user_oauth.user_no IS '회원번호 (ct_user.user_no)';
COMMENT ON COLUMN ct_user_oauth.oauth_provider_cd IS '소셜 제공자 (KAKAO/GOOGLE)';
COMMENT ON COLUMN ct_user_oauth.oauth_id IS '제공자측 회원 고유 ID (카카오 회원번호, 구글 sub). 탈퇴 시 NULL';
COMMENT ON COLUMN ct_user_oauth.oauth_email IS '제공자가 준 이메일';
COMMENT ON COLUMN ct_user_oauth.oauth_email_verified_yn IS '제공자가 이메일을 확인했는지';
COMMENT ON COLUMN ct_user_oauth.oauth_name IS '제공자 닉네임';
COMMENT ON COLUMN ct_user_oauth.oauth_picture IS '제공자 프로필 사진 주소';
COMMENT ON COLUMN ct_user_oauth.linked_at IS '연결일시';
COMMENT ON COLUMN ct_user_oauth.last_login_at IS '이 계정으로 마지막 로그인한 일시';
COMMENT ON COLUMN ct_user_oauth.unlinked_at IS '연결 해제일시 (탈퇴)';
COMMENT ON COLUMN ct_user_oauth.unlink_result_cd IS '제공자 연결 끊기 결과 (OK/FAILED/SKIPPED)';
COMMENT ON COLUMN ct_user_oauth.created_at IS '등록일시';
COMMENT ON COLUMN ct_user_oauth.updated_at IS '수정일시';
COMMENT ON COLUMN ct_user_oauth.deleted_yn IS '논리삭제 여부';
-- 살아 있는 연결 안에서만 유일하다. 탈퇴한 뒤 같은 카카오 계정으로 다시 가입할 수 있어야 한다.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_user_oauth_provider_id
    ON ct_user_oauth (oauth_provider_cd, oauth_id) WHERE deleted_yn = FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_user_oauth_user_provider
    ON ct_user_oauth (user_no, oauth_provider_cd) WHERE deleted_yn = FALSE;

-- ct_user_access: 로그인 세션·토큰 (refresh 회전 사슬)
CREATE TABLE IF NOT EXISTS ct_user_access (
    access_no BIGSERIAL PRIMARY KEY,
    user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    client_type_cd VARCHAR(20) NOT NULL DEFAULT 'APP',
    token_family VARCHAR(64) NOT NULL,
    parent_access_no BIGINT,
    access_jti VARCHAR(64) NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL,
    login_provider_cd VARCHAR(20),
    device_id VARCHAR(100),
    device_os VARCHAR(30),
    user_agent VARCHAR(500),
    ip_address VARCHAR(50),
    auth_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    refresh_expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    revoked_yn BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    revoke_reason_cd VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_user_access IS '로그인 토큰 (refresh 한 번 쓸 때마다 새 행, 같은 token_family 로 이어진다)';
COMMENT ON COLUMN ct_user_access.access_no IS '토큰 이력 고유번호 (PK)';
COMMENT ON COLUMN ct_user_access.user_no IS '회원번호 (ct_user.user_no)';
COMMENT ON COLUMN ct_user_access.client_type_cd IS '클라이언트 유형 (APP/WEB)';
COMMENT ON COLUMN ct_user_access.token_family IS '세션(회전 사슬) ID. access JWT 의 sid';
COMMENT ON COLUMN ct_user_access.parent_access_no IS '이 토큰을 낳은 이전 행 (회전)';
COMMENT ON COLUMN ct_user_access.access_jti IS '같이 낸 access JWT 의 jti (토큰 원문은 두지 않는다)';
COMMENT ON COLUMN ct_user_access.refresh_token_hash IS 'refresh 토큰 SHA-256 (hex). 원문은 두지 않는다';
COMMENT ON COLUMN ct_user_access.login_provider_cd IS '로그인한 제공자 (KAKAO/GOOGLE)';
COMMENT ON COLUMN ct_user_access.device_id IS '디바이스 식별자 (앱 설치 ID)';
COMMENT ON COLUMN ct_user_access.device_os IS '디바이스 OS (ANDROID/IOS/WEB)';
COMMENT ON COLUMN ct_user_access.user_agent IS 'User-Agent 문자열';
COMMENT ON COLUMN ct_user_access.ip_address IS '발급 시점 IP 주소';
COMMENT ON COLUMN ct_user_access.auth_at IS '처음 소셜 로그인한 시각 (회전해도 그대로, 세션 최대 수명 기준)';
COMMENT ON COLUMN ct_user_access.expires_at IS 'Access 토큰 만료일시';
COMMENT ON COLUMN ct_user_access.refresh_expires_at IS 'Refresh 토큰 만료일시';
COMMENT ON COLUMN ct_user_access.used_at IS 'refresh 로 한 번 쓰인 시각 (다시 오면 재사용 = 탈취 의심)';
COMMENT ON COLUMN ct_user_access.revoked_yn IS '토큰 폐기 여부 (로그아웃/탈퇴/재사용 탐지)';
COMMENT ON COLUMN ct_user_access.revoked_at IS '폐기일시';
COMMENT ON COLUMN ct_user_access.revoke_reason_cd IS '폐기 사유 (LOGOUT/LOGOUT_ALL/REUSE_DETECTED/WITHDRAW/SESSION_LIMIT/USER_INACTIVE/CODE_REPLAY)';
COMMENT ON COLUMN ct_user_access.created_at IS '토큰 발급일시';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_user_access_refresh_hash ON ct_user_access (refresh_token_hash);
CREATE INDEX IF NOT EXISTS ix_ct_user_access_family ON ct_user_access (token_family);
CREATE INDEX IF NOT EXISTS ix_ct_user_access_user ON ct_user_access (user_no, created_at);

-- ct_user_login_log: 로그인·접속 이력 (AsOne ct_admin_login_log 를 회원용으로)
CREATE TABLE IF NOT EXISTS ct_user_login_log (
    login_log_no BIGSERIAL PRIMARY KEY,
    user_no BIGINT,
    event_cd VARCHAR(30) NOT NULL,
    oauth_provider_cd VARCHAR(20),
    client_type_cd VARCHAR(20),
    device_id VARCHAR(100),
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    success_yn BOOLEAN NOT NULL DEFAULT FALSE,
    fail_reason VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_user_login_log IS '회원 로그인·접속 이력';
COMMENT ON COLUMN ct_user_login_log.login_log_no IS '로그 고유번호 (PK)';
COMMENT ON COLUMN ct_user_login_log.user_no IS '회원번호 (실패해서 모르면 NULL)';
COMMENT ON COLUMN ct_user_login_log.event_cd IS '이벤트 (LOGIN/LOGIN_FAIL/SIGNUP/REFRESH/REFRESH_FAIL/REUSE_DETECTED/LOGOUT/LOGOUT_ALL/WITHDRAW)';
COMMENT ON COLUMN ct_user_login_log.oauth_provider_cd IS '소셜 제공자';
COMMENT ON COLUMN ct_user_login_log.client_type_cd IS '클라이언트 유형 (APP/WEB)';
COMMENT ON COLUMN ct_user_login_log.device_id IS '디바이스 식별자';
COMMENT ON COLUMN ct_user_login_log.ip_address IS '요청 IP';
COMMENT ON COLUMN ct_user_login_log.user_agent IS 'User-Agent';
COMMENT ON COLUMN ct_user_login_log.success_yn IS '성공 여부';
COMMENT ON COLUMN ct_user_login_log.fail_reason IS '실패 사유 코드 (토큰·개인정보는 남기지 않는다)';
COMMENT ON COLUMN ct_user_login_log.created_at IS '발생일시';
CREATE INDEX IF NOT EXISTS ix_ct_user_login_log_user ON ct_user_login_log (user_no, created_at);

-- ct_user_push_token: 푸시 토큰 (AsOne 실제 표 7컬럼 + device_id, A1 유니크 포함)
CREATE TABLE IF NOT EXISTS ct_user_push_token (
    push_token_no BIGSERIAL PRIMARY KEY,
    user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    push_token VARCHAR(500) NOT NULL,
    platform_cd VARCHAR(20),
    device_id VARCHAR(100),
    active_yn BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_user_push_token IS '푸시 토큰';
COMMENT ON COLUMN ct_user_push_token.push_token_no IS '푸시토큰 고유번호 (PK)';
COMMENT ON COLUMN ct_user_push_token.user_no IS '회원번호 (ct_user.user_no)';
COMMENT ON COLUMN ct_user_push_token.push_token IS 'FCM/APNs 푸시 토큰 문자열';
COMMENT ON COLUMN ct_user_push_token.platform_cd IS '플랫폼 코드 (ANDROID/IOS/WEB, 대문자로 저장)';
COMMENT ON COLUMN ct_user_push_token.device_id IS '디바이스 식별자';
COMMENT ON COLUMN ct_user_push_token.active_yn IS '토큰 사용 가능 여부 (로그아웃·탈퇴·FCM 무효면 FALSE)';
COMMENT ON COLUMN ct_user_push_token.created_at IS '등록일시';
COMMENT ON COLUMN ct_user_push_token.updated_at IS '수정일시';
-- A1_push_token_unique.sql 과 같다. 앱이 켤 때마다 보내도 행이 쌓이지 않게 ON CONFLICT 로 등록한다.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_user_push_token_user_token
    ON ct_user_push_token (user_no, push_token);

-- ct_oauth_authorize: 서버 인가 코드 흐름 (state·PKCE·앱에 넘길 1회용 코드)
CREATE TABLE IF NOT EXISTS ct_oauth_authorize (
    authorize_no BIGSERIAL PRIMARY KEY,
    oauth_provider_cd VARCHAR(20) NOT NULL,
    state_hash CHAR(64) NOT NULL,
    provider_code_verifier VARCHAR(128) NOT NULL,
    nonce VARCHAR(64),
    app_redirect_uri VARCHAR(500) NOT NULL,
    app_state VARCHAR(200),
    app_code_challenge VARCHAR(128) NOT NULL,
    user_type_cd VARCHAR(20),
    device_id VARCHAR(100),
    expires_at TIMESTAMPTZ NOT NULL,
    callback_at TIMESTAMPTZ,
    user_no BIGINT,
    is_new_user_yn BOOLEAN NOT NULL DEFAULT FALSE,
    login_code_hash CHAR(64),
    login_code_expires_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    issued_token_family VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_oauth_authorize IS '소셜 인가 요청 (한 번만 쓰인다)';
COMMENT ON COLUMN ct_oauth_authorize.authorize_no IS '인가 요청 고유번호 (PK)';
COMMENT ON COLUMN ct_oauth_authorize.oauth_provider_cd IS '소셜 제공자 (KAKAO/GOOGLE)';
COMMENT ON COLUMN ct_oauth_authorize.state_hash IS '제공자에 보낸 state 의 SHA-256 (원문은 두지 않는다)';
COMMENT ON COLUMN ct_oauth_authorize.provider_code_verifier IS '제공자용 PKCE code_verifier (10분 뒤 쓸모없음)';
COMMENT ON COLUMN ct_oauth_authorize.nonce IS 'OIDC nonce (구글 ID 토큰에 그대로 돌아와야 한다)';
COMMENT ON COLUMN ct_oauth_authorize.app_redirect_uri IS '로그인 뒤 돌아갈 앱 주소 (허용 목록에 있는 것만)';
COMMENT ON COLUMN ct_oauth_authorize.app_state IS '앱이 보낸 state (그대로 돌려준다)';
COMMENT ON COLUMN ct_oauth_authorize.app_code_challenge IS '앱 PKCE code_challenge (S256). /api/auth/token 에서 확인';
COMMENT ON COLUMN ct_oauth_authorize.user_type_cd IS '새로 가입할 때 쓸 회원 유형';
COMMENT ON COLUMN ct_oauth_authorize.device_id IS '디바이스 식별자';
COMMENT ON COLUMN ct_oauth_authorize.expires_at IS 'state 만료일시';
COMMENT ON COLUMN ct_oauth_authorize.callback_at IS '제공자 콜백을 받은 일시 (state 사용 완료)';
COMMENT ON COLUMN ct_oauth_authorize.user_no IS '로그인된 회원번호';
COMMENT ON COLUMN ct_oauth_authorize.is_new_user_yn IS '이번에 새로 가입했는지';
COMMENT ON COLUMN ct_oauth_authorize.login_code_hash IS '앱에 넘긴 1회용 로그인 코드 SHA-256';
COMMENT ON COLUMN ct_oauth_authorize.login_code_expires_at IS '로그인 코드 만료일시';
COMMENT ON COLUMN ct_oauth_authorize.consumed_at IS '로그인 코드를 토큰으로 바꾼 일시';
COMMENT ON COLUMN ct_oauth_authorize.issued_token_family IS '로그인 코드로 낸 세션 (코드 재사용 시 폐기)';
COMMENT ON COLUMN ct_oauth_authorize.created_at IS '등록일시';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_oauth_authorize_state ON ct_oauth_authorize (state_hash);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_oauth_authorize_login_code ON ct_oauth_authorize (login_code_hash);
