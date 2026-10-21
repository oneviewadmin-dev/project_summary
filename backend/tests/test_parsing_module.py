# 파싱 함수는 parsing.py 에 있고, main.py 는 그것을 가져다 쓴다
#   python3 backend/tests/test_parsing_module.py
#
# main.py 가 28,000줄이라 쪼개기 시작했다. 첫 조각이 '글자에서 뜻을 꺼내는'
# 함수들이다. 서버 상태를 안 쓰는 순수 함수라 떼어내기가 가장 안전했다.
# 이 시험은 두 가지를 못 하게 막는다.
#   · parsing.py 안의 함수가 서버 상태(파일·설정·전역)를 다시 끌어 쓰는 것
#   · 누가 main.py 에 같은 함수를 다시 정의해 두 벌이 되는 것
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]      # backend/
sys.path.insert(0, str(ROOT))

MOVED = ["_parse_due_text", "_parse_report_filename", "_extract_excel_markers",
         "_parse_shipping_table_header", "_parse_sales_input"]
ok = 0

# ── 1. parsing.py 가 있고 다섯 개가 다 있다 ───────────────────
import parsing as P                                      # noqa: E402

for n in MOVED:
    assert hasattr(P, n), "parsing.py 에 %s 가 없다" % n
ok += 1

# ── 2. main.py 는 그걸 import 한다 (다시 정의하지 않는다) ──────
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
tree = ast.parse(SRC)

imported = set()
for n in tree.body:
    if isinstance(n, ast.ImportFrom) and n.module == "parsing":
        imported |= {a.name for a in n.names}
for n in MOVED:
    assert n in imported, "main.py 가 %s 를 parsing 에서 안 가져온다" % n
ok += 1

redefined = [n.name for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name in MOVED]
assert not redefined, "main.py 에 다시 정의돼 두 벌이다: %s" % redefined
ok += 1

# ── 3. parsing.py 는 서버 상태를 안 쓴다 ──────────────────────
# 파일을 읽거나 설정을 보기 시작하면 '따로 시험할 수 있다' 는 장점이 사라진다.
PSRC = (ROOT / "parsing.py").read_text(encoding="utf-8")
for bad in ("open(", "Path(", "os.getenv", "requests.", "json.load",
            "import main", "from main"):
    assert bad not in PSRC, "parsing.py 가 서버 상태를 쓴다: %s" % bad
ok += 1

# ── 4. 실제로 읽어 낸다 ───────────────────────────────────────
r = P._parse_report_filename("260703_파워박스 진행현황.pptx")
assert r["projects"] == ["파워박스"], r
assert r["date"] == "2026-07-03", r
assert r["week"] == 27, r
ok += 1

assert P._parse_due_text("8월 24일").endswith("-08-24"), P._parse_due_text("8월 24일")
assert P._parse_due_text("날짜 없음") is None
ok += 1

text, tables = P._extract_excel_markers(
    "앞줄\n\U0001F4CA 표.xlsx @@table_ref=A1:C3\n뒷줄")
assert text == "앞줄\n뒷줄", repr(text)          # 마커 줄은 본문에서 빠진다
assert tables == [{"filename": "표.xlsx", "table_ref": "A1:C3", "anchor": "앞줄"}], tables
ok += 1

s = P._parse_sales_input("[모델/판가]\nEFEM=65\nVTM=24\n\n[주차별]\nW27: EFEM 2/2, VTM 1/0")
assert s["prices"] == {"EFEM": 65.0, "VTM": 24.0}, s
assert s["weeks"]["W27"]["EFEM"] == {"plan": 2, "actual": 2}, s
assert s["weeks"]["W27"]["VTM"] == {"plan": 1, "actual": 0}, s
ok += 1

h = P._parse_shipping_table_header([])                   # 머리가 3줄이 안 되면
assert h == {"columns": [], "detected_months": [], "current_month": None}, h
ok += 1

print("전부 통과 ·", ok, "가지")
