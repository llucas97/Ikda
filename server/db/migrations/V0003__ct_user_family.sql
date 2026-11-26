-- 읽다 DDL — V0003 가족 관계 (양방향 매핑)
--
-- ct_family_link(어르신↔자녀 한 줄)는 서류·나눔이 가리키는 연결 ID 로 그대로 둔다.
-- 관계·별명·권한은 ct_user_family 두 줄(A→B, B→A)에 둔다. 수락 한 번에 둘 다 만들고,
-- 끊으면 둘 다 논리삭제한다. 초대 번호는 ct_family_invite 에 그대로 있다.
-- 이미 적용된 V0002 는 고치지 않는다. 초대에 관계 코드를 더하는 열은 여기서 넣는다.

CREATE TABLE IF NOT EXISTS ct_user_family (
    family_mapping_no BIGSERIAL PRIMARY KEY,
    primary_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    family_user_no BIGINT NOT NULL REFERENCES ct_user(user_no),
    relation_cd VARCHAR(20) NOT NULL,
    nickname VARCHAR(50),
    is_primary_yn BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    can_view_yn BOOLEAN NOT NULL DEFAULT TRUE,
    can_edit_yn BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete_yn BOOLEAN NOT NULL DEFAULT FALSE,
    notification_yn BOOLEAN NOT NULL DEFAULT TRUE,
    memo TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT NOT NULL,
    updated_at TIMESTAMPTZ,
    updated_by BIGINT,
    deleted_yn BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by BIGINT,
    CONSTRAINT ck_ct_user_family_not_self CHECK (primary_user_no <> family_user_no),
    CONSTRAINT ck_ct_user_family_relation CHECK (relation_cd IN ('SPOUSE', 'FATHER', 'MOTHER', 'SON', 'DAUGHTER', 'SON_IN_LAW', 'DAUGHTER_IN_LAW', 'GRANDCHILD', 'BROTHER', 'SISTER', 'GRANDFATHER', 'GRANDMOTHER', 'OTHER'))
);
COMMENT ON TABLE ct_user_family IS '가족 관계 매핑. 한 연결마다 두 줄(내가 보는 관계 / 상대가 보는 관계)';
COMMENT ON COLUMN ct_user_family.family_mapping_no IS '가족 매핑 고유번호 (PK)';
COMMENT ON COLUMN ct_user_family.primary_user_no IS '대표 회원번호. 이 줄은 이 회원이 상대를 어떻게 보는지 (ct_user.user_no)';
COMMENT ON COLUMN ct_user_family.family_user_no IS '가족 회원번호. 대표 회원이 보는 상대 (ct_user.user_no)';
COMMENT ON COLUMN ct_user_family.relation_cd IS '관계 코드. 대표 회원 쪽에서 본 상대 (SPOUSE/FATHER/MOTHER/SON/DAUGHTER/SON_IN_LAW/DAUGHTER_IN_LAW/GRANDCHILD/BROTHER/SISTER/GRANDFATHER/GRANDMOTHER/OTHER)';
COMMENT ON COLUMN ct_user_family.nickname IS '화면에 보일 별명 (예: 큰딸, 어머니). 없으면 관계 이름';
COMMENT ON COLUMN ct_user_family.is_primary_yn IS '이 대표 회원이 권한(보기·수정·삭제·알림)을 고치는 사람인지';
COMMENT ON COLUMN ct_user_family.is_active IS '매핑 사용 여부. 끊으면 false';
COMMENT ON COLUMN ct_user_family.can_view_yn IS '가족 회원이 대표 회원의 서류를 볼 수 있는지';
COMMENT ON COLUMN ct_user_family.can_edit_yn IS '가족 회원이 대표 회원 대신 서류를 보내거나 할 일을 고칠 수 있는지';
COMMENT ON COLUMN ct_user_family.can_delete_yn IS '가족 회원이 대표 회원의 서류를 지울 수 있는지. 기본은 주인·보낸 사람만';
COMMENT ON COLUMN ct_user_family.notification_yn IS '대표 회원에게 이 가족 알림(푸시)을 보낼지';
COMMENT ON COLUMN ct_user_family.memo IS '메모';
COMMENT ON COLUMN ct_user_family.created_at IS '등록일시';
COMMENT ON COLUMN ct_user_family.created_by IS '등록자 회원번호';
COMMENT ON COLUMN ct_user_family.updated_at IS '수정일시';
COMMENT ON COLUMN ct_user_family.updated_by IS '수정자 회원번호';
COMMENT ON COLUMN ct_user_family.deleted_yn IS '삭제 여부 (연결을 끊으면 양쪽 줄을 함께 논리삭제)';
COMMENT ON COLUMN ct_user_family.deleted_at IS '삭제일시';
COMMENT ON COLUMN ct_user_family.deleted_by IS '삭제한 회원번호';

-- 살아 있는 쌍만 유일. 끊었다가 다시 연결하면 새 줄.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ct_user_family_pair_alive
    ON ct_user_family (primary_user_no, family_user_no) WHERE deleted_yn = FALSE;
CREATE INDEX IF NOT EXISTS ix_ct_user_family_member ON ct_user_family (family_user_no, deleted_yn);

-- 초대에 관계 제안. 없으면 별명에서 짐작한다 (예전 앱과 호환).
ALTER TABLE ct_family_invite ADD COLUMN IF NOT EXISTS relation_cd VARCHAR(20);
ALTER TABLE ct_family_invite ADD COLUMN IF NOT EXISTS counter_relation_cd VARCHAR(20);
ALTER TABLE ct_family_invite ADD COLUMN IF NOT EXISTS counter_nickname VARCHAR(30);
COMMENT ON COLUMN ct_family_invite.relation_cd IS '초대한 사람이 받는 사람을 보는 관계 코드';
COMMENT ON COLUMN ct_family_invite.counter_relation_cd IS '받는 사람이 초대한 사람을 보도록 제안한 관계 코드';
COMMENT ON COLUMN ct_family_invite.counter_nickname IS '받는 사람이 쓸 별명 제안';

-- 이미 있는 연결도 두 줄로 맞춘다. 별명이 없으면 관계는 OTHER.
INSERT INTO ct_user_family (
    primary_user_no, family_user_no, relation_cd, nickname, is_primary_yn, is_active,
    can_view_yn, can_edit_yn, can_delete_yn, notification_yn,
    created_at, created_by, updated_at, updated_by, deleted_yn)
SELECT l.senior_user_no, l.child_user_no, 'OTHER', l.child_label, TRUE, TRUE,
       TRUE, TRUE, FALSE, TRUE,
       l.linked_at, COALESCE(l.created_by, l.senior_user_no), now(), l.updated_by, FALSE
FROM ct_family_link l
WHERE l.status_cd = 'ACTIVE'
  AND NOT EXISTS (
      SELECT 1 FROM ct_user_family f
      WHERE f.primary_user_no = l.senior_user_no AND f.family_user_no = l.child_user_no AND f.deleted_yn = FALSE);

INSERT INTO ct_user_family (
    primary_user_no, family_user_no, relation_cd, nickname, is_primary_yn, is_active,
    can_view_yn, can_edit_yn, can_delete_yn, notification_yn,
    created_at, created_by, updated_at, updated_by, deleted_yn)
SELECT l.child_user_no, l.senior_user_no, 'OTHER', l.senior_label, FALSE, TRUE,
       TRUE, FALSE, FALSE, TRUE,
       l.linked_at, COALESCE(l.created_by, l.child_user_no), now(), l.updated_by, FALSE
FROM ct_family_link l
WHERE l.status_cd = 'ACTIVE'
  AND NOT EXISTS (
      SELECT 1 FROM ct_user_family f
      WHERE f.primary_user_no = l.child_user_no AND f.family_user_no = l.senior_user_no AND f.deleted_yn = FALSE);
