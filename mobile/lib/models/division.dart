// 사업부(division) 데이터 모델.
// 백엔드 GET /divisions 응답을 그대로 받기 위한 클래스들입니다.
// 응답 구조 예:
// {
//   "divisions": [
//     {
//       "id": "semiconductor",
//       "label": "반도체사업부",
//       "order": 1,
//       "badge_short_label": "반도체",
//       "projects": [ { "id": "frame", "label": "프레임", "order": 8 }, ... ]
//     },
//     ...
//   ]
// }

// 사업부 안의 프로젝트 한 칸을 표현하는 가벼운 참조 모델.
// 홈/목록 화면에서 "사업부 → 프로젝트" 그리드를 그릴 때 사용합니다.
class DivisionProjectRef {
  // 프로젝트 식별자 (예: 'frame')
  final String id;

  // 화면에 표시할 한글 이름 (예: '프레임')
  final String label;

  // 사업부 내에서의 정렬 순서. 작은 숫자가 먼저 표시됩니다.
  final int order;

  // 모델 데이터 유무 (서버에서 계산됨).
  final bool hasModels;

  // 고객사 묶음 [큰 묶음, 작은 묶음] — 예: ['해외', 'Lam'] (2026-11-04).
  // 서버(division_columns.CUSTOMER_GROUPS)가 정한다. 묶지 않으면 null.
  final List<String>? group;

  const DivisionProjectRef({
    required this.id,
    required this.label,
    required this.order,
    this.hasModels = false,
    this.group,
  });

  // JSON → 모델 변환.
  // 안전을 위해 누락된 필드는 빈 문자열/0 으로 채웁니다.
  factory DivisionProjectRef.fromJson(Map<String, dynamic> j) {
    return DivisionProjectRef(
      id: (j['id'] ?? '').toString(),
      label: (j['label'] ?? '').toString(),
      order: (j['order'] is int) ? j['order'] as int : 0,
      hasModels: j['has_models'] as bool? ?? false,
      group: _pair(j['group']),
    );
  }
}

// 사업부 단위 모델.
// 사업부 자체의 정보 + 그 사업부에 속한 프로젝트 리스트를 담습니다.
class Division {
  // 사업부 식별자 (예: 'semiconductor')
  final String id;

  // 화면 표시용 풀네임 (예: '반도체사업부')
  final String label;

  // 짧은 라벨 (예: '반도체'). 카드 위 작은 배지 등에 사용합니다.
  final String? badgeShortLabel;

  // 사업부 정렬 순서.
  final int order;

  // 이 사업부에 속한 프로젝트들. order 기준으로 정렬된 상태로 보관합니다.
  final List<DivisionProjectRef> projects;

  // 고객사 묶음 순서 (2026-11-04) — [['국내',''], ['해외','Lam'], …].
  // 비어 있으면 묶지 않는다. 서버가 보낸다 — 앱 배포 없이 바뀐다.
  final List<List<String>> customerGroups;

  // 서버가 정하는 글자 (2026-11-05 — 이번 주 뒤로 앱을 못 올린다).
  //   ownerLabel  '고객사' · '프로젝트'   비어 있으면 앱의 옛 규칙(ownerLabelOf)
  //   groupTitle  묶은 목록 위 작은 제목  ('국내 / 해외' · '고객사별' · '종류별')
  final String ownerLabel;
  final String groupTitle;

  const Division({
    required this.id,
    required this.label,
    required this.order,
    required this.projects,
    this.badgeShortLabel,
    this.customerGroups = const [],
    this.ownerLabel = '',
    this.groupTitle = '',
  });

  // JSON → 모델 변환.
  // projects 도 함께 파싱하고, order 기준 오름차순 정렬해 둡니다.
  factory Division.fromJson(Map<String, dynamic> j) {
    final list = (j['projects'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(DivisionProjectRef.fromJson)
        .toList()
      ..sort((a, b) => a.order.compareTo(b.order));

    return Division(
      id: (j['id'] ?? '').toString(),
      label: (j['label'] ?? '').toString(),
      badgeShortLabel: j['badge_short_label']?.toString(),
      order: (j['order'] is int) ? j['order'] as int : 0,
      projects: list,
      customerGroups: [
        for (final g in (j['customer_groups'] as List? ?? const []))
          if (_pair(g) != null) _pair(g)!,
      ],
      ownerLabel: (j['owner_label'] ?? '').toString(),
      groupTitle: (j['group_title'] ?? '').toString(),
    );
  }
}

/// ['해외', 'Lam'] 모양만 받는다. 아니면 null.
List<String>? _pair(dynamic v) {
  if (v is! List || v.isEmpty) return null;
  final a = v.map((e) => (e ?? '').toString()).toList();
  return [a[0], a.length > 1 ? a[1] : ''];
}
