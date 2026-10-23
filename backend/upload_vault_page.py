# ══════════════════════════════════════════════════════════════════
#  원본 보관함 화면 (2026-10-23)
# ══════════════════════════════════════════════════════════════════
#
# 보관함에 파일이 쌓여도 꺼낼 길이 없으면 없는 것과 같다. flyctl ssh 를
# 써야만 볼 수 있다면 터미널을 안 쓰는 사람에게는 닫힌 금고다.
#
# 그래서 admin 로그인만 있으면 브라우저에서 목록을 보고, 한 건씩
# 내려받고, 한 달치를 zip 으로 통째로 받을 수 있게 한다.
#
# admin_v2.html 은 일부러 건드리지 않는다. 그 화면은 '수정 금지' 상태라
# 손대면 잠금과 섞인다. 이 화면은 보기만 하는 별도 페이지다.
HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>원본 보관함 · OneView</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#F4F6F9;color:#0F172A;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
  .wrap{max-width:1100px;margin:0 auto;padding:24px 18px 60px}
  h1{font-size:20px;margin:0 0 6px}
  .lead{font-size:13px;color:#55657a;line-height:1.65;margin:0 0 18px}
  .lead b{color:#0F172A}
  .bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
  select,input[type=search]{font:inherit;font-size:13px;padding:8px 10px;border:1px solid #D9DFE7;
       border-radius:8px;background:#fff}
  .btn{font:inherit;font-size:13px;font-weight:700;padding:8px 13px;border-radius:8px;
       border:1px solid #16467E;background:#1B5091;color:#fff;text-decoration:none;cursor:pointer}
  .btn.ghost{background:#fff;color:#1B5091}
  .stat{margin-left:auto;font-size:12px;color:#55657a}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden}
  th,td{padding:9px 11px;font-size:12.5px;text-align:left;border-bottom:1px solid #EEF1F5;vertical-align:top}
  th{background:#0F2C59;color:#fff;font-size:11.5px;font-weight:800;white-space:nowrap}
  tr:last-child td{border-bottom:none}
  td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
  .fn{font-weight:700}
  .where{font-size:11px;color:#6B7280;margin-top:2px;word-break:break-all}
  .pill{display:inline-block;font-size:10.5px;font-weight:800;padding:1px 7px;border-radius:6px;
        background:#EEF4FF;color:#1B5091}
  .pill.gray{background:#F3F4F6;color:#6B7280}
  .pill.warn{background:#FEF3C7;color:#92400E}
  a.dl{font-size:12px;font-weight:700;color:#156082;text-decoration:none;white-space:nowrap}
  .empty{background:#fff;border:1px dashed #D5DBE3;border-radius:10px;padding:28px;text-align:center;
         color:#6B7280;font-size:13px;line-height:1.7}
  .foot{margin-top:18px;font-size:11.5px;color:#7a8696;line-height:1.7}
</style>
</head>
<body>
<div class="wrap">
  <h1>원본 보관함</h1>
  <p class="lead">
    admin 에 올라온 <b>엑셀 원본</b>을 손대지 않은 그대로 보관합니다.
    반영된 결과(화면에 보이는 숫자)와 달리, 이건 <b>올린 사람이 올린 그 파일</b>입니다.
    숫자가 이상할 때 원본과 맞춰 보면 엑셀이 그랬는지 읽기가 틀렸는지 가릴 수 있습니다.<br>
    서버 디스크(fly 볼륨)에 쌓이고 배포해도 지워지지 않습니다. 이 페이지는 <b>보기 전용</b>입니다 — 여기서 뭘 눌러도 운영 데이터는 바뀌지 않습니다.
  </p>

  <div class="bar">
    <select id="mon"></select>
    <input type="search" id="q" placeholder="파일명 · 프로젝트 · 경로 검색" style="min-width:240px">
    <a class="btn" id="zip" href="#">이 달치 zip 으로 받기</a>
    <span class="stat" id="stat"></span>
  </div>

  <div id="list"></div>

  <p class="foot">
    · 같은 파일을 두 번 올리면 파일은 한 벌만 두고 기록만 두 줄 남습니다 (<span class="pill gray">같은 파일</span>).<br>
    · 50MB 가 넘는 파일, 보관함이 상한(2GB)에 닿은 뒤 올라온 파일은 받지 않고 기록만 남습니다 (<span class="pill warn">안 받음</span>).<br>
    · 한 번 들어온 원본은 코드가 지우지 않습니다. 지우려면 사람이 직접 지워야 합니다.
  </p>
</div>

<script>
var MON = [], ROWS = [];

function kb(n){
  if(n == null) return '';
  if(n < 1024) return n + ' B';
  if(n < 1048576) return (n/1024).toFixed(1) + ' KB';
  return (n/1048576).toFixed(1) + ' MB';
}
function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];
  });
}
function when(iso){
  var s = String(iso || '').replace('T', ' ');
  return s.slice(0, 16);
}

function draw(){
  var q = document.getElementById('q').value.trim().toLowerCase();
  var rows = ROWS.filter(function(r){
    if(!q) return true;
    return [r.filename, r.project, r.where].join(' ').toLowerCase().indexOf(q) >= 0;
  });
  var box = document.getElementById('list');
  if(!rows.length){
    box.innerHTML = '<div class="empty">이 달에 올라온 파일이 없습니다.<br>'
      + '보관은 2026-10-23 부터 시작했습니다 — 그 전에 올린 엑셀은 남아 있지 않습니다.</div>';
    return;
  }
  var h = '<table><tr><th>올린 시각</th><th>파일</th><th>프로젝트</th>'
        + '<th class="num">크기</th><th>상태</th><th></th></tr>';
  rows.slice().reverse().forEach(function(r){
    var state = r.ok
      ? (r.duplicate_of ? '<span class="pill gray">같은 파일</span>' : '<span class="pill">보관됨</span>')
      : '<span class="pill warn">안 받음</span>';
    h += '<tr><td>' + esc(when(r.at)) + '</td>'
      + '<td><div class="fn">' + esc(r.filename) + '</div>'
      + '<div class="where">' + esc(r.where || '') + '</div></td>'
      + '<td>' + esc(r.project || '-') + '</td>'
      + '<td class="num">' + kb(r.bytes) + '</td>'
      + '<td>' + state + (r.skipped ? '<div class="where">' + esc(r.skipped) + '</div>' : '') + '</td>'
      + '<td>' + (r.ok && r.id
          ? '<a class="dl" href="/admin/uploads/file/' + encodeURIComponent(r.id) + '">내려받기</a>'
          : '') + '</td></tr>';
  });
  box.innerHTML = h + '</table>';
}

function loadMonth(){
  var m = document.getElementById('mon').value;
  document.getElementById('zip').href = '/admin/uploads/zip?month=' + encodeURIComponent(m);
  fetch('/admin/uploads/list?month=' + encodeURIComponent(m), {credentials: 'same-origin'})
    .then(function(r){ return r.json(); })
    .then(function(d){ ROWS = d.entries || []; draw(); });
}

fetch('/admin/uploads/summary', {credentials: 'same-origin'})
  .then(function(r){ return r.json(); })
  .then(function(d){
    MON = d.months || [];
    var sel = document.getElementById('mon');
    if(!MON.length){
      var now = new Date();
      MON = [now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0')];
    }
    sel.innerHTML = MON.map(function(m){
      return '<option value="' + m + '">' + m + '</option>';
    }).join('');
    document.getElementById('stat').textContent =
      '보관 ' + (d.count || 0) + '건 · ' + kb(d.bytes || 0)
      + ' / 상한 ' + kb(d.max_total_bytes || 0);
    loadMonth();
  });

document.getElementById('mon').addEventListener('change', loadMonth);
document.getElementById('q').addEventListener('input', draw);
</script>
</body>
</html>
"""
