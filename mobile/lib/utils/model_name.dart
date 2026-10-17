// -*- 모델 이름 한 곳 -*-
//
/// 화면에 보일 모델 이름.
///
/// 모델명 칸은 비어 있을 수 있다 — 품번만 있고 따로 부르는 이름이 없는
/// 것들(아리스타 PCB)은 관리자 표에서 빈 칸으로 둔다. 그래도 목록에 빈
/// 줄이 보이면 안 되니 화면에서만 품번으로 대신한다.
///
/// `m['name'] ?? m['id']` 로는 모자란다 — 그건 null 만 잡고 빈 문자열은
/// 그대로 통과시킨다. 실제로 원가 화면 두 곳이 그렇게 빈 줄을 보여줬다.
String modelDisplayName(Map m) {
  final n = (m['name'] ?? '').toString().trim();
  if (n.isNotEmpty) return n;
  final pn = (m['part_number'] ?? '').toString().trim();
  if (pn.isNotEmpty) return pn;
  return (m['id'] ?? '').toString();
}
