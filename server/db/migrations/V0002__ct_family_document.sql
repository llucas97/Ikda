-- 읽어드림 DDL — V0002 가족 연결·서류 보관·푸시 기록 (PostgreSQL)
--
-- V0001 과 같은 규칙: 접두사 ct_, PK <이름>_no BIGSERIAL, 코드값 _cd, 여부 _yn, 시각 TIMESTAMPTZ(UTC),
-- 감사 컬럼 created_at/created_by/updated_at/updated_by, 논리삭제 deleted_yn, 한국어 COMMENT.
-- 개인정보 원칙: 사진은 어디에도 저장하지 않는다. ct_document 에는 AI 가 정리한 결과(글)만 둔다.
-- 초대 번호(6자리)는 HMAC-SHA256(JWT_SECRET) 으로, 초대 링크 토큰은 SHA-256 으로만 둔다.

-- ct_family_link: 어르신(SENIOR) ↔ 자녀(CHILD) 연결
CREATE TABLE IF NOT EXISTS ct_family_link (
    family_link_no BIGSERIAL PRIMARY KEY,
    senior_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    child_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    senior_label VARCHAR(30),
    child_label VARCHAR(30),
    status_cd VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    invite_no BIGINT,
    linked_at TIMESTAMPTZ NOT NULL,
    unlinked_at TIMESTAMPTZ,
    unlinked_by_user_no BIGINT,
    unlink_reason_cd VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by BIGINT,
    CONSTRAINT ck_ct_family_link_not_self CHECK (senior_user_no <> child_user_no)
);
COMMENT ON TABLE ct_family_link IS '가족 연결 (어르신 1 : 자녀 여럿, 자녀 1 : 어르신 여럿)';
COMMENT ON COLUMN ct_family_link.family_link_no IS '가족 연결 고유번호 (PK)';
COMMENT ON COLUMN ct_family_link.senior_user_no IS '어르신 회원번호 (서류 주인)';
COMMENT ON COLUMN ct_family_link.child_user_no IS '자녀 회원번호 (대신 보내기·공유 받기)';
COMMENT ON COLUMN ct_family_link.senior_label IS '자녀가 어르신을 부르는 이름 (예: 엄마)';
COMMENT ON COLUMN ct_family_link.child_label IS '어르신이 자녀를 부르는 이름 (예: 큰딸)';
COMMENT ON COLUMN ct_family_link.status_cd IS '연결 상태 (ACTIVE:연결됨 / UNLINKED:끊음)';
COMMENT ON COLUMN ct_family_link.invite_no IS '이 연결을 만든 초대 (ct_family_invite.invite_no)';
COMMENT ON COLUMN ct_family_link.linked_at IS '연결된 일시 (초대 수락)';
COMMENT ON COLUMN ct_family_link.unlinked_at IS '연결 끊은 일시';
COMMENT ON COLUMN ct_family_link.unlinked_by_user_no IS '연결을 끊은 회원번호 (어느 쪽이든 끊을 수 있다)';
COMMENT ON COLUMN ct_family_link.unlink_reason_cd IS '끊은 사유 (SELF:직접 / WITHDRAW:한쪽 탈퇴)';
COMMENT ON COLUMN ct_family_link.created_at IS '등록일시';
COMMENT ON COLUMN ct_family_link.created_by IS '등록자 회원번호 (초대를 수락한 회원)';
COMMENT ON COLUMN ct_family_link.updated_at IS '수정일시';
COMMENT ON COLUMN ct_family_link.updated_by IS '수정자 회원번호';
-- 같은 두 사람은 살아 있는 연결이 하나뿐. (반대 방향 중복은 서비스가 막는다)
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_family_link_pair_active
    ON ct_family_link (senior_user_no, child_user_no) WHERE status_cd = 'ACTIVE';
CREATE INDEX IF NOT EXISTS ix_ct_family_link_child ON ct_family_link (child_user_no, status_cd);

-- ct_family_invite: 초대 (6자리 번호 + 링크 토큰, 짧게 살고 한 번만 쓰인다)
CREATE TABLE IF NOT EXISTS ct_family_invite (
    invite_no BIGSERIAL PRIMARY KEY,
    inviter_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    inviter_role_cd VARCHAR(20) NOT NULL,
    invitee_label VARCHAR(30),
    code_hash CHAR(64) NOT NULL,
    link_token_hash CHAR(64) NOT NULL,
    status_cd VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_user_no BIGINT,
    accepted_at TIMESTAMPTZ,
    family_link_no BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_family_invite IS '가족 연결 초대 (번호·링크는 해시만 둔다)';
COMMENT ON COLUMN ct_family_invite.invite_no IS '초대 고유번호 (PK)';
COMMENT ON COLUMN ct_family_invite.inviter_user_no IS '초대한 회원번호';
COMMENT ON COLUMN ct_family_invite.inviter_role_cd IS '초대한 사람의 역할 (SENIOR/CHILD). 받는 사람은 반대 역할';
COMMENT ON COLUMN ct_family_invite.invitee_label IS '초대한 사람이 받는 사람을 부를 이름 (예: 엄마)';
COMMENT ON COLUMN ct_family_invite.code_hash IS '6자리 초대 번호의 HMAC-SHA256 (원문은 두지 않는다)';
COMMENT ON COLUMN ct_family_invite.link_token_hash IS '초대 링크 토큰(256비트)의 SHA-256';
COMMENT ON COLUMN ct_family_invite.status_cd IS '상태 (PENDING:기다림 / ACCEPTED:수락 / CANCELLED:취소 / EXPIRED:만료)';
COMMENT ON COLUMN ct_family_invite.expires_at IS '만료일시 (기본 30분)';
COMMENT ON COLUMN ct_family_invite.accepted_user_no IS '수락한 회원번호';
COMMENT ON COLUMN ct_family_invite.accepted_at IS '수락일시';
COMMENT ON COLUMN ct_family_invite.family_link_no IS '수락으로 생긴 연결';
COMMENT ON COLUMN ct_family_invite.created_at IS '등록일시';
COMMENT ON COLUMN ct_family_invite.updated_at IS '수정일시';
-- 6자리는 기다리는 초대들 사이에서만 유일하다 (만료·사용된 번호는 다시 나올 수 있다).
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_family_invite_code_pending
    ON ct_family_invite (code_hash) WHERE status_cd = 'PENDING';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_family_invite_token ON ct_family_invite (link_token_hash);
CREATE INDEX IF NOT EXISTS ix_ct_family_invite_inviter ON ct_family_invite (inviter_user_no, status_cd);

-- ct_document: 분석 결과 (사진 없음)
CREATE TABLE IF NOT EXISTS ct_document (
    document_no BIGSERIAL PRIMARY KEY,
    document_uid VARCHAR(40) NOT NULL,
    owner_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    sender_user_no BIGINT,
    family_link_no BIGINT,
    sender_label VARCHAR(30),
    source_cd VARCHAR(20) NOT NULL DEFAULT 'SELF',
    doc_type_cd VARCHAR(20) NOT NULL DEFAULT 'other',
    title VARCHAR(200),
    one_liner VARCHAR(1000),
    amount BIGINT,
    due_date DATE,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    details JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_cd VARCHAR(100),
    page_count INTEGER,
    owner_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by BIGINT,
    deleted_yn BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ
);
COMMENT ON TABLE ct_document IS '서류 분석 결과 (사진은 저장하지 않는다)';
COMMENT ON COLUMN ct_document.document_no IS '서류 고유번호 (PK)';
COMMENT ON COLUMN ct_document.document_uid IS '앱과 주고받는 서류 ID (doc_…). 전체에서 유일';
COMMENT ON COLUMN ct_document.owner_user_no IS '서류 주인 회원번호 (자녀가 보낸 것도 어르신 것)';
COMMENT ON COLUMN ct_document.sender_user_no IS '찍어서 보낸 회원번호 (본인이면 주인과 같음)';
COMMENT ON COLUMN ct_document.family_link_no IS '자녀가 보낼 때 쓴 가족 연결';
COMMENT ON COLUMN ct_document.sender_label IS '보낸 자녀를 부르는 이름 (보낼 때의 값, 자녀 탈퇴 시 지움)';
COMMENT ON COLUMN ct_document.source_cd IS '어디서 왔나 (SELF:직접 찍음 / FAMILY:자녀가 보냄 / IMPORT:기기 저장본 올림)';
COMMENT ON COLUMN ct_document.doc_type_cd IS '서류 종류 (bill/medicine/hospital/contract/government/other)';
COMMENT ON COLUMN ct_document.title IS '서류 이름 (삭제 시 지움)';
COMMENT ON COLUMN ct_document.one_liner IS '쉬운 말 요약 (삭제 시 지움)';
COMMENT ON COLUMN ct_document.amount IS '내야 할 돈 (원)';
COMMENT ON COLUMN ct_document.due_date IS '대표 기한';
COMMENT ON COLUMN ct_document.warnings IS '주의할 점 (문자열 배열)';
COMMENT ON COLUMN ct_document.details IS '자세한 내용 (''항목: 값'' 문자열 배열)';
COMMENT ON COLUMN ct_document.model_cd IS '정리한 AI 모델 (공급자:모델)';
COMMENT ON COLUMN ct_document.page_count IS '사진 장수 (사진 자체는 없음)';
COMMENT ON COLUMN ct_document.owner_seen_at IS '주인이 처음 열어 본 일시 (자녀가 보낸 새 서류 표시)';
COMMENT ON COLUMN ct_document.created_at IS '등록일시';
COMMENT ON COLUMN ct_document.created_by IS '등록자 회원번호';
COMMENT ON COLUMN ct_document.updated_at IS '수정일시 (할 일이 바뀌어도 갱신, 동기화 기준)';
COMMENT ON COLUMN ct_document.updated_by IS '수정자 회원번호';
COMMENT ON COLUMN ct_document.deleted_yn IS '삭제 여부 (삭제하면 내용을 지우고 ID 만 남긴다: 다른 기기 동기화용)';
COMMENT ON COLUMN ct_document.deleted_at IS '삭제일시';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_document_uid ON ct_document (document_uid);
CREATE INDEX IF NOT EXISTS ix_ct_document_owner ON ct_document (owner_user_no, updated_at);
CREATE INDEX IF NOT EXISTS ix_ct_document_sender ON ct_document (sender_user_no, created_at);

-- ct_document_todo: 서류의 할 일
CREATE TABLE IF NOT EXISTS ct_document_todo (
    todo_no BIGSERIAL PRIMARY KEY,
    document_no BIGINT NOT NULL REFERENCES ct_document(document_no),
    todo_uid VARCHAR(40) NOT NULL,
    title VARCHAR(200) NOT NULL,
    due_date DATE,
    detail VARCHAR(500),
    done_yn BOOLEAN NOT NULL DEFAULT FALSE,
    remind_yn BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    done_at TIMESTAMPTZ,
    done_by_user_no BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_document_todo IS '서류의 할 일';
COMMENT ON COLUMN ct_document_todo.todo_no IS '할 일 고유번호 (PK)';
COMMENT ON COLUMN ct_document_todo.document_no IS '서류 (ct_document.document_no)';
COMMENT ON COLUMN ct_document_todo.todo_uid IS '앱과 주고받는 할 일 ID (t_…). 서류 안에서 유일';
COMMENT ON COLUMN ct_document_todo.title IS '할 일 (예: 전기요금 내기)';
COMMENT ON COLUMN ct_document_todo.due_date IS '기한';
COMMENT ON COLUMN ct_document_todo.detail IS '방법·준비물 한 줄';
COMMENT ON COLUMN ct_document_todo.done_yn IS '다 했는지';
COMMENT ON COLUMN ct_document_todo.remind_yn IS '하루 전·당일 알림을 받을지 (알림은 기기가 맞춘다)';
COMMENT ON COLUMN ct_document_todo.sort_order IS '보여 줄 순서';
COMMENT ON COLUMN ct_document_todo.done_at IS '다 했다고 누른 일시';
COMMENT ON COLUMN ct_document_todo.done_by_user_no IS '다 했다고 누른 회원번호';
COMMENT ON COLUMN ct_document_todo.created_at IS '등록일시';
COMMENT ON COLUMN ct_document_todo.updated_at IS '수정일시';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_document_todo_uid ON ct_document_todo (document_no, todo_uid);

-- ct_document_share: 어르신이 자녀에게 결과를 나눔 ('자녀에게 보내기')
CREATE TABLE IF NOT EXISTS ct_document_share (
    share_no BIGSERIAL PRIMARY KEY,
    document_no BIGINT NOT NULL REFERENCES ct_document(document_no),
    family_link_no BIGINT NOT NULL REFERENCES ct_family_link(family_link_no),
    shared_by_user_no BIGINT NOT NULL,
    shared_to_user_no BIGINT NOT NULL,
    revoked_yn BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_document_share IS '서류 나눔 (어르신 → 연결된 자녀). 연결이 끊기면 같이 거둔다';
COMMENT ON COLUMN ct_document_share.share_no IS '나눔 고유번호 (PK)';
COMMENT ON COLUMN ct_document_share.document_no IS '서류 (ct_document.document_no)';
COMMENT ON COLUMN ct_document_share.family_link_no IS '나눈 가족 연결';
COMMENT ON COLUMN ct_document_share.shared_by_user_no IS '나눈 회원번호 (서류 주인)';
COMMENT ON COLUMN ct_document_share.shared_to_user_no IS '받은 회원번호 (자녀)';
COMMENT ON COLUMN ct_document_share.revoked_yn IS '거둠 여부 (주인이 거두거나 연결이 끊김)';
COMMENT ON COLUMN ct_document_share.revoked_at IS '거둔 일시';
COMMENT ON COLUMN ct_document_share.created_at IS '나눈 일시';
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_document_share_active
    ON ct_document_share (document_no, shared_to_user_no) WHERE revoked_yn = FALSE;
CREATE INDEX IF NOT EXISTS ix_ct_document_share_to ON ct_document_share (shared_to_user_no, revoked_yn);

-- ct_push_log: 푸시 보낸 기록 (알림 내용은 남기지 않는다)
CREATE TABLE IF NOT EXISTS ct_push_log (
    push_log_no BIGSERIAL PRIMARY KEY,
    user_no BIGINT NOT NULL,
    push_token_no BIGINT,
    event_cd VARCHAR(30) NOT NULL,
    document_no BIGINT,
    family_link_no BIGINT,
    sender_cd VARCHAR(20) NOT NULL,
    result_cd VARCHAR(20) NOT NULL,
    message_id VARCHAR(200),
    error_cd VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_push_log IS '푸시 발송 기록 (토큰 1개당 1행, 받을 기기가 없으면 NO_TOKEN 1행)';
COMMENT ON COLUMN ct_push_log.push_log_no IS '푸시 기록 고유번호 (PK)';
COMMENT ON COLUMN ct_push_log.user_no IS '받는 회원번호';
COMMENT ON COLUMN ct_push_log.push_token_no IS '보낸 푸시 토큰 (ct_user_push_token.push_token_no)';
COMMENT ON COLUMN ct_push_log.event_cd IS '이벤트 (DOC_RECEIVED:자녀가 보냄 / DOC_SHARED:어르신이 나눔 / FAMILY_LINKED:연결됨)';
COMMENT ON COLUMN ct_push_log.document_no IS '관련 서류';
COMMENT ON COLUMN ct_push_log.family_link_no IS '관련 가족 연결';
COMMENT ON COLUMN ct_push_log.sender_cd IS '발송 수단 (FCM/FAKE/NONE)';
COMMENT ON COLUMN ct_push_log.result_cd IS '결과 (SENT/FAILED/INVALID_TOKEN/NO_TOKEN/DISABLED)';
COMMENT ON COLUMN ct_push_log.message_id IS 'FCM 메시지 이름';
COMMENT ON COLUMN ct_push_log.error_cd IS '실패 사유 코드 (예: UNREGISTERED)';
COMMENT ON COLUMN ct_push_log.created_at IS '발송일시';
CREATE INDEX IF NOT EXISTS ix_ct_push_log_user ON ct_push_log (user_no, created_at);

-- ct_family_log: 가족 기능 감사 기록 (초대·수락·끊기·대신 보내기·나눔·거절된 접근)
CREATE TABLE IF NOT EXISTS ct_family_log (
    family_log_no BIGSERIAL PRIMARY KEY,
    actor_user_no BIGINT,
    event_cd VARCHAR(30) NOT NULL,
    family_link_no BIGINT,
    invite_no BIGINT,
    document_no BIGINT,
    target_user_no BIGINT,
    success_yn BOOLEAN NOT NULL DEFAULT TRUE,
    fail_reason VARCHAR(200),
    ip_address VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE ct_family_log IS '가족 기능 감사 기록';
COMMENT ON COLUMN ct_family_log.family_log_no IS '기록 고유번호 (PK)';
COMMENT ON COLUMN ct_family_log.actor_user_no IS '한 회원번호';
COMMENT ON COLUMN ct_family_log.event_cd IS '이벤트 (INVITE_CREATE/INVITE_CANCEL/INVITE_ACCEPT/INVITE_FAIL/LINK_LABEL/LINK_UNLINK/DOC_SEND/DOC_SHARE/DOC_UNSHARE/DOC_DELETE/ACCESS_DENIED)';
COMMENT ON COLUMN ct_family_log.family_link_no IS '관련 가족 연결';
COMMENT ON COLUMN ct_family_log.invite_no IS '관련 초대';
COMMENT ON COLUMN ct_family_log.document_no IS '관련 서류';
COMMENT ON COLUMN ct_family_log.target_user_no IS '상대 회원번호';
COMMENT ON COLUMN ct_family_log.success_yn IS '성공 여부';
COMMENT ON COLUMN ct_family_log.fail_reason IS '실패 사유 코드 (번호·토큰 원문은 남기지 않는다)';
COMMENT ON COLUMN ct_family_log.ip_address IS '요청 IP';
COMMENT ON COLUMN ct_family_log.created_at IS '발생일시';
CREATE INDEX IF NOT EXISTS ix_ct_family_log_actor ON ct_family_log (actor_user_no, event_cd, created_at);
-- 초대 번호 맞히기 시도 제한(회원별·IP별)에 쓴다.
CREATE INDEX IF NOT EXISTS ix_ct_family_log_ip ON ct_family_log (ip_address, event_cd, created_at);
