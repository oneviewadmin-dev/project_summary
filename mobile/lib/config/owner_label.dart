// 사업부마다 '프로젝트' 를 뭐라고 부르나 (2026-11-04)
//
// Min: "ESS, 자동차, 네트워크, PCB는 고객사 00개로 명칭 변경해줘"
//
// 이 네 사업부는 프로젝트가 곧 고객사다 (양식도 '고객사별 품목정보').
// 서버 backend/division_columns.py SHAPES 의 '고객사형' 과 같은 목록이다 —
// 한쪽만 바꾸면 테스트(test_owner_label.py)가 잡는다.
const Set<String> kCustomerDivisions = {'ess', 'pcb', 'network', 'automotive'};

/// 서버(/divisions 의 owner_label)가 알려 준 값 (2026-11-05).
/// DivisionsService 가 받을 때마다 채운다. 여기 있으면 이게 먼저다 —
/// 앱을 다시 올리지 않아도 서버(division_columns FORMS)에서 바뀐다.
final Map<String, String> kServerOwnerLabels = {};

/// '고객사' 또는 '프로젝트'.
String ownerLabelOf(String? divisionId) {
  final id = (divisionId ?? '').trim().toLowerCase();
  final s = kServerOwnerLabels[id];
  if (s != null && s.isNotEmpty) return s;
  return kCustomerDivisions.contains(id) ? '고객사' : '프로젝트';
}
