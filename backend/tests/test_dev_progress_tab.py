# 개발 진행현황 탭 (2026-11-02)
#   python3 backend/tests/test_dev_progress_tab.py
#
# Min: "모델 목록, 주차별 계획, 개발 진행현황 이런식으로 나눠지고
#      개발 진행현황에 개발 일정 정리되어 있는거 한 눈에 보기 쉽게 정리
#      해야될 것 같은데"
#      "이 사이에 search toggle 있으면 좋을 것 같아"
#
# 품목 × 단계 격자. 칸 색이 곧 상태다 — 초록(실적) · 빨강(계획일 지남) ·
# 회색(계획) · 빈칸(날짜 없음). 색만으로 읽히면 안 되니 칸마다 날짜를
# 같이 적는다.
#
# node 로 실제로 그려 본다. 글자만 grep 하면 함수가 중간에 터져도 통과한다.
import json, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 탭과 판이 있는가 ───────────────────────────────────────────
ok('data-mtab="dev"' in HTML, '개발 진행현황 탭 단추가 없다')
ok('data-mpane="dev"' in HTML, '개발 진행현황 판이 없다')
ok('id="dv-prog-box"' in HTML, '그릴 자리가 없다')
# 들어올 때 그린다 — 처음부터 그리면 개발이 없는 프로젝트에서도 한 번 더 부른다
ok("if (t.dataset.mtab === 'dev' && window._devProgRender)" in HTML,
   '탭을 눌러도 안 그린다')

# ── 1-b. 단계 머리글은 똑바로 ────────────────────────────────────
# Min: "글씨 왜 upside down으로 되어 있고 공백이 왜이렇게 많냐"
# 한글은 세로쓰기(writing-mode)에서 글자가 '똑바로' 선 채 쌓인다.
# 거기에 rotate(180deg) 를 걸면 라틴문자는 밑에서 위로 읽히지만
# 한글은 글자 자체가 뒤집힌다. 그래서 세로쓰기를 아예 안 쓴다.
_css = HTML[HTML.find(".dvp-tbl th.st {"):HTML.find(".dvp-lg {")]
ok('writing-mode' not in _css, '단계 머리글이 세로쓰기다 — 한글이 뒤집힌다')
ok('rotate(180deg)' not in _css, '단계 머리글을 180도 돌렸다 — 거꾸로 보인다')
# 남는 가로폭을 품목 칸이 다 먹으면 가운데가 텅 빈다 — 진행률이 가져간다
# 남는 폭은 빈 칸(pad)이 먹는다. 진행률에 주면 막대가 쓸데없이 길어지고
# (Min: "진행률이 쓸때 없이 너무 길어"), 품목에 주면 가운데가 벌어진다.
ok('.dvp-tbl td.pad, .dvp-tbl th.pad { width:100%' in HTML,
   '남는 폭을 먹을 빈 칸이 없다 — 한 칸이 혼자 늘어난다')
ok('.dvp-tbl td.pg, .dvp-tbl th.pg { width:150px' in HTML,
   '진행률 칸에 폭 상한이 없다')
ok(HTML.count('<th class="pad">') == 1 and HTML.count('<td class="pad">') == 1,
   '빈 칸이 머리와 몸에 한 짝씩 있어야 한다')
ok('max-width:340px' in _css, '품목 칸에 상한이 없다')
# 남는 폭을 받는 칸은 하나뿐이어야 한다. 둘이면 반씩 나눠 가져서,
# 끈 줄 알았던 칸이 그래도 절반만큼 늘어난다 — 진행률이 그랬다.
_w100 = [c for c in _css.split("',") if 'width:100%' in c]
ok(len(_w100) == 1 and 'pad' in _w100[0],
   'width:100% 가 pad 말고 다른 칸에도 있다 — 남는 폭을 나눠 가진다')

# ── 2. 실제로 그려 본다 ──────────────────────────────────────────
NODE = shutil.which('node')
if NODE:
    harness = r'''
const fs=require('fs');
const s=fs.readFileSync(process.argv[2],'utf8');
const lines=s.split('\n');
const b=[]; lines.forEach((l,i)=>{const t=l.trim(); if(t==='<script>'||t==='</script>') b.push([i+1,t]);});
const t=s.slice(0,s.indexOf('window._devProgRender')).split('\n').length;
const a=b.filter(x=>x[0]<t).pop()[0], c=b.filter(x=>x[0]>t)[0][0];
const code=lines.slice(a,c-1).join('\n');
const els={};
function mk(id){return {id,_h:'',style:{},dataset:{},classList:{add(){},remove(){},toggle(){}},
  addEventListener(){},removeAttribute(){},setAttribute(){},getAttribute(){return null},
  querySelectorAll(){return []},querySelector(){return null},
  get innerHTML(){return this._h}, set innerHTML(v){this._h=v},
  get textContent(){return this._t||''}, set textContent(v){this._t=v},
  value:'',files:null,click(){},focus(){},setSelectionRange(){},remove(){},appendChild(){}};}
const document={getElementById:(id)=>els[id]||(els[id]=mk(id)),
  querySelector:()=>null,querySelectorAll:()=>[],createElement:()=>mk('x'),
  addEventListener(){},head:mk('head'),body:mk('body')};
const window={};
let lastUrl='';
const DATA=JSON.parse(process.argv[3]);
const fetch=(u)=>{lastUrl=u; return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(DATA)});};
const fn=new Function('document','window','fetch','setTimeout','alert','confirm','FormData','location','console',
  code+'\n;return {render: window._devProgRender};');
const out=fn(document,window,fetch,(f)=>f(),()=>{},()=>true,function(){this.append=()=>{}},{href:''},console);
out.render('p1');
setTimeout(()=>{process.stdout.write(lastUrl+'\u0000'+(els['dv-prog-box']._h||''));},0);
'''
    hp = pathlib.Path(tempfile.mkdtemp(prefix='dvp_')) / 'h.js'
    hp.write_text(harness, encoding='utf-8')
    DATA = {"models": [
        {"id": "A1", "name": "PC (Zelux M)", "part_number": "HP-001",
         "dev_type": "RPM", "group": "개발", "display_group": "개발",
         "frame": "개발", "progress": 69,
         "process": [{"name": "FA PO"}, {"name": "자재 발주"},
                     {"name": "FAIR 제출", "actual": "2026-09-16"},
                     {"name": "최종 승인 완료"}]},
        {"id": "A2", "name": "PC (Dynex)", "part_number": "HP-002",
         "dev_type": "RPM", "group": "개발", "display_group": "개발",
         "frame": "개발", "progress": 77,
         "process": [{"name": "FA PO"},
                     {"name": "LAIR 제출", "expected": "2026-06-09"},
                     {"name": "LAP TEST", "expected": "2099-11-30"},
                     {"name": "최종 승인 완료"}]},
        {"id": "A3", "name": "끝난 것", "part_number": "HP-003",
         "dev_type": "HVM", "group": "개발", "display_group": "개발",
         "frame": "개발", "progress": 100, "dev_owner": "김과장",
         # 계획과 실적이 둘 다 있는 품목. 하나는 늦고 하나는 당겼다.
         "process": [{"name": "FA PO",
                      "expected": "2026-01-05", "actual": "2026-01-02"},
                     {"name": "최종 승인 완료",
                      "expected": "2026-05-01", "actual": "2026-05-05"}]},
        {"id": "A4", "name": "날짜 없음", "part_number": "HP-004",
         "dev_type": "", "group": "개발", "display_group": "개발",
         "frame": "개발", "progress": None,
         # 날짜가 아닌 글자로 적힌 칸 — '고객사 검토중' · 'PO 완료'
         "process": [{"name": "FA PO", "expected_note": "고객사 검토중"},
                     {"name": "최종 승인 완료", "actual_note": "PO 완료"}]},
        # 양산 · 틀이 양산인 개발(아리스타)은 빠져야 한다
        {"id": "M1", "name": "양산품", "part_number": "HP-900",
         "group": "양산", "display_group": "양산", "frame": "양산", "process": []},
        {"id": "R1", "name": "아리스타개발", "part_number": "AR-1",
         "group": "개발", "display_group": "개발", "frame": "양산",
         "process": [{"name": "x"}]},
    ]}
    try:
        r = subprocess.run([NODE, str(hp), str(ROOT / 'admin_v2.html'),
                            json.dumps(DATA, ensure_ascii=False)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            FAIL.append('화면이 안 그려진다: %s' % (r.stderr or '')[-400:])
            h, url = '', ''
        else:
            url, _, h = r.stdout.partition('\x00')

        ok(url == '/projects/p1/models/detail', '엉뚱한 곳에서 불러온다: %r' % url)
        # 요약 타일
        for k in ('개발 품목', '마지막 단계 완료', '진행 중', '계획일 지남', '아직 날짜 없음'):
            ok(k in h, '요약 타일에 %r 가 없다' % k)
        # 찾기 · 거르기 줄
        for k in ('dvp-q', 'dvp-chip', 'data-dvf="late"', 'data-dvf="idle"'):
            ok(k in h, '찾기·거르기 줄에 %r 가 없다' % k)
        # 격자
        ok('품목 · 파트넘버 · 유형' in h, '머리글이 없다')
        ok('HP-001 · RPM' in h, '파트넘버·유형을 안 적는다')
        # 칸 네 가지 상태가 다 나와야 한다
        for k in ('class="c done"', 'class="c late"', 'class="c plan"', 'class="c none"'):
            ok(k in h, '%s 칸이 없다' % k)
        # 색만으로 읽히면 안 된다 — 날짜를 같이 적는다
        for k in ('09/16', '06/09', '11/30'):
            ok(k in h, '칸에 날짜 %r 가 안 적힌다' % k)
        ok('title="실적 2026-09-16"' in h, '칸에 올려도 전체 날짜가 안 뜬다')
        # 개발 품목만
        ok('양산품' not in h, '양산 품목이 격자에 들어왔다')
        ok('아리스타개발' not in h,
           '틀이 양산인 개발이 들어왔다 — 공정 단계가 없어 빈 줄만 선다')
        ok((h.count('class="nm"') - 1) == 4, '품목이 4줄이어야 한다')
        # 단계는 품목마다 다를 수 있다 — 이름으로 자리를 맞춘다
        ok('_dvpState.steps' in HTML and 'by[n] ? _dvpCell' in HTML,
           '단계를 순서로 맞춘다 — 3단계짜리가 엉뚱한 칸에 선다')
        ok('범례' in h or '실적 (완료)' in h, '범례가 없다')
        # ── 계획과 실적을 같이 적는다 ──────────────────────────
        # Min: "계획 작성된거 있으면 그것도 보이게끔 하고
        #      실적이 있으면 실적으로 작성하고"
        # 전에는 실적이 들어오는 순간 계획이 칸에서 사라졌다. 그러면
        # '언제 하기로 했는데 언제 했다' 를 볼 수가 없다.
        ok('01/02' in h and '<span class="pl">01/05</span>' in h,
           '실적 밑에 계획이 같이 안 적힌다')
        ok('title="실적 2026-01-02 · 계획 2026-01-05 · 당김"' in h,
           '칸에 올려도 계획 대비 당겼는지 안 뜬다')
        ok('title="실적 2026-05-05 · 계획 2026-05-01 · 늦음"' in h,
           '칸에 올려도 계획 대비 늦었는지 안 뜬다')
        # 계획만 있는 칸에는 밑줄이 붙으면 안 된다 — 같은 날짜가 두 번 뜬다
        ok('<td class="c late" title="계획 2026-06-09 · 지남">06/09</td>' in h,
           '계획만 있는 칸에 군더더기가 붙었다')

        # ── 개발 담당 주재원 ──────────────────────────────────
        # Min: "개발 담당 주재원도 보이게끔 해줘"
        # 양식은 읽고 있었지만 저장을 안 해서 올릴 때마다 버려졌다.
        ok('<th class="ow">담당</th>' in h, '담당 칸 머리글이 없다')
        ok('<td class="ow">김과장</td>' in h, '담당이 안 적힌다')
        # 안 적힌 품목은 빈 칸이 아니라 '—' 로 — 칸이 밀리면 표가 어긋난다
        ok(h.count('<td class="ow">') == 4, '담당 칸이 줄마다 하나씩 있어야 한다')
        ok('<td class="ow">—</td>' in h, '담당이 없는 줄에 자리가 안 잡힌다')
        ok('담당으로 찾기' in HTML, '담당으로 못 찾는다')

        # ── 날짜가 아닌 글자도 칸에 뜬다 ──────────────────────
        # Min: "엑셀에는 내용 다 적혀져 있고 ... 왜 적용을 못 하는거야"
        # 날짜만 그리던 때는 이런 칸이 '·' 로 비어 보였다.
        ok('고객사 검토중' in h, "계획 칸의 글자가 안 뜬다")
        ok('title="계획 고객사 검토중"' in h, '글자 칸에 올려도 설명이 없다')
        # 실적 칸에 '완료' 라고 적혔으면 끝난 칸으로 — 양식 머리의 규칙
        ok('class="c done txt"' in h and 'PO 완료' in h,
           "실적 '완료' 가 끝난 칸으로 안 그려진다")
        # 글자는 날짜보다 길다 — 줄바꿈이 막혀 있으면 칸이 터진다
        ok('.dvp-tbl td.c.txt' in HTML and 'white-space:normal' in HTML,
           '글자 칸이 한 줄로 눌려 칸을 밀어낸다')
        ok("r.type + ' ' + r.owner" in HTML, '찾기에 담당이 안 들어간다')
    finally:
        shutil.rmtree(hp.parent, ignore_errors=True)
else:
    print('(node 없음 — 그려 보기는 건너뜀)')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 개발 진행현황 탭')
