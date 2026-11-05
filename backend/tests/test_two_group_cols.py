# -*- coding: utf-8 -*-
"""'구분' 칸이 둘인 양식 (2026-10-26).

아리스타 양식에는 구분이 둘이다.

    구분 1  시트메탈 · 렉 · 샷시 · 캐스팅 · 하드웨어   ← 무엇으로 만드나
    구분 2  양산 · 개발                              ← 어느 단계인가

머리글이 둘 다 '구분' 이라 왼쪽부터 집으면 '샷시' 가 구분으로 들어온다.
양산도 개발도 아니니 전부 '양산' 으로 떨어져서, 개발 59건이 양산으로
둔갑했다. 양산은 판가×수량, 개발은 고정단가로 매출을 잡으니 숫자가
통째로 틀어진다. 블룸 양식도 같은 모양이라 같이 틀리고 있었다.

머리글로는 못 가린다. **값을 보고** 가린다 — 양산/개발이 적힌 칸이
구분이고, 남은 칸은 분류로 쓴다 (반도체 양식의 HVM/RPM 자리).
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
sys.path.insert(0, BACK)

import division_form_import as dfi      # noqa: E402

FAIL = []


def ok(c, why):
    if not c:
        FAIL.append(why)


try:
    import openpyxl
except Exception:
    openpyxl = None

FORMS = os.path.join(HERE, "forms", "v2")


def parse(name, div):
    f = os.path.join(FORMS, name + ".xlsx")
    if not openpyxl or not os.path.exists(f):
        return None
    return dfi.parse_workbook(openpyxl.load_workbook(f, data_only=True), div)


# ── 아리스타 양식 '구분 1 + 구분 2' 판 (2026-10-23 첫 장)
#    구분 1 을 집으면 개발 59건이 전부 양산으로 둔갑한다.
g = parse("아리스타_실제_1023", "arista")
if g:
    grp = Counter(i["group"] for i in g["items"])
    ok(grp.get("개발") == 59 and grp.get("양산") == 31,
       "구분을 잘못 읽었다 (구분 1 을 집으면 전부 양산이 된다): %r" % dict(grp))
    cls = Counter(i["dev_type"] for i in g["items"])
    ok(cls.get("샷시") == 74, "남은 구분(구분 1)을 분류로 안 쓴다: %r" % dict(cls))

# ── 지금 쓰는 아리스타 양식 (구분 하나 · 파트넘버가 모델명 앞)
g2 = parse("아리스타_실제_1023b", "arista")
if g2:
    ok(len(g2["items"]) == 90, "품목을 90건 읽어야 하는데 %d건" % len(g2["items"]))
    grp2 = Counter(i["group"] for i in g2["items"])
    ok(grp2.get("개발") == 59 and grp2.get("양산") == 31,
       "구분이 하나인 양식에서 구분을 잘못 읽었다: %r" % dict(grp2))
    ok(g2["weeks"] == ["W41", "W42", "W43", "W44"], "주차를 %r 로 읽었다" % g2["weeks"])
    ok(g2["month"] == "2026-10", "달을 %r 로 읽었다" % g2["month"])
    ok(len({i["owner"] for i in g2["items"]}) == 27,
       "프로젝트를 %d개로 읽었다 (27개여야 한다)" % len({i["owner"] for i in g2["items"]}))
    ok(not g2["warnings"], "경고가 떴다: %r" % g2["warnings"])
    # 파트넘버가 모델명보다 앞이다 — 둘이 뒤바뀌면 표가 통째로 어긋난다
    _l = [i for i in g2["items"] if i["owner"] == "Lodoga"]
    ok(_l and _l[0]["part_number"].startswith("ASY-"),
       "파트넘버를 못 읽었다: %r" % (_l[0] if _l else None))
    ok(sum(1 for i in g2["items"] if i["name"]) == 46,
       "모델명이 적힌 줄을 %d건으로 읽었다 (46건이어야 한다)"
       % sum(1 for i in g2["items"] if i["name"]))

# ── 블룸도 같은 모양이었다 (함체 · 시트메탈 / 양산 · 개발)
b = parse("블룸_실제_2026-10", "bloom")
if b:
    grp = Counter(i["group"] for i in b["items"])
    ok(grp.get("개발", 0) > 0,
       "블룸 양식의 개발 줄이 전부 양산으로 둔갑했다: %r" % dict(grp))
    cls = Counter(i["dev_type"] for i in b["items"])
    ok(cls.get("시트메탈", 0) > 0, "블룸 분류를 안 읽는다: %r" % dict(cls))

# ── 구분이 하나뿐인 양식은 그대로여야 한다
for name, div in (("PCB", "pcb"), ("네트워크", "network"),
                  ("자동차", "automotive"), ("ESS", "ess")):
    x = parse(name, div)
    if not x:
        continue
    grp = Counter(i["group"] for i in x["items"])
    ok(set(grp) <= {"양산", "개발"}, "%s 구분이 깨졌다: %r" % (name, dict(grp)))
    ok(grp.get("개발", 0) >= 1, "%s 의 개발 줄을 못 읽는다: %r" % (name, dict(grp)))

# ── 값으로 못 가리면 옛 동작(왼쪽부터)
src = __import__("io").open(os.path.join(BACK, "division_form_import.py"),
                            encoding="utf-8").read()
ok("group_cands" in src, "'구분' 후보를 모으지 않는다")
ok("best = group_cands[0]" in src,
   "값으로 못 가릴 때 돌아갈 자리가 없다 — 양식이 바뀌면 구분이 통째로 빈다")
ok('if "dev_type" not in cols and rest:' in src,
   "'분류' 칸이 따로 있는 양식(반도체)에서 남은 구분이 분류를 덮는다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 구분이 둘인 양식")

# ======================================================================
#  아리스타를 앱에서 켠다 (2026-10-26)
#
#  프로젝트 키는 양식이 만든다 — arista_lodoga · arista_banff …
#  그래서 키를 하나씩 적을 수가 없다. 접두사로 켠다.
# ======================================================================
_cfg = __import__("io").open(
    os.path.join(os.path.dirname(BACK), "mobile", "lib", "config", "app_config.dart"),
    encoding="utf-8").read()
ok("'arista_'," in _cfg, "앱에서 아리스타 주차 보드를 안 켰다")
ok("'ess_'," in _cfg, "양식으로 새로 생긴 ESS 프로젝트가 꺼져 있다")
ok("'pcb_'," in _cfg, "PCB 프로젝트에 주차 현황 보드가 안 뜬다")
ok("endsWith('_')" in _cfg, "접두사로 켜는 길이 없다 — 키를 하나씩 적어야 한다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 아리스타 켜기")
