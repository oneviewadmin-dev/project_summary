# 앱 오프라인용 묶음 — 사업부 하나의 화면 자료를 한 번에 (2026-11-05)
#   python3 backend/tests/test_offline_bundle.py
#
# Min: "그냥 애초에 온라인 일 때 알아서 데이터 여기 안까지 다 있게끔 해줘"
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_b = SRC[SRC.find('@app.get("/divisions/{division_id}/offline-bundle")'):]
assert _b, "묶음 주소가 없다"
# 앱 화면이 여는 주소와 같은 이름으로 담아야 앱이 제자리에 저장한다
for path in ('"/models/detail"', '"/models"', '"/weekly-plan"', '"/issues/summary"',
             '"/process-steps"', '"/weekly-board" + q', '"/weekly-revenue" + q'):
    assert path in _b, path
assert 'Content-Encoding": "gzip"' in _b
APP = (ROOT.parent / "mobile/lib/services/offline_prefetch.dart").read_text(encoding="utf-8")
assert "/offline-bundle?month=" in APP and "OfflineStore.store(" in APP
STORE = (ROOT.parent / "mobile/lib/services/offline_store.dart").read_text(encoding="utf-8")
assert "'models_$pk'" in STORE and "'weekly_plan_$pk'" in STORE, "화면의 저장 이름과 안 맞는다"
SCR = (ROOT.parent / "mobile/lib/screens/project_overview_screen.dart").read_text(encoding="utf-8")
assert "'models_${widget.projectKey}'" in SCR and "'weekly_plan_${widget.projectKey}'" in SCR
print("ok — 오프라인 묶음 (사업부 한 번 · 주소별 저장)")
