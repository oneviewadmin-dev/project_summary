# 매출 관리 화면은 '실적 + 타겟' 둘로만 선다 (2026-10-27).
#
# Min: "실적이랑 타겟만 두면 되고 예상은 빼도 돼".
#
# 반도체만 Estimate 파일이 있어서 예상 칸을 만들어 뒀는데, 다른 사업부는
# 그런 파일이 없다. 사업부마다 칸이 다르면 같은 화면을 보면서 서로 다른
# 이야기를 하게 된다. 표의 '달성' 칸도 같이 내린다 — 그 칸은 실적 ÷
# **예상** 이라 예상이 없으면 늘 '-' 인 빈 칸만 남는다.
#
# 지운 게 아니라 끈 것이므로(RV_ESTIMATE_ON), 이 검사는 '꺼져 있는가' 와
# '켜면 돌아오는가' 를 같이 본다.
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "..", "admin_v2.html")

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


src = io.open(HTML, encoding="utf-8").read()

# ── 1. 스위치가 있고 꺼져 있다
ok("var RV_ESTIMATE_ON = false;" in src,
   "RV_ESTIMATE_ON 이 없거나 켜져 있다 — 예상 칸이 다시 보인다")

# ── 2. 예상 칸이 스위치를 거치지 않고 그려지는 자리가 없다
ok("kpi('이번 달 예상'" not in src.replace("? kpi('이번 달 예상'", ""),
   "'이번 달 예상' KPI 가 스위치 밖에서 그려진다")
ok("'<th>예상</th><th>달성</th>" not in src.replace(
       "(RV_ESTIMATE_ON ? '<th>예상</th><th>달성</th><th>　</th>' : '')", ""),
   "표 머리글의 예상·달성이 스위치 밖에서 그려진다")

# ── 3. 넣는 고리는 지우지 않았다 (켜면 그대로 돌아와야 한다)
for need, why in [
    ("rv-est-pick", "예상 파일 버튼 id 가 사라졌다"),
    ("rv-est-file", "예상 파일 입력 id 가 사라졌다"),
    ("function sendEst(", "예상 파일 보내는 함수가 사라졌다"),
]:
    ok(need in src, why + " — 스위치를 켜도 안 돌아온다")


# ── 4. 실제로 그려 본다. 켰을 때와 껐을 때 칸 수가 맞는가.
#      (칸 수가 머리글과 본문에서 어긋나면 표가 통째로 밀린다)
def render(force_on):
    a = src.index("  var RV_ESTIMATE_ON = false;")
    b = src.index("  function wire(d) {", a)
    part = src[a:b]
    if force_on:
        part = part.replace("var RV_ESTIMATE_ON = false;",
                            "var RV_ESTIMATE_ON = true;")
    js = """
const part = %s;
const code = 'var _open = {g1:true}, _month = "2026-10", _pick = null, _busy = false;'
  + part + '\\n; module.exports = { view, RV_ESTIMATE_ON };';
const m = { exports: {} };
new Function('module', 'document', 'window', 'fetch', code)(
  m, { getElementById: () => null }, {}, () => Promise.resolve());
const d = {
  month: '2026-10', months_all: ['2026-10'],
  actual: 8038256, as_of: 'W42',
  has_estimate: false, estimate: 0,
  has_target: true, target: 35000000, target_rate: 23,
  ytd: 149611234,
  sources: { weekly: { file: 'a.xlsx', at: '2026-10-19T07:02', year: 2026,
                       weeks: 52, lines: 53 } },
  groups: [{ key: 'g1', label: '반도체', actual: 5659609, items_actual: 5659609,
             estimate: 0, rate: null,
             items: [{ item: 'CUP', cust: 'CUP', actual: 1000 }] }],
  subtotal: { label: '소계', actual: 5958180, estimate: 0, rate: null },
  internal: { key: 'g2', label: '구미', actual: 2080076, items_actual: 2080076,
              estimate: 0, rate: null, items: [] },
  grand: { label: '총합', actual: 8038256, estimate: 0, rate: null },
};
const html = m.exports.view(d);
const head = (html.match(/<thead>[\\s\\S]*?<\\/thead>/) || [''])[0];
const body = (html.match(/<tbody>[\\s\\S]*?<\\/tbody>/) || [''])[0];
const out = {
  th: (head.match(/<th[ >]/g) || []).length,
  tds: body.split('<tr').slice(1).map(t => (t.match(/<td[ >]/g) || []).length),
  kpi: (html.match(/class="ov-kpi/g) || []).length,
  grid: Number((html.match(/grid-template-columns:repeat\\((\\d)/) || [])[1]),
  slots: (html.match(/class="rv-slot[ "]/g) || []).length,
  hasEst: /예상/.test(html),
};
console.log(JSON.stringify(out));
""" % _js_str(part)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(js)
        path = f.name
    try:
        out = subprocess.run(["node", path], capture_output=True, text=True)
    finally:
        os.unlink(path)
    if out.returncode != 0:
        return {"error": (out.stderr or "")[-400:]}
    import json as _json
    return _json.loads(out.stdout.strip().splitlines()[-1])


def _js_str(t):
    import json as _json
    return _json.dumps(t)


# node 가 없으면 그림 검사는 건너뛴다 (문자열 검사만으로도 되돌아감은 잡힌다)
try:
    subprocess.run(["node", "-v"], capture_output=True, check=True)
    has_node = True
except Exception:
    has_node = False

if has_node:
    off = render(False)
    ok("error" not in off, "꺼진 화면을 그리다 터졌다: %s" % off.get("error"))
    if "error" not in off:
        ok(off["th"] == 2, "껐을 때 머리글이 2칸이어야 하는데 %d칸" % off["th"])
        ok(set(off["tds"]) == {2},
           "껐을 때 본문 칸 수가 머리글과 다르다 (%s)" % off["tds"])
        ok(off["kpi"] == 4, "껐을 때 KPI 가 4개여야 하는데 %d개" % off["kpi"])
        ok(off["grid"] == 4, "껐을 때 KPI 칸이 4열이 아니다 (%s)" % off["grid"])
        ok(off["slots"] == 2,
           "껐을 때 올리기 칸이 실적·타겟 둘이어야 하는데 %d개" % off["slots"])
        ok(not off["hasEst"], "껐는데 화면에 '예상' 글자가 남아 있다")

    on = render(True)
    ok("error" not in on, "켠 화면을 그리다 터졌다: %s" % on.get("error"))
    if "error" not in on:
        ok(on["th"] == 5, "켰을 때 머리글이 5칸이어야 하는데 %d칸" % on["th"])
        ok(set(on["tds"]) == {5},
           "켰을 때 본문 칸 수가 머리글과 다르다 (%s)" % on["tds"])
        ok(on["kpi"] == 5, "켰을 때 KPI 가 5개여야 하는데 %d개" % on["kpi"])
        ok(on["slots"] == 3, "켰을 때 올리기 칸이 3개여야 하는데 %d개" % on["slots"])

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_revenue_no_estimate%s" % ("" if has_node else " (node 없음 — 그림 검사 건너뜀)"))
