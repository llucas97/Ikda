/// 서버 가족 연결 한 줄. 내가 상대를 보는 관계와, 상대가 나에게 준 권한.
class FamilyLink {
  const FamilyLink({
    required this.linkId,
    required this.myRole,
    required this.name,
    required this.label,
    required this.relationCd,
    required this.relationLabel,
    required this.nickname,
    required this.isPrimary,
    required this.canView,
    required this.canEdit,
    required this.canDelete,
    required this.notification,
    required this.canSend,
    this.photoUrl,
    this.mappingId,
  });

  final int linkId;
  final String myRole;
  final String name;
  final String label;
  final String? photoUrl;
  final String relationCd;
  final String relationLabel;
  final String nickname;
  final int? mappingId;
  final bool isPrimary;
  final bool canView;
  final bool canEdit;
  final bool canDelete;
  final bool notification;
  /// 상대 서류로 대신 보낼 수 있는지 (상대 줄의 can_edit_yn).
  final bool canSend;

  String get display => nickname.isEmpty ? label : nickname;

  factory FamilyLink.fromJson(Map<String, dynamic> j) {
    final member = Map<String, dynamic>.from((j['member'] as Map?) ?? const {});
    final perm = Map<String, dynamic>.from((j['permissions'] as Map?) ?? const {});
    return FamilyLink(
      linkId: (j['linkId'] as num).toInt(),
      myRole: (j['myRole'] as String?) ?? 'SENIOR',
      name: (member['name'] as String?) ?? '가족',
      label: (member['label'] as String?) ?? '가족',
      photoUrl: member['profileImageUrl'] as String?,
      relationCd: (j['relationCd'] as String?) ?? 'OTHER',
      relationLabel: (j['relationLabel'] as String?) ?? '가족',
      nickname: (j['nickname'] as String?) ?? (member['label'] as String?) ?? '가족',
      mappingId: (j['mappingId'] as num?)?.toInt(),
      isPrimary: (j['isPrimary'] as bool?) ?? false,
      canView: (perm['canView'] as bool?) ?? true,
      canEdit: (perm['canEdit'] as bool?) ?? false,
      canDelete: (perm['canDelete'] as bool?) ?? false,
      notification: (perm['notification'] as bool?) ?? true,
      canSend: (j['canSend'] as bool?) ?? (j['myRole'] == 'CHILD'),
    );
  }
}

class InviteTicket {
  const InviteTicket({
    required this.inviteId,
    required this.code,
    required this.myRole,
    required this.expiresAt,
    required this.shareText,
    required this.appLink,
    required this.webLink,
  });

  final int inviteId;
  final String code;
  final String myRole;
  final DateTime? expiresAt;
  final String shareText;
  final String appLink;
  final String webLink;

  String get pretty => code.length == 6 ? '${code.substring(0, 3)} ${code.substring(3)}' : code;

  factory InviteTicket.fromJson(Map<String, dynamic> j) => InviteTicket(
        inviteId: (j['inviteId'] as num).toInt(),
        code: j['code'] as String,
        myRole: (j['myRole'] as String?) ?? 'SENIOR',
        expiresAt: j['expiresAt'] is String ? DateTime.tryParse(j['expiresAt'] as String) : null,
        shareText: (j['shareText'] as String?) ?? '',
        appLink: (j['appLink'] as String?) ?? '',
        webLink: (j['webLink'] as String?) ?? '',
      );
}

class InvitePreview {
  const InvitePreview({
    required this.name,
    required this.yourRole,
    required this.alreadyLinked,
    this.photoUrl,
    this.relationCd,
    this.counterRelationCd,
    this.counterNickname,
  });

  final String name;
  final String? photoUrl;
  final String yourRole;
  final bool alreadyLinked;
  final String? relationCd;
  final String? counterRelationCd;
  final String? counterNickname;

  factory InvitePreview.fromJson(Map<String, dynamic> j) {
    final inviter = Map<String, dynamic>.from((j['inviter'] as Map?) ?? const {});
    return InvitePreview(
      name: (inviter['name'] as String?) ?? '가족',
      photoUrl: inviter['profileImageUrl'] as String?,
      yourRole: (j['yourRole'] as String?) ?? 'SENIOR',
      alreadyLinked: (j['alreadyLinked'] as bool?) ?? false,
      relationCd: j['relationCd'] as String?,
      counterRelationCd: j['counterRelationCd'] as String?,
      counterNickname: j['counterNickname'] as String?,
    );
  }
}

/// 부모 쪽에서 보는 관계. 그림이 큰 고르기 화면에서 쓴다.
const parentRelations = <(String, String)>[
  ('DAUGHTER', '딸'),
  ('SON', '아들'),
  ('DAUGHTER_IN_LAW', '며느리'),
  ('SON_IN_LAW', '사위'),
  ('GRANDCHILD', '손주'),
  ('SPOUSE', '배우자'),
  ('OTHER', '기타'),
];

/// 자녀가 부모를 부르는 관계.
const elderRelations = <(String, String)>[
  ('MOTHER', '어머니'),
  ('FATHER', '아버지'),
  ('GRANDMOTHER', '할머니'),
  ('GRANDFATHER', '할아버지'),
  ('SPOUSE', '배우자'),
  ('OTHER', '기타'),
];

String relationKo(String code) {
  for (final row in [...parentRelations, ...elderRelations]) {
    if (row.$1 == code) return row.$2;
  }
  return '가족';
}
