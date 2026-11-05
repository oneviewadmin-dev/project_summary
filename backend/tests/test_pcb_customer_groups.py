# PCB 고객사 목록 — 국내 / 해외(Lam · 아리스타 · 기타) (2026-11-04)
#   python3 backend/tests/test_pcb_customer_groups.py
#
# Min: "고객사 매출 기여순으로 하지 말고 국내/해외로 나누고 해외 같은 경우에
#      Lam, 아리스타, 기타로 나눠줘"
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import division_columns as dc   # noqa: E402
LIB = ROOT / "mobile" / "lib"
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


cfg = (LIB / "config/customer_groups.dart").read_text(encoding="utf-8")
scr = (LIB / "screens/division_projects_screen.dart").read_text(encoding="utf-8")

order = re.findall(r"\['(국내|해외)', '([^']*)'\]", cfg[cfg.find("kCustomerGroupOrder"):cfg.find("kPcbOverseasOther")])
ok(order == [("국내", ""), ("해외", "Lam"), ("해외", "아리스타"), ("해외", "기타")], "묶음 순서가 다르다: %r" % order)
ok("k.startsWith('pcb_lam_')" in cfg, "새 LAM 고객사가 Lam 으로 안 따라온다")
ok("k == 'pcb_arista'" in cfg, "아리스타 묶음이 없다")
ok("bool customerGroupsOn(String divisionId) => divisionId == 'pcb';" in cfg, "PCB 만 켜는 스위치가 아니다")

ok("config/customer_groups.dart" in scr, "사업부 화면이 묶음 설정을 안 불러온다")
# ── 서버가 정한다 (2026-11-04, Min: "최대한 앱 배포 없이 픽스")
# 2026-11-05 — 묶음은 엑셀 칸이 정한다. 코드 이름 규칙은 처음 한 번 옮겨 적을 때만(seed_group).
ok(dc.customer_group_order("pcb") == [["국내", ""], ["해외", "Lam"], ["해외", "아리스타"], ["해외", "기타"],
                                     ["미분류", ""]], "서버 묶음 순서가 다르다")
ok(dc.customer_group("pcb", "pcb_lam_new_one", ["해외", ""], "LAM NEW") == ["해외", "Lam"], "새 LAM 고객사가 Lam 으로 안 간다")
ok(dc.customer_group("pcb", "pcb_arista", ["해외", ""], "아리스타") == ["해외", "아리스타"], "아리스타 묶음")
ok(dc.seed_group("pcb", "pcb_kumho_india") == ["해외", "기타"], "옮겨 적을 때 해외 기타")
ok(dc.seed_group("pcb", "pcb_lam_jabil", "LAM JABIL") == ["해외", "Lam"], "옮겨 적을 때 Lam")
ok(dc.seed_group("pcb", "pcb_brand_new") == ["국내", ""], "옮겨 적을 때 모르는 고객사는 국내")
ok(dc.customer_group("pcb", "pcb_brand_new") == ["미분류", ""], "칸이 빈 새 고객사를 짐작했다")
ok(dc.customer_group("ess", "ess_sdi") is None and dc.customer_group_order("ess") == [], "ESS 까지 묶였다")
# 앱 값과 서버 값이 어긋나면 옛 서버에서만 다르게 보인다 — 맞춰 둔다
_app_other = set(re.findall(r"'(pcb_[a-z_]+)'", cfg[cfg.find("kPcbOverseasOther"):cfg.find("bool customerGroupsOn")]))
_srv_other = set(dc.CUSTOMER_GROUPS["pcb"]["seed"]["rules"][0][1])
ok(_app_other == _srv_other, "앱 예비 명단과 서버 명단이 다르다: %r / %r" % (_app_other, _srv_other))
MAIN = (ROOT / "backend/main.py").read_text(encoding="utf-8")
_ld = MAIN[MAIN.find("def list_divisions"):]
_ld = _ld[:_ld.find("\n@app.", 10)]
ok('"customer_groups": _dcol.customer_group_order(' in _ld and '"group": _dcol.customer_group(div_id, p.get("id"),' in _ld,
   "/divisions 가 묶음을 안 보낸다")
mdl = (LIB / "models/division.dart").read_text(encoding="utf-8")
ok("customerGroups:" in mdl and "group: _pair(j['group'])" in mdl, "앱이 서버 묶음을 안 읽는다")
ok("widget.division.customerGroups.isNotEmpty" in scr and "p.group!" in scr, "화면이 서버 묶음을 안 쓴다")

ok("else if (_grouped) ..._groupedRows(visibleProjects)" in scr, "목록이 묶음으로 안 그려진다")
ok("if (_grouped) _sort = _ProjectSort.name;" in scr, "PCB 기본 정렬이 아직 매출 기여순이다")
_s = scr[scr.find("List<_ProjectItem> _sortProjects("):]
_s = _s[:_s.find("\n  }\n")]
ok("if (!_grouped) {" in _s, "묶음 모드에서도 매출 있는 고객사를 앞세운다")
# 줄 모양은 원래 목록과 같아야 한다
ok(scr.count("ProjectRevenueRow(") >= 2 and "Widget _projectRow(_ProjectItem p)" in scr, "묶음 줄 모양이 다르다")

# 바로 가기 버튼 — 묶음 머리글로 내려간다 (지연 그리기 때문에 미리 그려 둔다)
ok("_jumpChip(" in scr and "Scrollable.ensureVisible(ctx" in scr, "묶음 바로 가기 버튼이 없다")
ok("cacheExtent: _grouped ? 20000 : null" in scr, "아래 묶음이 아직 안 그려져서 버튼이 못 내려간다")
ok(scr.count("KeyedSubtree(key: key") >= 2, "묶음 머리글에 자리 표시가 없다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — PCB 고객사: 국내 / 해외(Lam · 아리스타 · 기타)")
