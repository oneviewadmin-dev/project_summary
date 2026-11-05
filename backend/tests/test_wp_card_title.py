# 모델별 주차별 계획 카드 제목 — 사업부가 정한 '주 이름' 을 쓴다 (2026-10-27).
#
# Min: "하바 같은 경우에는 품목이 소재명으로 되어 있어서 파트넘버 기준으로
#      보이게끔 해줘"
#
# 하바플레이트는 '모델명' 칸에 **소재**를 적는다 (양식에도 '*하바플레이트
# 경우 소재 입력' 이라고 쓰여 있다). 그래서 74개 카드가 전부 'PC (Dynex)'
# 로 떠서 어느 것이 어느 품목인지 가릴 수 없었다.
#
# 사업부마다 무엇이 주 이름인지는 서버가 안다 (division_columns 의 primary).
# 모델 목록 표가 이미 그 값을 쓰므로, 카드도 같은 것을 봐야 한다 —
# 한쪽만 고치면 같은 모델이 두 이름으로 뜬다.
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "..", "admin_v2.html")
sys.path.insert(0, os.path.join(HERE, ".."))

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


src = io.open(HTML, encoding="utf-8").read()

# ── 1. 제목을 고르는 자리가 따로 있다
ok("function _wpTitle(m)" in src, "_wpTitle 이 없다")
ok("sp.primary === 'part_number'" in src,
   "사업부 열 구성(primary)을 안 본다 — 모델 목록과 다른 이름이 뜬다")
ok("(m.name || m.id) + '</span>'" not in src,
   "카드가 아직 이름을 그대로 쓴다")

# ── 2. 서버가 반도체는 파트넘버를 주 이름으로 준다
import division_columns as dcol      # noqa: E402

ok(dcol.columns_for("semiconductor")["primary"] == "part_number",
   "서버가 반도체 주 이름을 파트넘버로 안 준다")
ok(dcol.columns_for("ess")["primary"] == "name",
   "서버가 고객사형 주 이름을 품목으로 안 준다")

# ── 3. 실제로 돌려 본다 (node)
try:
    subprocess.run(["node", "-v"], capture_output=True, check=True)
    has_node = True
except Exception:
    has_node = False

if has_node:
    a = src.index("  function _wpTitle(m) {")
    b = src.index("  function _wpBuildCard(m, idx, no) {")
    part = src[a:b]
    js = """
const code = %s + '\\n; module.exports = { T: _wpTitle };';
function run(div, spec, m) {
  const mod = { exports: {} };
  new Function('module', 'document', 'window', code)(mod,
    { getElementById: () => (div ? { value: div } : null) }, { _mdlColSpec: spec });
  return mod.exports.T(m);
}
const SP = { semiconductor: { primary: 'part_number' }, ess: { primary: 'name' } };
const hrva = { id: '713-312133-006', part_number: '713-312133-006', name: 'PC (Dynex)' };
const out = {
  semi:   run('semiconductor', SP, hrva),
  cust:   run('ess', SP, { id: 'SBB', part_number: '', name: 'SBB 1.5' }),
  group:  run('semiconductor', SP, { id: '__group__', name: '개발 (합계)' }),
  same:   run('semiconductor', SP, { id: 'c', part_number: '715-1', name: '715-1' }),
  nospec: run(null, null, hrva),
  esc:    run('semiconductor', SP, { id: 'x', part_number: '<b>P</b>', name: 'n' }),
};
console.log(JSON.stringify(out));
""" % json.dumps(part)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True)
    finally:
        os.unlink(path)
    if r.returncode != 0:
        bad.append("카드 제목을 그리다 터졌다: %s" % (r.stderr or "")[-300:])
    else:
        g = json.loads(r.stdout.strip().splitlines()[-1])
        ok(g["semi"]["main"] == "713-312133-006",
           "반도체 카드 제목이 파트넘버가 아니다 (%s)" % g["semi"])
        ok(g["semi"]["sub"] == "PC (Dynex)",
           "소재를 부제목으로 안 남겼다 — 적어 둔 값이 화면에서 사라진다")
        ok(g["cust"]["main"] == "SBB 1.5",
           "고객사형은 품목이 주 이름이어야 한다 (%s)" % g["cust"])
        ok(g["group"]["main"] == "개발 (합계)",
           "'개발 (합계)' 줄에 id(__group__)가 떴다 (%s)" % g["group"])
        ok(g["same"]["sub"] == "",
           "품번과 이름이 같은데 두 번 찍었다 (%s)" % g["same"])
        ok(g["nospec"]["main"] == "PC (Dynex)",
           "열 구성을 못 받았을 때 옛 동작으로 안 돌아간다 (%s)" % g["nospec"])
        ok("<b>" not in g["esc"]["main"],
           "엑셀에서 온 꺾쇠를 그대로 넣는다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_wp_card_title%s" % ("" if has_node else " (node 없음 — 그림 검사 건너뜀)"))
