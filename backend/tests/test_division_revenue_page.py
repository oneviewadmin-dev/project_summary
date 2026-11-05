# 사업부 매출 관리도 반도체와 같은 화면 (2026-10-28)
#   python3 backend/tests/test_division_revenue_page.py
#
# Min: "다른 사업부 매출 관리도 반도체사업부처럼 동일하게 적용시켜줘"
#
# 전에는 반도체만 'KPI 네 칸 · 자료 올리기 · 매출 정리' 였고 다른 사업부는
# 생김새가 다른 화면이었다. 사이드바에서 사업부를 바꿀 때마다 눈이 다시
# 적응해야 했다. 같은 일을 하는 화면은 같게 둔다.
#
# node 로 dvView 를 꺼내 실제로 그려 본다. 글자만 grep 하면, 함수가 중간에
# 터져서 화면이 안 나와도 통과한다.
import json, os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 서버가 반도체 화면과 같은 칸을 채우는가 ────────────────────
_v = SRC[SRC.index('def _div_revenue_view'):]
_v = _v[:_v.index('\n@app.') if '\n@app.' in _v else len(_v)]
for key in ('"ytd"', '"as_of"', '"target_rate"', '"revenue_file"'):
    ok(key in _v, '사업부 매출에 %s 칸이 없다 — 반도체 화면과 칸이 다르다' % key)
# 연간 누적도 '파일 먼저, 없으면 계산' 같은 규칙으로 센다
_y = SRC[SRC.index('def _div_ytd_money'):]
_y = _y[:_y.index('\ndef _div_revenue_view')]
ok('_drev.month_usd(div, key)' in _y, '연간 누적이 매출 파일을 안 본다')
ok('_div_actual_money(models, key)' in _y, '연간 누적이 파일 없는 달을 못 센다')

# ── 2. 화면을 실제로 그려 본다 ───────────────────────────────────
NODE = shutil.which('node')
if NODE:
    harness = r'''
const fs=require('fs');
const s=fs.readFileSync(process.argv[2],'utf8');
function grab(name){
  const k='function '+name+'(';
  const i=s.indexOf(k);
  if(i<0) throw new Error('못 찾음 '+name);
  let d=0, j=s.indexOf('{',i);
  for(let p=j;p<s.length;p++){
    if(s[p]==='{')d++;
    else if(s[p]==='}'){d--; if(d===0) return s.slice(i,p+1);}
  }
  throw new Error('끝 못 찾음 '+name);
}
let code='';
for(const n of ['dvView','dvMoney','kpi','pct','bar','_rvMoney','monthOptions','esc'])
  code+=grab(n)+'\n';
code+='\nreturn {dvView};';
const dv=new Function('RV_ESTIMATE_ON','_dvOpen', code)(false,{}).dvView;
const D=JSON.parse(process.argv[3]);
process.stdout.write(dv(D));
'''
    hp = pathlib.Path(tempfile.mkdtemp(prefix='dvh_')) / 'h.js'
    hp.write_text(harness, encoding='utf-8')
    try:
        FULL = {
            "label": "ESS사업부", "month": "2026-10",
            "actual": 53727080, "actual_source": "매출 파일",
            "target": 61200000, "has_target": True,
            "target_source": "그 달 계획 합계", "target_editable": True,
            "rate": 88, "ytd": 399861720, "counts": {"total": 13},
            "months_all": [],
            "revenue_file": {"file": "ESS매출.xlsx", "at": "2026-10-28T04:00:00",
                             "months": ["2026-09", "2026-10"], "rows": []},
            "projects": [
                {"id": "ess_sdi", "label": "SDI", "models": 4,
                 "po_qty": 2262, "shipped_qty": 1901, "money": 30100000},
                {"id": "ess_epc", "label": "EPC POWER", "models": 1,
                 "po_qty": 2752, "shipped_qty": 1463, "money": 0}],
        }

        def draw(d):
            r = subprocess.run([NODE, str(hp), str(ROOT / 'admin_v2.html'),
                                json.dumps(d, ensure_ascii=False)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                FAIL.append('화면이 안 그려진다: %s' % (r.stderr or '')[-300:])
                return ''
            return r.stdout

        h = draw(FULL)
        # 반도체 화면과 같은 칸·같은 class
        for k in ('이번 달 실적', '이번 달 타겟', '타겟 달성', '연간 누적',
                  '자료 올리기', '매출 정리', 'ov-kpi', 'rv-slot', 'wb-tbl'):
            ok(k in h, '사업부 화면에 %r 가 없다 — 반도체와 다르게 생겼다' % k)
        # 숫자가 실제로 찍히는가
        for k in ('$53,727,080', '$61,200,000', '88%', '$399,861,720',
                  'ESS매출.xlsx', '총합'):
            ok(k in h, '화면에 %r 가 안 찍힌다' % k)
        # 올리는 자리와 타겟 적는 자리
        for k in ('dv-rvf-pick', 'dv-target', 'dv-save'):
            ok(k in h, '%s 단추가 없다' % k)

        # ── 매출 정리는 **매출 파일의 구분** 그대로 (2026-10-28)
        #
        # Min: "반도체사업부도 보면 내가 있는 품목이 아니더라도 매출 관리
        #      파일 기준으로 구분이 나눠져 있잖아 다른 사업부들도 다
        #      동일하게 해줘"
        DET = dict(FULL)
        DET['detail'] = {
            'groups': [
                {'key': 'g0', 'label': '제품 매출 금액', 'actual': 5023295, 'items': []},
                {'key': 'cust', 'label': '고객사별', 'actual': 3881213,
                 'items': [{'item': 'SAMSUNG', 'actual': 1408548}]},
            ],
            'subtotal': {'label': 'Sub-total', 'actual': 9394690},
            'internal': {'label': '내부거래 (Internal)', 'actual': 100664},
            'grand': {'label': '총합 (내부거래 포함)', 'actual': 9495354},
        }
        hd = draw(DET)
        for k in ('제품 매출 금액', '고객사별', 'Sub-total',
                  '내부거래 (Internal)', '총합 (내부거래 포함)',
                  '$9,495,354', '$5,023,295'):
            ok(k in hd, '매출 정리에 %r 가 없다' % k)
        ok('data-dv-grp' in hd, '묶음을 펼칠 수가 없다')
        # 세부는 접혀 있어야 한다 — 펴 둔 묶음만 보인다
        ok('SAMSUNG' not in hd, '안 펼친 묶음의 세부가 그대로 보인다')
        ok('매출 파일이 적어 둔 구분 그대로입니다' in hd, '어디서 온 표인지 안 적는다')

        # 파일이 없는 달은 프로젝트별로 떨어지고, 왜 $0 인지 알려 준다
        ok('판가 × 그 달 실적' in h, '파일 없는 달에 출처를 안 적는다')
        ok('실적 수량이 비어 있으면 $0 으로 보입니다' in h, \
           '$0 인 까닭을 안 알려 준다')

        # 매출 파일이 없는 사업부도 깨지지 않는다
        BARE = dict(FULL)
        BARE.update({"revenue_file": {"file": "", "at": "", "months": [], "rows": []},
                     "actual_source": "판가 × 그 달 실적",
                     "has_target": False, "target": 0, "rate": None})
        h2 = draw(BARE)
        ok('아직 올린 파일이 없습니다' in h2, '파일 없는 사업부 안내가 없다')
        ok('타겟을 넣으면 나옵니다' in h2, '타겟 없을 때 안내가 없다')
        ok('판가 × 그 달 실적' in h2, '실적이 어디서 왔는지 안 적는다')
        # 프로젝트가 없어도 화면은 떠야 한다
        NONE = dict(BARE); NONE['projects'] = []
        h3 = draw(NONE)
        ok('등록된 프로젝트가 없습니다' in h3, '프로젝트 없는 사업부에서 표가 빈다')
        ok('매출 정리' in h3, '프로젝트가 없다고 카드가 통째로 사라졌다')
    finally:
        shutil.rmtree(hp.parent, ignore_errors=True)
else:
    print('(node 없음 — 그려 보기는 건너뜀)')

# ── 3. 옛 화면 조각이 남아 있지 않은가 ───────────────────────────
ok('<div class="dv-kpis">' not in HTML, '옛 사업부 KPI 줄이 아직 남아 있다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 사업부 매출 관리가 반도체와 같은 화면')
