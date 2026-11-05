# 네트워크 국내 / 해외 · 이름 다듬기 · 앱이 들고 있던 값을 서버로 (2026-11-05)
#   python3 backend/tests/test_network_groups.py
#
# Min: "이건 국내/해외로 나누면 될 것 같고 KMW HA nam 처럼 이름 이상한건 좀
#      고쳐주던가 … 근데 내가 말한 모든건 fix가 되면 안되고 유동적으로 변경이
#      되게끔 되어야해 왜냐면 이번주 이후로 난 앱 업데이트를 못 하거든"
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import division_columns as d   # noqa: E402

# 2026-11-05 — 묶음은 엑셀 칸이 정한다. 코드 이름 규칙은 처음 한 번 옮겨 적을 때만(seed_group).
G = lambda k, lab, ov=None: d.seed_group("network", k, lab)[0]
for k, lab in [("network_fxc_vn", "FXC VN"), ("network_kmw_ha_nam", "KMW HÀ nam"),
               ("network_nokia_india", "Nokia India"), ("network_nokia_finland", "Nokia Finland"),
               ("network_ls_vn", "LS VN"), ("network_aristocrat", "ARISTOCRAT"),
               ("network_watch_guard", "WATCH GUARD"), ("network_avigilon", "AVIGILON"),
               ("network_fxc_vn_sanmina_mexico", "FXC VN / Sanmina/ Mexico"),
               ("network_ericsson", "ERICSSON"), ("network_portable_winch", "PORTABLE WINCH"),
               ("network_wave_tech", "WAVE TECH")]:
    assert G(k, lab) == "해외", (k, lab)
for k, lab in [("network_samsung", "SAMSUNG"), ("network_ls", "LS 산전"), ("network_krf", "KRF"),
               ("network_hanwha", "HANWHA"), ("network_avnet", "AVNET")]:          # 'AVNET' 안의 VN 은 나라가 아니다
    assert G(k, lab) == "국내", (k, lab)
# 엑셀 '국내/해외' 칸이 이긴다 — 해외는 더 안 나눈다
assert d.customer_group("network", "network_samsung", ["해외", ""], "SAMSUNG") == ["해외", ""]
assert d.customer_group("network", "network_fxc_vn", ["국내", ""], "FXC VN") == ["국내", ""]
assert d.region_on("network") and d.group_col("network")["header"] == "국내/해외"
assert d.group_title("network") == "국내 / 해외"

# ── 이름 다듬기 (화면만)
c = d.clean_label
assert c("KMW HÀ nam") == "KMW HA NAM", c("KMW HÀ nam")
assert c("Nokia India") == "Nokia India" and c("Waymo") == "Waymo"
assert c("Banff DUT Rack ver 1") == "Banff DUT Rack ver 1", "원래 섞어 쓰는 이름을 바꿨다"
assert c("LS 산전") == "LS 산전" and c("영화테크") == "영화테크"
assert c("Đồng Nai") == "Dong Nai"

# ── 앱이 들고 있던 것을 서버로
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
assert '"owner_label": _dcol.columns_for(div_id)["owner_label"]' in SRC
assert '"group_title": _dcol.group_title(div_id)' in SRC
assert '"label": _dcol.clean_label(p.get("label"))' in SRC
assert '"board": _dcol.board_on(_div, _key)' in SRC
MOB = ROOT.parent / "mobile/lib"
assert "kServerOwnerLabels[d.id.toLowerCase()]" in (MOB / "services/divisions_service.dart").read_text(encoding="utf-8")
assert "final b = ms.data?['board'];" in (MOB / "screens/project_overview_screen.dart").read_text(encoding="utf-8")
assert "j['group_title']" in (MOB / "models/division.dart").read_text(encoding="utf-8")
# 서버의 보드 판정이 지금 앱 판정과 같다 (옮기면서 바뀌면 안 된다)
for k, div, want in [("chamber", "semiconductor", True), ("spacex", "semiconductor", True),
                     ("cup", "semiconductor", False), ("pcb_smac", "pcb", True),
                     ("bloom_sm", "bloom", True), ("ess_sdi", "ess", True),
                     ("network_samsung", "network", False), ("arista_banff", "arista", True)]:
    assert d.board_on(div, k) == want, (k, want)
# 칸이 빈 새 고객사는 짐작하지 않는다
assert d.customer_group("network", "network_brand_new_vn", None, "BRAND NEW VN") == ["미분류", ""]
print("ok — 네트워크 국내/해외 · 이름 다듬기 · 보드 · 글자를 서버가 정한다")
