# 지금 폴더의 코드 지문. 배포한 게 갔는지 가리는 데 쓴다 (2026-10-28).
#
#   python3 backend/build_stamp.py            → 내 폴더 지문
#   curl -s https://project-summary-mkoo.fly.dev/health
#
# 두 값이 같으면 올라간 것, 다르면 아직 안 간 것이다.
# 배포했는데 화면이 안 바뀔 때, '배포가 안 갔나 · 고친 게 틀렸나 ·
# 엑셀을 다시 안 올렸나' 셋을 한 번에 가려 준다.
import hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
h = hashlib.sha256()
for n in ("main.py", "admin_v2.html", "division_columns.py",
          "division_form_import.py", "config_loader.py",
          # main.py 의 _build_stamp 와 **같은 목록**이어야 한다.
          # 다르면 늘 "안 올라갔다" 로 읽힌다.
          "dev_schedule_import.py", "revenue_file_import.py",
          "division_revenue.py"):
    try:
        with open(os.path.join(HERE, n), "rb") as f:
            h.update(f.read())
    except Exception:
        h.update(b"?")
print(h.hexdigest()[:10])
