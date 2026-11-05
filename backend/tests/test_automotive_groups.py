# 자동차 고객사를 큰 고객으로 — 이름 첫 낱말 (2026-11-05)
#   python3 backend/tests/test_automotive_groups.py
#
# Min: "자동차사업부 같은 경우에는 고객사별로 묶어줘 HYYUNDAi, LG, VALEO처럼
#      이렇게 고객사 여러개 있긴 한데 결국에는 한 큰틀로 나눌 수 잇게끔 해줘"
#      → "이후에 다른 고객사 생기면 어떻게 분류하려고" → "자동차 같은 경우...이름으로 묶어주고"
# 명단을 외우지 않는다 — 새 고객사도 이름만으로 따라온다.
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import division_columns as d   # noqa: E402

LABS = ("VALEO ETAPLES|LGE VN|LGE KR|JAHWA VINA|KET VINA|SDI KR|KEFICO INDIA|SIEMENS|KET KOREA|"
        "영화테크|HYUNDAI JG|SDI MLBW|VALEO SLP|VALEO CZE POLAND|Waymo|VALEO KAPEC|Stellantis|"
        "KEFICO KR|VALEO SFL|SDI AUSTRIA|SDI PPE|BORGWARNER CN|KEFICO VN|HANON|VALEO HUNGARY|"
        "SDI USA|LG MAGNA|Schaeffler|SDI HUNGARY|HYUNDAI MOBIS").split("|")
G = lambda lab, peers=LABS: d.customer_group("automotive", "automotive_x", None, lab, "", peers)[0]

got = {}
for lab in LABS:
    got.setdefault(G(lab), []).append(lab)
assert {k: len(v) for k, v in got.items()} == {
    "VALEO": 6, "SDI": 6, "LG": 3, "KEFICO": 3, "HYUNDAI": 2, "KET": 2, "기타": 8}, got
assert G("LGE VN") == "LG" and G("LG MAGNA") == "LG", "LGE 와 LG 가 안 합쳐졌다"
assert G("HANON") == "기타" and G("Waymo") == "기타", "혼자인 고객사가 기타로 안 갔다"
assert G("KET VINA") == "KET" and G("KEFICO KR") == "KEFICO", "KET 와 KEFICO 가 섞였다"

# 새 고객사 — 코드도 엑셀 칸도 없이 이름만으로
NEW = LABS + ["VALEO MEXICO", "BOSCH KR", "BOSCH CN"]
assert G("VALEO MEXICO", NEW) == "VALEO", "새 VALEO 고객사가 안 붙었다"
assert G("BOSCH KR", NEW) == "BOSCH" and G("BOSCH CN", NEW) == "BOSCH", "새 큰 고객 묶음이 안 생겼다"
assert G("BOSCH KR", LABS + ["BOSCH KR"]) == "기타", "혼자인 BOSCH 가 묶음이 됐다"

# 순서 — 고객사가 많은 큰 고객부터, 기타는 맨 뒤
_gs = [d.customer_group("automotive", "x", None, lab, "", LABS) for lab in LABS]
order = [x[0] for x in d.customer_group_order("automotive", _gs)]
assert order[:2] == ["SDI", "VALEO"] and order[-2:] == ["기타", "미분류"], order

# 양식에 묶음 칸은 없다 · 처음 옮겨 적기도 안 한다 (이름이 늘 정한다)
assert not d.region_on("automotive") and d.group_col("automotive") is None
assert d.seed_group("automotive", "automotive_hanon", "HANON") is None
assert d.group_title("automotive") == "고객사별"

# /divisions 가 이름 전부를 넘긴다
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_ld = SRC[SRC.find("def list_divisions"):]
_ld = _ld[:_ld.find("\n@app.", 10)]
assert '_peers = [p.get("label") or "" for p in ps_sorted]' in _ld and _ld.count("_peers)") >= 2
DART = (ROOT.parent / "mobile/lib/screens/division_projects_screen.dart").read_text(encoding="utf-8")
assert "widget.division.groupTitle.isNotEmpty" in DART
print("ok — 자동차 고객사 묶음 (이름 첫 낱말 · 혼자면 기타 · 새 고객사 자동)")
