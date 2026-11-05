// 고객사 목록을 국내 / 해외로 나눠 보여 준다 (2026-11-04)
//
// Min: "고객사 매출 기여순으로 하지 말고 국내/해외로 나누고 해외 같은 경우에
//      Lam, 아리스타, 기타로 나눠줘"
//
// ★ 고치는 곳은 서버다 — backend/division_columns.py 의 CUSTOMER_GROUPS.
//   서버가 /divisions 로 묶음을 보내 주면 앱은 그대로 따른다 (앱 배포 없음).
//   여기 값은 그걸 안 보내 주는 옛 서버를 만났을 때만 쓰는 예비다.

/// 묶음 순서 — [큰 묶음, 작은 묶음]
const List<List<String>> kCustomerGroupOrder = [
  ['국내', ''],
  ['해외', 'Lam'],
  ['해외', '아리스타'],
  ['해외', '기타'],
];

/// PCB 해외 · 기타 (인도 · 해외 법인)
const Set<String> kPcbOverseasOther = {
  'pcb_kaynes_technology',
  'pcb_kumho_india',
  'pcb_vvdn_tech',
  'pcb_motherson_marelli',
  'pcb_unominda',
  'pcb_cci_antenna',
};

/// 묶어서 보여 줄 사업부인가
bool customerGroupsOn(String divisionId) => divisionId == 'pcb';

/// 그 고객사의 [큰 묶음, 작은 묶음]. 묶지 않는 사업부면 null.
List<String>? customerGroupOf(String divisionId, String projectId) {
  if (!customerGroupsOn(divisionId)) return null;
  final k = projectId.trim().toLowerCase();
  if (k.startsWith('pcb_lam_') || k == 'pcb_lam') return const ['해외', 'Lam'];
  if (k == 'pcb_arista') return const ['해외', '아리스타'];
  if (kPcbOverseasOther.contains(k)) return const ['해외', '기타'];
  return const ['국내', ''];
}
