# 양식 다섯 장 중 '용어' 와 '공정별 일일 실적' 도 읽는다 (2026-10-27).
#
# Min: "일단 틀 잡힌 엑셀들 기준으로 만들어줘"
#
# 양식은 다섯 장이다 — 품목정보 · 개발 프로세스 · 일일 실적 · 이슈사항 · 용어.
# 지금까지 품목과 이슈 둘만 읽고 나머지는 말없이 버렸다. 올린 사람은
# '용어도 적었는데 들어갔나' 를 알 길이 없었고, 모르면 다음부터 안 적는다.
# (개발 프로세스는 아직 양식이 확정 전이라 뺀다)
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import openpyxl                      # noqa: E402
import division_form_import as dfi   # noqa: E402

FORMS = os.path.join(HERE, "forms", "v2")
bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


def load(name, div):
    p = os.path.join(FORMS, name)
    if not os.path.exists(p):
        bad.append("양식이 없다: %s" % name)
        return None
    return dfi.parse_workbook(openpyxl.load_workbook(p, data_only=True),
                              division_id=div)


# ── 1. 용어 — PCB 실제 양식에 한 줄 적혀 있다
g = load("PCB_실제_1023.xlsx", "pcb")
if g:
    ok(len(g["terms"]) == 1, "PCB 용어 1건을 못 읽었다 (%d건)" % len(g["terms"]))
    if g["terms"]:
        t = g["terms"][0]
        ok(t["short"] == "MPS", "약어를 잘못 읽었다 (%r)" % t["short"])
        ok("Master Production Schedule" in t["full"], "Full Name 을 못 읽었다")
        ok("생산계획" in t["ko"], "한국어 뜻을 못 읽었다")
        ok(t["note"], "비고를 못 읽었다")

    # ── 2. 일일 실적 — 날짜 칸을 '있는 만큼' 읽는다
    ok(len(g["daily"]) == 6, "PCB 일일 실적 6줄을 못 읽었다 (%d줄)" % len(g["daily"]))
    ok(len(g["daily_dates"]) >= 2,
       "날짜 칸을 못 읽었다 (%s)" % g["daily_dates"])
    if g["daily"]:
        r = g["daily"][0]
        ok(r["owner"] == "SDI", "고객사를 못 읽었다 (%r)" % r["owner"])
        ok(r["step"] == "제관/용접", "공정을 못 읽었다 (%r)" % r["step"])
        ok(r["ship_wait"] == 12, "출하 대기를 못 읽었다 (%r)" % r["ship_wait"])
        ok(r["days"], "날짜별 계획·실적이 비어 있다")
        ok(all(r2["example"] for r2 in g["daily"]),
           "'예시)' 줄을 예시로 표시하지 않았다 — 반영하면 가짜 자료가 들어간다")
    # 0 과 빈 칸을 가린다 — 실적 0 은 '0 이라고 적었다' 는 뜻이다
    if g["daily"] and g["daily"][0]["days"]:
        cell = list(g["daily"][0]["days"].values())[0]
        ok(cell["actual"] == 0, "실적 0 을 0 으로 안 읽었다 (%r)" % cell["actual"])

# ── 3. 용어 시트가 비어 있어도 터지지 않는다 (반도체 네 장은 한 줄도 없다)
g2 = load("반도체_CUP_실제_1023.xlsx", "semiconductor")
if g2:
    ok(g2["terms"] == [], "빈 용어 시트에서 뭔가 읽혔다")
    ok(not g2["warnings"], "용어가 비었다고 경고를 냈다 — 비어 있는 게 보통이다")
    # 달력만 깔려 있고 자료가 없는 일일실적 시트
    ok(g2["daily"] == [], "빈 일일 실적에서 줄이 읽혔다")
    ok(len(g2["daily_dates"]) >= 28, "달력 날짜 칸을 못 읽었다 (%d)" % len(g2["daily_dates"]))

# ── 4. 블룸은 품목정보만 N열까지 읽는다. 그 제한이 다른 시트에 번지면 안 된다
#      (일일 실적의 날짜 칸은 K열부터라 14로 끊으면 통째로 사라진다)
src = io.open(os.path.join(HERE, "..", "division_form_import.py"),
              encoding="utf-8").read()
for fn in ("def parse_terms(", "def parse_daily("):
    i = src.index(fn)
    body = src[i:src.index("\ndef ", i + 10)]
    ok("_lastc(" not in body,
       "%s 가 품목정보용 열 제한을 쓰고 있다 — 다른 시트까지 잘린다" % fn)
    ok("ws.max_column" in body, "%s 가 시트 끝까지 안 읽는다" % fn)

# ── 5. 담는 쪽 — 빈 목록이 기존 용어를 지우면 안 된다
import division_terms as dt          # noqa: E402

ok(hasattr(dt, "put") and hasattr(dt, "get"), "용어 담는 모듈이 없다")
tsrc = io.open(os.path.join(HERE, "..", "division_terms.py"), encoding="utf-8").read()
ok("if not rows:\n        return 0" in tsrc,
   "빈 용어 목록이 와도 저장을 시도한다 — 한 번 적은 말이 다음 양식에 사라진다")
ok("DATA_DIR" in tsrc, "config/ 에 담는다 — 배포하면 덮인다")

msrc = io.open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
ok("_dterm.put(division_id" in msrc, "반영이 용어를 안 담는다")
ok('"terms": got.get("terms") or []' in msrc, "미리보기가 용어를 안 보여준다")
ok('@app.get("/divisions/{division_id}/terms")' in msrc, "용어를 내주는 창구가 없다")

html = io.open(os.path.join(HERE, "..", "admin_v2.html"), encoding="utf-8").read()
ok("용어 ' + tm.length + '건" in html, "미리보기 화면이 용어를 안 그린다")
ok("공정별 일일 실적 ' + dr + '줄" in html, "미리보기 화면이 일일 실적을 안 그린다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_form_terms_daily")
