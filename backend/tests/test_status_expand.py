# 홈 '전체 현황' — 사업부 줄을 누르면 프로젝트가 펼쳐진다 (2026-11-05)
#   python3 backend/tests/test_status_expand.py
#
# Min: "일정 지연이나 집중관리에 있는 사업부 누르면 어떤 프로젝트의 일정 지연이나
#      집중관리 해야 되는건지 보였으면 좋겠어"
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_h = SRC[SRC.find("def get_home_alerts"):]
_h = _h[:_h.find("\n@app.", 10)]
assert '"items": []' in _h and 'row["items"].append(dict(r))' in _h, "사업부 줄에 프로젝트를 안 싣는다"
assert 'it["models"] = names[:3]' in _h and 'it["more"]' in _h, "프로젝트에 모델 이름을 안 싣는다"
LIB = ROOT.parent / "mobile/lib"
card = (LIB / "components/home/status_board_card.dart").read_text(encoding="utf-8")
svc = (LIB / "services/home_alerts_service.dart").read_text(encoding="utf-8")
assert "j['items']" in svc and "j['models']" in svc, "앱이 프로젝트 목록을 안 읽는다"
assert "if (p.items.isEmpty) return _plainRow(p);" in card, "옛 서버에서 줄이 안 열린다"
assert "_subRow(it, c)" in card and "화면으로" in card, "펼친 프로젝트 · 사업부 화면 가기가 없다"
print("ok — 사업부 줄 펼치기 (프로젝트 · 모델 이름)")
