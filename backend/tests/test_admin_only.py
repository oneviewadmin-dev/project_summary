# -*- coding: utf-8 -*-
"""admin 프로젝트 목록 — 숨긴 프로젝트 중 '자료 올리는 자리' 는 보여야 한다.

블룸은 품목 일곱 개가 각각 프로젝트인데, 올리는 파일은 품목을 전부 담고
있어서 원본이 bloom_main 한 곳에 저장된다. 그런데 bloom_main 이
visible:false 라 admin 화면에 아예 안 나왔다 — 올릴 자리가 없으니 사람들은
품목 일곱 개 중 하나를 골라 올리고 있었고, 어디서 올려도 결과가 같아서
매번 헷갈렸다.

그래서 admin_only 를 붙였다. 앱·홈이 보는 목록(visible_only=True)은 그대로
두고, admin 목록에만 끼워 넣는다. 이 둘이 어긋나면 안 되므로 여기서 묶는다.
"""
import json
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

import config_loader as cl   # noqa: E402

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


MAIN = (BACK / "main.py").read_text(encoding="utf-8")


def admin_list(div):
    """main.py 의 /admin/config/projects 필터를 그대로 옮겼다."""
    items = cl.get_projects(division_id=div, visible_only=False)
    return [p for p in items if p.get("visible", True) or p.get("admin_only")]


# ── 1. 라우트가 정말 그 규칙을 쓰는가 ───────────────────────────────
for frag, why in [
    ('items = _cl.get_projects(division_id=division_id, visible_only=False)',
     "라우트가 아직 visible_only=True 다 — 숨긴 자리가 다시 사라진다"),
    ('if p.get("visible", True) or p.get("admin_only")',
     "admin_only 예외가 라우트에 없다"),
    ('"admin_only": bool(p.get("admin_only")),',
     "응답에 admin_only 가 안 들어간다"),
]:
    ok(frag in MAIN, why)


# ── 2. 2026-10-26 · 프로젝트 목록은 엑셀이 만든다 ──────────────────
#
# 전에는 블룸 품목 여덟 개 + 저장소(bloom_main)를 config 에 박아 뒀다.
# 그런데 양식에 적힌 이름이 그와 달라지면(CORVA EFM KPE · SM 등) 화면에
# '등록된 모델 없음' 짜리와 새로 생긴 것이 나란히 서서 어느 쪽이 진짜인지
# 알 수 없게 됐다. 이제 기준은 올라온 엑셀 하나다.
#
# config 에는 반도체(와 공용)만 남는다. 다른 사업부 프로젝트는 양식을
# 올릴 때 만들어진다 — 그래서 여기서 셀 수가 없다. 대신 '만들어지는 길'
# 이 살아 있는지만 지킨다.
_cfg_divs = {p.get("division_id") for p in cl.get_projects(visible_only=False)}
ok(_cfg_divs <= {"semiconductor", "system"},
   "config 에 반도체 · 공용 말고 다른 사업부가 남아 있다: %r" % sorted(_cfg_divs))

for frag, why in [
    ('def _df_create_projects', "양식으로 프로젝트를 만드는 자리가 없다"),
    ('row["bloom_item"] = r["owner"]',
     "양식으로 만든 일 보고 프로젝트에 품목 이름을 안 붙인다 — "
     "일 보고를 잘라 볼 열쇠가 없어진다"),
    ('"created_by": "division_form"',
     "양식이 만든 프로젝트에 표시를 안 남긴다 — 나중에 정리할 수가 없다"),
]:
    ok(frag in MAIN, why)


# ── 4. 다른 사업부는 하나도 안 바뀐다 ───────────────────────────────
divs = {p.get("division_id") for p in cl.get_projects(visible_only=False)
        if p.get("division_id")}
for div in sorted(divs):
    a = [p.get("id") for p in admin_list(div)]
    b = [p.get("id") for p in cl.get_projects(division_id=div, visible_only=True)]
    if div == "bloom":
        continue
    ok(a == b, "%s 의 admin 목록이 달라졌다: %s" % (div, set(a) ^ set(b)))


# ── 5. admin_only 를 아무 데나 달아 두지 않았는지 ───────────────────
alls = cl.get_projects(visible_only=False)
ao = [p.get("id") for p in alls if p.get("admin_only")]
# 2026-10-26 — bloom_main 이 config 에서 빠지면서 admin_only 도 비었다.
# 아무 데나 달지 않았는지만 본다 (반도체에는 하나도 없어야 한다).
ok(all(p.get("division_id") != "semiconductor" for p in alls if p.get("admin_only")),
   "반도체 프로젝트에 admin_only 가 붙었다: %s" % ao)
for p in alls:
    if p.get("admin_only"):
        ok(p.get("visible") is False,
           "%s 는 admin_only 인데 visible 이 false 가 아니다 — 그럼 플래그가 의미 없다"
           % p.get("id"))


# ── 6. config 파일 자체가 성립하는가 ────────────────────────────────
raw = json.loads((BACK / "config" / "projects.json").read_text(encoding="utf-8"))
seen = set()
for p in raw.get("projects", []):
    i = p.get("id")
    ok(i and i not in seen, "프로젝트 id 가 비었거나 겹친다: %r" % i)
    seen.add(i)
    ok(p.get("division_id"), "%s 에 division_id 가 없다" % i)
    ok(p.get("label"), "%s 에 label 이 없다" % i)

# 2026-10-26 — '자료 올리는 곳'(블룸 전체) 줄은 없앴다.
#
# 일 보고 자료는 오른쪽 위 '엑셀 올리기' 안에서 올린다. 그래서 품목도
# 모델도 없는 'bloom_main' 줄이 목록 맨 앞에 설 이유가 없어졌다.
# config 에서 지우지는 않는다 — 지난 자료가 그 키에 붙어 있다.
AV2 = (BACK / "admin_v2.html").read_text(encoding="utf-8")
ok("UPLOAD_LEAD_PROJECT = {};" in AV2,
   "'올리는 곳' 선언을 비우지 않았다 — 블룸 (전체) 줄이 다시 선다")
ok("MDL_PICK_HIDE" in AV2 and "'bloom_main'" in AV2,
   "프로젝트 목록에서 bloom_main 을 숨기지 않는다")
ok("블룸 자료는 <b>블룸 (전체)</b>" not in AV2,
   "없앤 '블룸 (전체)' 로 안내가 아직 보낸다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과 · 검사 6묶음 · 사업부 %d개" % len(divs))
