# 엑셀 메뉴 동기화 + breadcrumb 사업부
#   python3 backend/tests/test_admin_v2_menu.py
#
# 둘 다 '한 번만 맞추고 끝'이라 생긴 문제였다.
#   - 엑셀 메뉴: 툴바가 다시 그려지면 hidden 이 마크업 기본값으로 돌아갔다
#   - breadcrumb: '반도체사업부' 가 박혀 있고 사업부를 바꿔도 그대로였다
import json, os, pathlib, re, subprocess, tempfile

HTML = (pathlib.Path(__file__).resolve().parents[1] / 'admin_v2.html').read_text(encoding='utf-8')
ok = 0

# ── 호출 지점이 살아 있는지 ────────────────────────────────────────
assert "importBtn.addEventListener('click', function(e) {" in HTML
_open = HTML[HTML.index("importBtn.addEventListener('click'"):][:500]
assert 'window._bdSyncMenu' in _open, '메뉴를 열 때 동기화하지 않는다'
ok += 1

_chg = HTML[HTML.index("sidebarSel.addEventListener('change'"):][:300]
assert 'window._v2SyncCrumbBiz' in _chg, '사업부를 바꿀 때 breadcrumb 을 안 고친다'
ok += 1
assert HTML.count('window._v2SyncCrumbBiz()') >= 3, \
    'breadcrumb 동기화 호출이 모자란다 (페이지 이동·사업부 변경·첫 로드)'
ok += 1

if subprocess.run(['node', '--version'], capture_output=True).returncode != 0:
    print(f'전부 통과 ({ok}/{ok}) · node 없어 동작 검사는 건너뜀'); raise SystemExit(0)

def grab(name):
    i = HTML.index('window.%s = function' % name)
    j = HTML.index('\n  };', i)
    return HTML[i:j + 5]

JS = """
var els = {
  'v2-crumb-biz': {textContent: '반도체사업부'},
  'v2-division-select': {selectedIndex: 1,
    options: [{text:'반도체사업부'}, {text:'블룸'}], value: 'bloom'},
  'mdl-bloom-btn': {hidden: true, dataset: {}, onclick: null},
  'mdl-lead-btn': {hidden: false},
  
  'mdl-proc-reset-btn': {hidden: false},
  'mdl-import-menu': {hidden: true},
  'pf-file': {clicked: 0, click: function(){ this.clicked++; }}
};
var seps = [{hidden:false},{hidden:false}];
var document = {
  getElementById: function(id){ return els[id] || null; },
  querySelectorAll: function(){ return { forEach: function(f){ seps.forEach(f); } }; }
};
var window = { _bdWireUpload: function(){}, _ovProjectKey: function(){ return 'bloom_main'; } };
var alert = function(){};
window.DAILY_BOARD_PROJECTS = ['bloom_main'];
window._bdIsDaily = function(pk){ return (window.DAILY_BOARD_PROJECTS||[]).indexOf(pk) >= 0; };
__FN__
window._v2SyncCrumbBiz();
window._bdSyncMenu('bloom_main');
var afterBloom = {
  crumb: els['v2-crumb-biz'].textContent,
  bloom: els['mdl-bloom-btn'].hidden,
  excel: els['mdl-lead-btn'].hidden,
  sep: seps[0].hidden
};
// 툴바가 다시 그려진 상황 — hidden 이 마크업 기본값으로 돌아간다
els['mdl-bloom-btn'].hidden = true;
els['mdl-lead-btn'].hidden = false;
seps[0].hidden = false;
window._bdSyncMenu('bloom_main');      // 메뉴를 다시 열었다
var afterRerender = { bloom: els['mdl-bloom-btn'].hidden, excel: els['mdl-lead-btn'].hidden };
// 반도체 프로젝트로 넘어가면 원래대로
window._bdSyncMenu('chamber');
var afterSemi = { bloom: els['mdl-bloom-btn'].hidden, excel: els['mdl-lead-btn'].hidden,
                  sep: seps[0].hidden };
// 사업부를 반도체로 되돌리면 breadcrumb 도 따라온다
els['v2-division-select'].selectedIndex = 0;
window._v2SyncCrumbBiz();
var crumbBack = els['v2-crumb-biz'].textContent;
console.log(JSON.stringify({afterBloom:afterBloom, afterRerender:afterRerender,
                            afterSemi:afterSemi, crumbBack:crumbBack}));
""".replace('__FN__', grab('_v2SyncCrumbBiz') + '\n' + grab('_bdSyncMenu'))

f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
f.write(JS); f.close()
r = subprocess.run(['node', f.name], capture_output=True, text=True)
os.unlink(f.name)
assert r.returncode == 0, f'실행 실패\n{r.stderr[:700]}'
out = json.loads(r.stdout)

assert out['afterBloom']['crumb'] == '블룸', out['afterBloom']
ok += 1
assert out['afterBloom'] == {'crumb': '블룸', 'bloom': False, 'excel': True, 'sep': True}, out['afterBloom']
ok += 1
# 다시 그려진 뒤 메뉴를 열어도 그대로여야 한다 — 이게 이번 버그다
assert out['afterRerender'] == {'bloom': False, 'excel': True}, out['afterRerender']
ok += 1
# 반도체로 가면 원래 메뉴
assert out['afterSemi'] == {'bloom': True, 'excel': False, 'sep': False}, out['afterSemi']
ok += 1
assert out['crumbBack'] == '반도체사업부', out['crumbBack']
ok += 1

print(f'전부 통과 ({ok}/8)')

# ======================================================================
#  새로고침해도 보던 자리에 그대로 (2026-10-26)
#
#  전에는 무엇을 보고 있었든 새로고침하면 첫 사업부(반도체) · 첫 화면으로
#  돌아갔다. 적을 때는 'v2_division' 에 적고 읽을 때는
#  'v2_selected_division' 을 봐서, 이름이 어긋나 저장이 아무 일도 안 했다.
#  엑셀을 반영하면 화면이 저절로 다시 뜨기 때문에 더 자주 걸린다.
# ======================================================================
_s = (BACK / "admin_v2.html").read_text(encoding="utf-8") if 'BACK' in dir() \
     else __import__('io').open(__import__('os').path.join(
         __import__('os').path.dirname(__import__('os').path.dirname(
             __import__('os').path.abspath(__file__))), 'admin_v2.html'),
         encoding='utf-8').read()

_fail = []
def _ok(c, why):
    if not c:
        _fail.append(why)

_ok("localStorage.setItem('v2_page', pg)" in _s,
    "보던 화면을 안 적어 둔다 — 새로고침하면 홈으로 떨어진다")
_ok("localStorage.getItem('v2_page')" in _s, "보던 화면을 안 되살린다")
_ok("localStorage.setItem('v2_selected_division'" in _s,
    "사업부를 읽는 이름으로 안 적는다 — 적어도 되살아나지 않는다")
_ok("localStorage.getItem('v2_selected_division') ||" in _s,
    "옛 이름('v2_division')도 같이 읽지 않는다 — 쓰던 사람만 또 처음으로 간다")
_ok(".nav-item[data-page=\"' + _pg + '\"]" in _s,
    "되살릴 때 그 메뉴를 누르지 않는다")
# 반영 뒤에는 사람이 안 눌러도 저절로 다시 뜬다
_ok("setTimeout(function() { location.reload(); }" in _s,
    "반영하고 나서 화면이 저절로 다시 뜨지 않는다")

if _fail:
    print("실패 %d건" % len(_fail))
    for f in _fail:
        print(" -", f)
    raise SystemExit(1)
print("ok — 새로고침 자리 지키기")
