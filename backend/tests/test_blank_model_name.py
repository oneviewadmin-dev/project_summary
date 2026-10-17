# -*- coding: utf-8 -*-
"""모델명 칸이 비어 있으면 비어 있는 대로 둔다.

예전에는 비면 품번으로 채웠다. 그러면 관리자 표에 똑같은 글자가 두 칸
나란히 찍힌다 — 아리스타 PCB 처럼 품번만 있고 따로 부르는 이름이 없는
것들이 그렇다.

대신 이름이 꼭 있어야 하는 자리(앱 목록·상세 제목)에서는 품번으로
대신 보여준다. 거기까지 비우면 목록에 빈 줄이 뜬다.
"""
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
SRC = (BACK / "main.py").read_text(encoding="utf-8")
MOB = BACK.parent / "mobile" / "lib"
DART = (MOB / "screens" / "model_list_screen.dart").read_text(encoding="utf-8")
HELP = MOB / "utils" / "model_name.dart"

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


i = SRC.find("async def admin_models_import")
ok(i > 0, "모델 등록 엑셀 처리가 없어졌다")
blk = SRC[i:i + 14000]

ok('name = str(name_v).strip() if name_v is not None else ""' in blk,
   "모델명이 비면 아직 품번으로 채운다")
ok("if not name and not pn:" in blk,
   "모델명도 품번도 없는 줄을 거르지 않는다")

# 빈 이름을 이름 목록에 넣으면 빈 이름끼리 전부 한 모델이 된다
ok("if name:\n                by_name.setdefault(name.lower(), entry)" in blk,
   "빈 이름을 by_name 에 넣는다 — 이름 없는 줄이 전부 한 모델로 합쳐진다")
ok("elif name:\n            existing = by_name.get(name.lower())" in blk,
   "품번 없이 이름도 빈 줄을 이름으로 찾고 있다")

# 모델명 열이 아예 없는 양식으로 올렸을 때 기존 이름을 지우면 안 된다
ok('if col_map.get("name"):\n                    existing["name"] = name' in blk,
   "모델명 열이 없는 양식을 올려도 이름을 덮어쓴다")

# 앱은 빈 이름을 품번으로 대신 보여준다
ok(HELP.exists(), "앱의 모델 이름 헬퍼(utils/model_name.dart)가 없다")
H = HELP.read_text(encoding="utf-8") if HELP.exists() else ""
ok("String modelDisplayName(Map m)" in H, "헬퍼에 modelDisplayName 이 없다")
ok("m['part_number']" in H, "헬퍼가 품번으로 대신하지 않는다")
ok("m['name']?.toString() ?? ''" not in DART,
   "모델 목록이 아직 이름을 그대로 그린다 — 빈 줄이 보인다")

# ?? 는 null 만 잡는다. 빈 문자열은 그대로 통과해서 빈 줄이 된다.
for f in ("model_cost_detail_screen.dart", "model_cost_list_screen.dart",
          "model_list_screen.dart"):
    t = (MOB / "screens" / f).read_text(encoding="utf-8")
    ok("modelDisplayName(" in t, "%s 가 헬퍼를 안 쓴다" % f)
    # 모델을 담는 변수만 본다. e['name'] 은 공정 단계 이름이라 해당 없다.
    import re as _re
    stray = _re.findall(r"\b(?:m|model)\['name'\]\s*\?\?", t)
    ok(not stray,
       "%s 에 아직 모델 이름을 `?? ` 로 받는 곳이 %d군데 있다 — "
       "?? 는 null 만 잡아서 빈 이름이 빈 줄로 보인다" % (f, len(stray)))

# ── 저장(PUT)도 이름 없는 모델을 버리면 안 된다 ──
#
# 임포터만 고치고 저장을 안 고쳤더니, 화면이 그 줄을 돌려보내는 순간
# 서버가 버렸다. 81종 중 13종이 사라질 뻔했고 409 경고로만 드러났다.
j = SRC.find('@app.put("/admin/projects/{project_key}/models")')
ok(j > 0, "모델 저장(PUT)이 없어졌다")
put = SRC[j:j + 3000]
ok("if not mid or not name:" not in put,
   "저장이 아직 이름 없는 모델을 버린다 — 화면에서 저장만 눌러도 사라진다")
ok("if not mid:" in put, "id 없는 줄을 거르지 않는다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과 · 빈 모델명은 비워 두고, 앱에서만 품번으로 보여준다")
