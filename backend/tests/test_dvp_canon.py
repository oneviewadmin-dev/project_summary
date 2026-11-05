# admin 개발 진행현황 — 같은 단계는 한 칸 (2026-11-05)
#   python3 backend/tests/test_dvp_canon.py
#
# Min: "CUP 모델에 개발 진행현황인데 왜 저렇게 정리가 되어 있는거야"
# CUP 개발 29종이 같은 13단계를 네 가지 이름으로 들고 있어서 칸이
# 'FA PO · 01 PO 접수 · 입고 · 입고 Material receipt · 03 자재 입고 …' 로 늘어섰다.
import json
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML = (ROOT / "admin_v2.html").read_text(encoding="utf-8")
assert "function _dvpCanon(" in HTML, "단계 이름을 맞추는 함수가 없다"
assert "var n = _dvpCanon(s.name);" in HTML, "칸을 세울 때 이름을 안 맞춘다"
assert HTML.count("_dvpCanon(s.name)") >= 2, "칸과 품목 칸이 다른 이름으로 맞춰진다"

CUP = [
    ["FA PO", "자재 발주", "입고", "가공 (조립)", "LA 입고", "LAIR 작성", "LAIR 승인",
     "Source Inspection", "FAIR 작성", "FAIR 승인", "LAP TEST", "CDR", "최종 승인 완료"],
    ["FA PO", "자재 발주 Material procurement", "입고 Material receipt",
     "가공 (조립) Processing (Assembly)", "LA 입고 LA receipt", "LAIR 작성 LAIR preparation",
     "LAIR 승인 LAIR approval", "Source Inspection", "FAIR 작성 FAIR preparation",
     "FAIR 승인 FAIR approval", "LAP TEST", "CDR", "최종 승인 완료 Fully approved"],
    ["FA PO", "자재 발주", "입고", "가공 (조립)", "LA 입고", "LAIR 제출", "LAIR 승인",
     "Source Inspection", "FAIR 제출", "FAIR 승인", "LAP TEST", "CDR", "최종 승인 완료"],
    ["01 PO 접수", "02 자재 발주", "03 자재 입고", "04 가공 (조립)", "05 LA 입고",
     "06 LAIR 작성", "07 LAIR 승인", "08 소스인스펙션 (SI)", "09 FAIR 작성",
     "10 FAIR 승인", "11 LAP 테스트", "12 CDR", "13 최종 승인 완료"],
]
OTHER = ["13 CDR/PRR 작성", "04 CB", "T-car 제작", "1차 시작품"]

if not shutil.which("node"):
    print("ok — (node 없음: 글자 검사만)")
    raise SystemExit(0)
JS = """
const fs = require('fs');
const h = fs.readFileSync(process.argv[2], 'utf8');
eval(h.slice(h.indexOf('var _DVP_SAME'), h.indexOf('window._dvpCanon')));
const v = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
console.log(JSON.stringify(v.map(r => r.map(_dvpCanon))));
"""
with tempfile.TemporaryDirectory() as d:
    js = pathlib.Path(d) / "c.js"
    js.write_text(JS, encoding="utf-8")
    data = pathlib.Path(d) / "v.json"
    data.write_text(json.dumps(CUP + [OTHER], ensure_ascii=False), encoding="utf-8")
    out = json.loads(subprocess.check_output(["node", str(js), str(ROOT / "admin_v2.html"), str(data)]))
got = out[:4]
assert all(r == got[0] for r in got), "네 가지 이름이 한 칸으로 안 모인다: %r" % got
assert len(set(got[0])) == 13, got[0]
assert got[0][0] == "PO 접수" and got[0][2] == "자재 입고" and got[0][7] == "소스인스펙션 (SI)", got[0]
# 모르는 이름은 번호만 떼고 그대로
assert out[4] == ["CDR/PRR 작성", "CB", "T-car 제작", "1차 시작품"], out[4]

# ── 칸은 틀대로 — 비어 있는 뒤 단계도 순서대로 선다 ───────────────
# Min: "… 최종 승인 완료 로 해주는거 아니야? 왜 FAIR 작성에서 끝났냐"
JS2 = """
const fs = require('fs');
const h = fs.readFileSync(process.argv[2], 'utf8');
eval(h.slice(h.indexOf('var _DVP_SAME'), h.indexOf('window._dvpCanon')));
const a = h.indexOf('var _stepHas = function');
const tail = 'if (!steps.length) steps = _allSteps;';
const b = h.indexOf(tail) + tail.length;
const dev = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
eval(h.slice(a, b));
console.log(JSON.stringify(steps));
"""
def P(names, filled):
    return {"process": [{"name": n, "actual": ("2026-01-01" if i in filled else "")}
                        for i, n in enumerate(names)]}
dev = ([P(CUP[2], {0, 1, 2, 4, 6})] * 3 +          # 앞 몇 칸만 적힘 — 가공 · LAIR 작성 비어 있음
       [P(CUP[3], {0, 3, 8})] +                   # 번호 틀
       [P(["T-car", "Proto"] + CUP[0][:2], set()),  # 빈 다른 틀 — 칸을 차지하면 안 된다
        P(CUP[0] + ["추가 검사"], {13})])           # 틀 밖 단계가 적혀 있으면 뒤에 붙는다
with tempfile.TemporaryDirectory() as d:
    js = pathlib.Path(d) / "c2.js"
    js.write_text(JS2, encoding="utf-8")
    data = pathlib.Path(d) / "dev.json"
    data.write_text(json.dumps(dev, ensure_ascii=False), encoding="utf-8")
    cols = json.loads(subprocess.check_output(["node", str(js), str(ROOT / "admin_v2.html"), str(data)]))
assert cols[:13] == got[0], "틀대로 13칸이 안 선다: %r" % cols
assert cols[13:] == ["추가 검사"], "틀 밖 단계 처리가 이상하다: %r" % cols
assert "T-car" not in cols, "빈 다른 틀이 칸을 차지했다"
print("ok — 같은 단계는 한 칸 · 칸은 틀대로 13칸 (CUP)")
