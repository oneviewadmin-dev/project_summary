# main.py 설명 기록

코드 안의 긴 설명(docstring · 주석 문단)을 한 줄로 줄이면서 옮겨 둔 원문입니다.
왜 그렇게 짰는지 · 누가 무엇을 물었는지가 여기 남아 있습니다. 코드에서 이름으로 찾으세요.

## def _safe_text_for_card

```
카드 한 장에서 "분류에 쓸 글자" 만 모아 한 줄로 잇는다.

    이 한 줄을 config_loader 가 보고 사업부·프로젝트를 맞춘다.
    쓰는 곳: enrich_card (PPT 를 읽어 카드를 만든 직후)
    
```

## def _normalize_model_name

```
모델 이름 앞의 목록 번호를 떼고 띄어쓰기를 하나로 맞춘다.

    주간보고 PPT 는 이름 앞에 번호를 붙여 온다 ('3. EFEM' · '1-2) EFEM').
    번호가 다르다고 같은 모델이 두 장으로 갈리면 안 된다.
    쓰는 곳: _model_match_key · _group_dashboard_cards
    
```

## def _model_match_key

```
카드의 모델 이름 → 같은 모델끼리 묶을 열쇠.

    주간보고 PPT 는 같은 모델을 장마다 조금씩 다르게 적는다
    ('EFEM' · 'EFEM (2대)' · 'EFEM-추가'). 이름 앞머리가 겹치면 이미 만든
    묶음의 열쇠를 돌려줘서, 이슈 여러 건이 모델 카드 한 장으로 모인다.
    쓰는 곳: _group_dashboard_cards (앱 대시보드 신호등 카드 — dashboard_service.dart)
    
```

## def _worst_status

```
이슈 여러 개의 색 중 가장 나쁜 색 하나를 고른다.

    카드 한 장 안에 이슈가 여럿일 때 카드 자체의 색을 정하는 데 쓴다.
    빨강이 하나라도 있으면 카드는 빨강이다 — 좋은 쪽으로 묻히지 않게.
    모르는 값은 0점이라 BLACK 보다도 아래로 친다.

    쓰는 곳: _group_dashboard_cards · project_templates.py
    
```

## def _load_headline_cache

```
headline_cache.json 을 읽는다. 없거나 깨졌으면 빈 캐시로 시작한다.

    캐시가 없다고 멈추면 안 된다 — 그냥 GPT 를 다시 부르면 되는 일이다.

    쓰는 곳: _ai_headline
    
```

## def _save_headline_cache

```
캐시를 파일에 적는다. 실패해도 조용히 넘어간다(캐시일 뿐이라서).

    쓰는 곳: _ai_headline
    
```

## def _pick_headline_source

```
    dated_items: [(due_date, text, raw_str), ...]
    due_date_min 과 같은 날짜의 항목을 우선 선택.
    없으면 첫 항목.

    쓰는 곳: dashboard
    
```

## def _ai_headline

```
    원문 한 줄을 15자 이내 행동 중심 요약으로 변환.
    캐시 우선. OpenAI 실패 시 원문 앞 15자.

    쓰는 곳: _fire_status_alarms · dashboard
    
```

## def _normalize_issue_headline

```
    이슈 헤드라인 dedup 용 정규화 (중간 강도).
    - 앞쪽 번호 prefix 제거
    - 양 끝 공백/구두점 정리
    - 다중 공백 1개로
    - 끝쪽의 보조어 (중/진행/예정/완료/중임/중입니다 등) 제거
    - 한글/영문 모델명 사이 공백 통일
    - 비교용이므로 lowercase

    쓰는 곳: _group_dashboard_cards
    
```

## def _group_dashboard_cards

```
    cards 를 모델 단위로 그룹핑.

    쓰는 곳: dashboard
    
```

## def enrich_card

```
    /dashboard 카드에 division/project 분류 정보를 '추가'한다.
    기존 필드는 절대 건드리지 않는다.
    실패 시 새 필드는 None으로만 들어가고, 카드 자체는 정상 반환한다.

    쓰는 곳: dashboard
    
```

## def enrich_project_detail

```
    /projects/{key} 상세 응답 최상위에 분류 정보를 '추가'한다.

    쓰는 곳: get_project_detail
    
```

## def _strip_useless_caveats

```
'실적이 없는 주차도 있으니 주의가 필요합니다' 같은 군더더기 경고 문장 제거.

    쓰는 곳: chat
    
```

## def _rag_build_chunks

```
벡터 인덱스에 넣을 텍스트 조각. 숫자가 아니라 '말'을 담는다.

    숫자(매출·수량·주차 계획)는 규칙 엔진이 권위 데이터로 답한다.
    벡터 검색은 규칙으로 못 잡는 비고·이슈·자재 메모를 찾는 용도다.

    쓰는 곳: _rag_rebuild
    
```

## def _rag_rebuild

```
인덱스를 지금 데이터로 다시 만든다. 서버에서만 돈다(임베딩 키 필요).

    쓰는 곳: _rag_maybe_refresh · rag_rebuild
    
```

## def _rag_maybe_refresh

```
인덱스가 없거나 하루 넘게 묵었으면 백그라운드에서 다시 만든다.

    쓰는 곳: chat
    
```

## def _rag_context

```
질문과 가까운 메모를 찾아 LLM 에 넘길 배경 텍스트로 만든다.
    인덱스가 없거나 닮은 게 없으면 빈 문자열 — 그러면 예전과 똑같이 동작한다.

    쓰는 곳: chat
    
```

## def _issue_answer

```
이슈·지연 질문 즉답. 적어둔 이슈 문장을 자르지 않고 그대로 낸다.

    LLM 을 거치면 문장이 중간에서 멈춘다(컨텍스트가 80자에서 잘려 있었다).
    이슈는 짧게 요약할 성질이 아니라 적힌 그대로가 답이다.

    쓰는 곳: chat
    
```

## def _alert_short_date

```
'2026-09-14' → '9/14'. 연도는 화면에서 이미 아는 값이다.

    쓰는 곳: _alert_brief
    
```

## def _alert_brief

```
한 줄 사유.

    적어 둔 이슈가 있으면 앞머리만 쓴다. '2대 고객 사급자재 지연
    (ETA: 9/20) → W39 (9/23) 출하예정' 을 통째로 들고 오면 화면에서
    잘려서 오히려 무슨 말인지 모르게 된다.

    쓰는 곳: _alert_answer_all
    
```

## def _alert_answer_all

```
프로젝트를 안 짚고 '일정 지연' 만 물었을 때.

    홈 카드와 같은 계산(get_home_alerts)을 그대로 쓴다. 예전에는 챗이
    따로 세서, 홈은 '일정 지연 8건 · 3곳' 인데 챗은 2건 2곳이라고 했다.
    이슈 칸에 견적 협의 메모를 적어 둔 모델까지 지연으로 끌어왔었다.

    쓰는 곳: chat
    
```

## def _chat_project_keywords

```
질문에서 프로젝트를 찾을 때 쓰는 '키워드 → project_key' 사전.

    config/projects.json 의 label / badge_label / aliases / keywords 를 전부 끌어온다.
    (예전에는 project_templates.PRODUCT_TO_PROJECT 8개 + 하바 하드코딩만 봐서
     블룸·큐리처럼 나중에 추가된 프로젝트를 아예 인식하지 못했다.)

    쓰는 곳: _chat_resolve_project
    
```

## def _chat_resolve_project

```
질문 문장에서 프로젝트 키를 찾는다. 가장 긴 키워드가 이긴다.

    쓰는 곳: chat
    
```

## def _answer_number_mismatch

```
답변에 들어간 금액/수량이 권위 데이터에 없는 값이면 그 값을 돌려준다.
    (없으면 None) — LLM 이 수치를 바꿔 말하는 것을 잡아내는 안전망.

    쓰는 곳: chat
    
```

## def _keep_upload

```
업로드 파일을 읽으면서 원본을 보관함에 한 벌 남긴다.

    쓰는 곳: _auto_read_upload · _ds_open · _pbx_open_upload · _rv_file_open 외 20곳
    
```

## def _init_fcm

```
Firebase Admin SDK 초기화. 서비스 계정 JSON은 FIREBASE_SERVICE_ACCOUNT_JSON 환경변수.

    쓰는 곳: _send_fcm_to_all
    
```

## def _load_device_tokens

```
등록된 기기 토큰 목록을 읽는다. 없으면 빈 목록.

    쓰는 곳: 알림을 보낼 때(받는 사람 명단) · 토큰을 새로 등록할 때.
    
```

## def _save_device_tokens

```
앱 푸시 알림을 받을 폰 목록(device_tokens.json)을 저장한다.

    쓰는 곳: _add_device_token · _send_fcm_to_all
    
```

## def _add_device_token

```
앱이 보내온 기기 토큰을 명단에 넣는다. 이미 있으면 시각만 갱신.

    앱은 켜질 때마다 토큰을 보낸다. 그래서 같은 토큰이 몇 번이고 온다 —
    중복으로 쌓지 않고 last_seen 만 고쳐 준다. 그 시각을 보면
    "이 폰이 마지막으로 앱을 켠 때" 를 알 수 있다.

    쓰는 곳: POST /fcm/register (앱이 부른다)
    
```

## def _send_fcm_to_all

```
등록된 모든 토큰에 알람 전송. 오늘 스코프: 디버그 토큰만 대상.

    쓰는 곳: _fire_status_alarms · admin_fcm_test
    
```

## def _snapshot_notes_status

```
현재 notes.json의 카드별 상태 + 원인 아이템 스냅샷.

    Value 형태:
      {
        "status": "RED",
        "trigger": {"text": "...", "due_date": "2026-08-02", "days_diff": -1}
      }

    쓰는 곳: admin_notes_item_due_override · admin_notes_item_due_override_reset
          · admin_notes_item_hide_auto_due · admin_notes_item_hide_auto_due_reset 외 2곳
    
```

## def _detect_status_transitions

```
이전 → 이후 상태 diff. RED/ORANGE로 새로 전이된 카드만 반환.

    before/after 는 신구 구조 모두 대응 (str or dict).

    쓰는 곳: admin_notes_item_due_override · admin_notes_item_due_override_reset
          · admin_notes_item_hide_auto_due · admin_notes_item_hide_auto_due_reset 외 2곳
    
```

## def _load_fcm_cooldown

```
같은 알림을 너무 자주 안 보내려고 적어 둔 '마지막 보낸 시각'을 읽는다.

    쓰는 곳: _fire_status_alarms
    
```

## def _save_fcm_cooldown

```
푸시 알림 '마지막 보낸 시각'을 저장한다.

    쓰는 곳: _fire_status_alarms
    
```

## def _load_fcm_history

```
보낸 푸시 알림 기록을 읽는다 (알림 화면 · 중복 막기).

    쓰는 곳: _fire_status_alarms · get_notifications · mark_notifications_read
    
```

## def _save_fcm_history

```
보낸 푸시 알림 기록을 저장한다. 오래된 것은 잘라 낸다.

    쓰는 곳: _fire_status_alarms · mark_notifications_read
    
```

## def _load_edit_session

```
편집 세션 파일 로드. 구조: {doc_id: {"snapshot": {...}, "started_at": timestamp}}

    쓰는 곳: _cleanup_expired_sessions · _clear_edit_session · _save_edit_session
    
```

## def _save_edit_session

```
편집 세션 저장 (before snapshot)

    쓰는 곳: admin_update_report
    
```

## def _clear_edit_session

```
편집 세션 클리어 및 저장된 snapshot 반환

    쓰는 곳: admin_report_edit_done
    
```

## def _cleanup_expired_sessions

```
30분 이상 된 세션 자동 정리

    쓰는 곳: admin_update_report
    
```

## def _fire_status_alarms

```
상태 전이 이벤트를 FCM으로 전송. 30분 쿨다운 적용 + 히스토리 저장.

    쓰는 곳: admin_notes_item_due_override · admin_notes_item_due_override_reset
          · admin_notes_item_hide_auto_due · admin_notes_item_hide_auto_due_reset 외 2곳
    
```

## def _b64u

```
바이트 → 쿠키에 담아도 안전한 글자.

    쓰는 곳: _sign_session
    
```

## def _b64u_decode

```
_b64u 의 반대. 잘라냈던 '=' 를 채워서 되돌린다.

    쓰는 곳: _verify_session
    
```

## def _sign_session

```
쿠키 값을 만든다 — "발급시각.만료시각.서명".

    DB 가 없어 세션을 서버에 저장하지 않는다. 대신 시각을 쿠키에 적고
    서버 비밀값으로 서명한다. 값을 고치면 서명이 안 맞아 들통난다.
    쓰는 곳: _issue_session_cookie
    
```

## def _verify_session

```
쿠키를 검사한다. 통과하면 만료시각, 아니면 None.

    ① 서명이 맞나 ② 8시간 안 지났나 ③ 발급 후 24시간 안 넘었나.
    쓰는 곳: get_admin_session — 모든 /admin 요청이 여기를 거친다.
    
```

## def _issue_session_cookie

```
로그인에 성공했을 때 쿠키를 구워서 응답에 붙인다.

    issued_at 을 넘기면 "연장" 이다 — 최초 발급 시각을 그대로 들고 가서
    24시간 상한을 넘기지 못하게 한다.

    쓰는 곳: admin_extend · admin_login_submit
    
```

## def get_admin_session

```
문지기. /admin 엔드포인트에 Depends(get_admin_session) 으로 붙인다.

    쿠키가 없거나 썩었으면 401 을 던져 거기서 요청이 끝난다.

    쓰는 곳: admin_add_model · admin_add_model_alias · admin_app_release
          · admin_app_release_upload 외 129곳
    
```

## def admin_login_page

```
admin 로그인 화면(HTML).

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / release.sh
    
```

## def admin_login_submit

```
admin 비밀번호 확인 → 세션 쿠키.

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / release.sh
    
```

## def admin_logout

```
admin 로그아웃.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_extend

```
admin 세션 시간 연장.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_session_info

```
admin 세션이 살아 있나 · 남은 시간.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _read_json

```
JSON 파일을 읽는다. 없거나 깨졌으면 default 를 돌려준다.

    이 시스템의 자료는 전부 JSON 파일이라 이 함수가 사실상 "DB 읽기" 다.
    절대 예외를 던지지 않는다 — 파일 하나 깨졌다고 서버가 서면 안 된다.

    쓰는 곳: _get_project_types · _load_fcm_cooldown · _load_fcm_history
          · _resync_notes_from_latest 외 18곳 · config_loader.py
    
```

## def _write_json

```
JSON 파일에 적는다. 이 시스템의 "DB 쓰기".

    통째로 덮어쓴다. 그래서 쓰기 전에 백업이 필요하다 (./backup.sh).
    indent=2 · ensure_ascii=False — 사람이 열어 봐야 할 때가 많아서다.

    쓰는 곳: _save_fcm_cooldown · _save_fcm_history · _update_latest
          · admin_create_manual_report 외 6곳
    
```

## def _make_doc_id

```
올라온 파일에 붙일 짧은 id 를 만든다 (12자리).

    파일명 + 올린 시각을 섞어 해시한다. 같은 이름을 또 올려도 다른 id 가
    나와야 앞 자료를 덮어쓰지 않는다.

    쓰는 곳: upload_ppt
    
```

## def _convert_pptx_to_png

```
LibreOffice + Poppler 로 PPTX → PDF → PNG 변환

    쓰는 곳: upload_ppt
    
```

## def _extract_text_per_slide

```
슬라이드별 텍스트 추출

    쓰는 곳: upload_ppt
    
```

## def _extract_pptx_text_and_tables

```
슬라이드별 텍스트(표 제외)와 표를 분리 추출.
    반환: (slide_texts: list[str], slide_tables: list[list[dict]])
    각 표: {"headers": [...], "rows": [[...], ...]}

    쓰는 곳: admin_notes_from_pptx
    
```

## def _classify_status_with_gpt

```
주간보고 PPT 글자를 GPT 에 보내 제품별 상태(신호등)를 뽑는다.

    쓰는 곳: upload_ppt
    
```

## def _cleanup_old_files

```
6개월 지난 파일 자동 삭제

    쓰는 곳: upload_ppt
    
```

## def _update_latest

```
    최신 보고서 저장.
    - 같은 doc_id가 있으면 갱신 (중복 방지)
    - 그 외에는 누적
    - report_family는 부가 정보로만 사용 (덮어쓰기 키로 사용 X)
    - 최대 50개까지만 유지 (오래된 것부터 제거)

    쓰는 곳: upload_ppt
    
```

## def _build_stamp

```
# 지금 서버에 올라가 있는 코드의 지문 (2026-10-28)
#
# Min: "flyctl deploy를 oneview admin 계정으로 했는데 그래서 적용이
#       안되는건가 뭐지"
#
# 배포했는데 화면이 안 바뀌면, 배포가 안 간 건지 · 고친 게 틀린 건지 ·
# 엑셀을 다시 안 올린 건지 알 길이 없었다. 셋 다 증상이 같다.
# 그래서 뜰 때 코드 지문을 재 둔다 — /health 한 번이면 가려진다.
#
# 뜰 때 한 번만 잰다. /health 는 fly.io 가 수시로 부르는 자리라 파일을
# 읽으면 안 된다.
지금 코드의 지문(10자리). /health 로 '배포가 갔나'를 확인할 때 쓴다.

    쓰는 곳: (파일 맨 위에서 바로 씀) · build_stamp.py
    
```

## def health

```
서버가 살아 있는지만 답한다.

    fly.io 가 주기적으로 부른다. 여기가 안 되면 서버를 죽이고 다시 띄운다.
    그래서 무거운 일을 하면 안 된다 — 파일도 읽지 않는다.

    build — 올라가 있는 코드의 지문. 배포 전에 로컬에서
            `python3 backend/build_stamp.py` 로 찍어 두고, 배포 뒤
            여기 값과 같은지만 보면 된다.
    up    — 이 서버가 뜬 시각. 배포가 갔으면 방금 시각이다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / backup.sh
    
```

## def data_version

```
자료가 바뀌었는지 한 줄로 알려준다. 앱의 자동 반영이 이걸 본다.

    부르는 곳: admin v2 — 없음 / 앱 — data_version_service.dart fetch()
    
```

## def _load_upload_hash_index

```
# 같은 파일을 두 번 올리는 걸 막으려고 파일 내용의 해시를 적어 둔다.
# 파일명이 달라도 내용이 같으면 같은 해시가 나온다.
올라왔던 파일들의 해시 장부를 읽는다.

    쓰는 곳: _find_duplicate_upload_by_hash · _record_upload_hash · admin_delete_doc
    
```

## def _save_upload_hash_index

```
해시 장부를 적는다. 실패해도 넘어간다(중복 검사가 느슨해질 뿐).

    쓰는 곳: _record_upload_hash · admin_delete_doc
    
```

## def _find_duplicate_upload_by_hash

```
전에 올라온 적 있는 파일인가? 있으면 그때의 파일명·doc_id 를 준다.

    /upload 가 이걸 보고 "이미 올린 파일입니다" 를 띄운다.
    정말 다시 올리려면 allow_duplicate=True 로 넘긴다.

    쓰는 곳: upload_ppt
    
```

## def _record_upload_hash

```
방금 받은 파일을 해시 장부에 적는다.

    쓰는 곳: upload_ppt
    
```

## def upload_ppt

```
주간보고 PPT 를 받는다. 이 구역에서 제일 중요한 창구.

    하는 일 순서
      ① 비밀번호(또는 로그인 쿠키) 확인
      ② 같은 파일 또 올린 건지 해시로 확인
      ③ PPT → PDF → 슬라이드 PNG 로 변환 (soffice + poppler)
      ④ 슬라이드 그림을 GPT 에게 보여 주고 이슈·신호등 색을 받아 온다
      ⑤ 사업부·프로젝트를 붙여(enrichment) 카드로 묶는다
      ⑥ notes.json / reports_latest.json 에 적는다

    division_id · project_id 를 같이 넘기면 ⑤ 의 추측을 건너뛰고
    그 값을 그대로 쓴다 (사장님이 미리 지정한 경우).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _due_status_one

```
단일 due_date 문자열 → 상태색.

    쓰는 곳: _calc_card_status · _snapshot_notes_status
    
```

## def _calc_card_status

```
카드 안 items 들의 due_date 들을 보고 가장 위험한 색으로 집계.
    빨강 > 주황 > 파랑 > 초록(매출만) > 검정 순.
    items가 비어있고 매출 데이터도 없으면 → BLACK.
    매출 데이터가 있고 due 항목이 없으면 → GREEN (정상 운영중).

    쓰는 곳: _snapshot_notes_status · dashboard · get_project_detail
    
```

## def dashboard

```
신호등 카드 - 각 카드에 project_key 포함 → Flutter에서 상세 이동에 사용

    부르는 곳: admin v2 — 없음 / 앱 — dashboard_service.dart
    
```

## def _normalize_project_name

```
프로젝트명 정규화: trim + 연속공백을 단일공백으로 + 자주 틀리는 표기 통일.

    쓰는 곳: _dedupe_cards_by_project · admin_create_manual_report · admin_update_report
    
```

## def _report_sort_key

```
dedupe용 정렬 키. 최신이 클수록 큰 값.
    uploaded_at -> created_at -> parsed.date 순으로 fallback.

    쓰는 곳: _dedupe_cards_by_project
    
```

## def _dedupe_cards_by_project

```
같은 프로젝트명이 여러 카드에 있으면 최신 것만 남긴다.
    비교 전 이름을 정규화. 순서는 최신순으로 정렬.

    쓰는 곳: admin_list_reports_all · list_reports
    
```

## def _split_report_by_project

```
한 리포트에 여러 프로젝트가 들어있으면 프로젝트 단위 카드로 분리.
    project_overrides가 있으면 프로젝트명을 그걸로 대체.

    쓰는 곳: admin_list_reports_all · list_reports
    
```

## def _classify_report_status

```
업로드 후 경과 시간과 report_date 기준 상태 분류.

    - 업로드 후 5분 이내: ai_processing (Chamber D-2 예시처럼)
    - report_date가 미래 or 오늘: review_pending (검토 대기)
    - 그 외: published (발행 완료)

    쓰는 곳: admin_list_reports_all · list_reports
    
```

## def list_reports

```
올라온 주간보고 목록.

    부르는 곳: admin v2 — getISOWeek() / 앱 — 없음
    
```

## def get_product_detail

```
제품 단위 상세 (기존 카드 탭용)

    부르는 곳: admin v2 — executeDelete() · __moreBtn.onclick() · _loadSalesForSection()
           · _flushManualEditAlarmSession() 외 1곳 / 앱 — 없음
    
```

## def _models_backups

```
# _save_models 는 덮어쓰기 전에 models.json.auto_<시각> 을 남긴다 (최근 10개).
# 무언가 사라졌을 때 어디로 돌아가야 하는지 보려면 그 안을 들여다볼 수
# 있어야 한다. 되돌리는 것도 저장이라, 되돌리기 전의 상태도 백업으로 남는다.
#
# models.json 백업 보기 · 되돌리기
models.json 자동 백업 파일 목록 (최신부터).

    쓰는 곳: admin_models_backups
    
```

## def _models_shape

```
프로젝트별로 무엇이 몇 개 들어 있는지. 백업끼리 비교하려고 쓴다.

    쓰는 곳: admin_models_backups · admin_models_restore
    
```

## def admin_models_backups

```
백업 목록. name 을 주면 그 백업 안이 어떤 모양인지 같이 보여준다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_models_restore

```
백업으로 되돌린다. payload = {name, projects?: [키...]}

    projects 를 주면 그 프로젝트만 백업 것으로 바꾼다. 통째로 되돌리면
    그 사이에 제대로 들어간 것까지 같이 잃는다.
    되돌리기 직전 상태도 백업으로 남으므로 다시 되돌릴 수 있다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_app_page

```
APK 올리는 화면. 배포 없이 새 버전을 내보낼 수 있다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _read_app_version

```
볼륨과 이미지 중 버전 코드가 더 높은 쪽.

    예전에는 볼륨을 무조건 앞세웠다. 그런데 볼륨에는 한참 전에 admin 으로
    올린 2.1.9 가 남아 있었고, release.sh 로 2.3.8 을 배포해도 서버는 계속
    2.1.9 를 알려줬다. 그 주소는 비공개 저장소의 릴리스라 앱이 받지도
    못해서 '업데이트 실패 404' 만 떴다.

    쓰는 곳: admin_app_release · admin_app_release_upload · get_app_changelog · get_app_version
    
```

## def _parse_changelog

```
'## 2.3.10 — 2026-09-16' 단위로 쪼갠다.

    쓰는 곳: _load_changelog
    
```

## def _load_changelog

```
CHANGELOG.md 를 읽는다 (앱 '변경 내역' · 업데이트 팝업).

    쓰는 곳: _changelog_for · get_app_changelog
    
```

## def _changelog_for

```
그 버전의 본문. 없으면 빈 문자열.

    쓰는 곳: get_app_version
    
```

## def get_app_changelog

```
설정 화면의 '변경 내역'. 최신 버전부터.

    부르는 곳: admin v2 — 없음 / 앱 — changelog_screen.dart initState()
    
```

## def get_app_version

```
앱 시작 시 호출. 최신 버전 정보 반환.

    부르는 곳: admin v2 — 없음 / 앱 — app_updater.dart _fromServer()
    
```

## def download_app_apk

```
최신 APK 다운로드.

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / release.sh
    
```

## def admin_app_release

```
지금 서버가 내주고 있는 버전과 APK 상태.

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / release.sh
    
```

## def admin_app_release_upload

```
새 APK 와 버전 정보를 올린다. 올리는 즉시 앱에 뜬다 (배포 불필요).

    versionCode 는 반드시 올라가야 한다. 안드로이드는 같거나 낮은 번호의
    APK 를 기존 앱 위에 설치하지 않는다 — 설치 실패 이유도 알려주지 않는다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / release.sh
    
```

## def _load_notes

```
사업부 노트(notes.json)를 읽는다.

    쓰는 곳: _build_major_module_issue_lines · _rag_build_chunks · _resync_notes_from_latest
          · _snapshot_notes_status 외 12곳
    
```

## def _save_notes

```
사업부 노트(notes.json)를 저장한다.

    쓰는 곳: _resync_notes_from_latest · _sync_report_to_notes · admin_delete_note
          · admin_notes_item_due_override 외 4곳
    
```

## def _load_models

```
운영 데이터를 읽는다. 씨앗으로 떨어질 때는 조용히 넘어가지 않는다.

    예전에는 /app/models.json 으로 말없이 떨어졌다. 볼륨이 안 붙거나 비면
    에러 없이 몇 달 전 자료가 그대로 서비스돼서, 화면은 멀쩡한데 숫자만
    옛날 것인 상태가 된다 — 아무도 못 알아챈다. 그래서 떨어질 때마다
    로그에 크게 남긴다.

    쓰는 곳: _apply_dev_status · _apply_report_workbook · _auto_diff · _auto_order_merge 외 95곳
    
```

## def _save_models

```
모든 프로젝트·모델 자료(models.json)를 저장한다. 저장 전에 자동 백업을 남긴다.

    쓰는 곳: _apply_dev_status · _apply_report_workbook · _auto_order_merge
          · _cleanup_auto_notes 외 39곳 · plan_archive.py · upload_store.py
    
```

## def _ess_legacy_cleanup

```
옛 ESS 프로젝트를 지운다. 지운 키 목록을 돌려준다.

    쓰는 곳: _ess_legacy_cleanup_on_startup · division_columns.py
    
```

## def _auto_order_merge

```
수주 자료를 양식 품목에 얹고 auto_* 를 지운다. 한 일을 돌려준다.

    쓰는 곳: _ess_legacy_cleanup_on_startup
    
```

## def _ess_legacy_cleanup_on_startup

```
서버가 켜질 때 저절로 돈다
```

## def _normalize_model

```
dict → 정규화된 모델 dict. 검증 실패 시 None 반환

    쓰는 곳: admin_add_model
    
```

## def _get_project_models

```
프로젝트 키로 모델 목록 조회 (별칭 매핑 적용)

    쓰는 곳: admin_get_project_models · get_project_models
    
```

## def _new_asset_id

```
사업부별 자산 ID 생성: YYYY-MM-DD_<uuid8>

    쓰는 곳: _save_note_photo · _save_note_table · admin_upload_note_excel
          · admin_upload_note_photo 외 1곳
    
```

## def _table_path

```
노트에 붙인 표(JSON) 파일 자리.

    쓰는 곳: _delete_note_table · _load_note_table · _save_note_table · admin_save_note_table
    
```

## def _photo_path

```
노트에 붙인 사진 파일 자리.

    쓰는 곳: _save_note_photo · admin_upload_note_excel · admin_upload_note_photo
          · admin_upload_weekly_plan
    
```

## def _save_note_table

```
표 JSON 저장 → asset_id 반환 (예: 'semiconductor/2026-06-11_a1b2c3d4')

    쓰는 곳: admin_notes_from_pptx · admin_save_note_table
    
```

## def _save_note_photo

```
이미지 bytes → note_photos/에 저장 → photo_ref 반환.
    반환 예: 'semiconductor/2026-07-30_a1b2c3d4.png'

    쓰는 곳: _products_to_note_cards · admin_upload_section_file
    
```

## def _xlsx_file_to_png_bytes

```
xlsx → PNG bytes (LibreOffice + pdf2image로 색상/스타일 완벽 반영).
    
    옛 openpyxl+Pillow 직접 렌더링 방식은 표 서식/조건부 서식/테마 색상을
    지원하지 못했음. LibreOffice로 pdf 변환 후 pdf2image로 png 렌더링하면
    원본 엑셀과 시각적으로 100% 동일.

    쓰는 곳: _products_to_note_cards · admin_upload_section_file
    
```

## def _derive_division_id_from_report

```
report dict → division_id 유추.
    우선순위: it.division_id → products[i].name derive → 'semiconductor' 폴백.
    _sync_report_to_notes의 로직과 동일하게 유지.

    쓰는 곳: admin_upload_section_file
    
```

## def _load_note_table

```
table_ref = 'semiconductor/2026-06-11_a1b2c3d4' → 표 JSON 반환

    쓰는 곳: _inject_tables_into_cards · get_note_table · notes_by_project
    
```

## def _delete_note_table

```
노트에 붙인 표 파일 하나를 지운다.

    쓰는 곳: admin_delete_note_table
    
```

## def _delete_note_photo

```
photo_ref = 'semiconductor/2026-06-11_a1b2c3d4.jpg'

    쓰는 곳: _cleanup_plan_originals · admin_delete_note_photo · admin_delete_weekly_plan
          · admin_upload_weekly_plan
    
```

## def admin_notes_from_pptx

```
업로드된 PPT를 주간 보고 카드 구조로 자동 변환.
    - 슬라이드 텍스트는 AI로 카드 구조화
    - 표는 자동으로 note_assets/tables/ 에 저장 + table_ref 연결

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def notes_by_project

```
프로젝트 키로 가장 최근 노트 카드를 찾아 반환.
    매칭 우선순위:
      1) card.get("project_key") == project_key
      2) card.get("title") 가 projects.json 의 label/aliases 와 매칭
    표는 _load_note_table 으로 inline 포함.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _inject_tables_into_cards

```
정리된 카드 구조에 type:'table' item 을 앵커 기준으로 주입.

    쓰는 곳: main.py 안에서는 안 쓴다 (테스트 · 예전 코드)
    
```

## def _extract_photo_markers

```
텍스트에서 사진 마커 추출 (next_anchor 기반 위치 보존).
    반환: (clean_text, [{filename, photo_ref, anchor, next_anchor, placeholder}])
    anchor      = 마커 직전의 비어있지 않은 줄
    next_anchor = 마커 다음에 나오는 비어있지 않은 줄 (마커가 아닌 줄)

    쓰는 곳: admin_notes_ai_parse
    
```

## def _extract_due_date_from_text

```
본문 텍스트에서 due_date(YYYY-MM-DD) 추출. 못 찾으면 빈 문자열.
    
    화살표 인식형 파서 (마커 없이 자동 판단):
      1) 텍스트를 화살표(-->, ->, →, ➜, ⇒, ~>)로 split → 단계별로 나눔.
      2) 마지막 세그먼트만 대상으로 날짜 후보 수집 (앞 단계는 완료로 간주).
      3) 마지막 세그먼트에 날짜 없으면 전체 텍스트에서 fallback.
      4) 후보 중 최적 선택:
         - 오늘 이후(포함) 날짜 있으면 → 그중 가장 가까운 미래
         - 없으면 → 지난 날짜 중 가장 최근 (지연 D+n 표시용)
    
    지원 패턴:
      - [YYYY-MM-DD] / YYYY-MM-DD
      - YY.M.D / YY-M-D
      - M월말 (해당 월 마지막 평일)
      - M월 D일
      - (M/D), M/D
      - (M/D-M/D), (M/D~M/D)  → 종료일 채택
      - W23~W53 (해당 ISO 주차 금요일)

    쓰는 곳: _extract_due_date
    
```

## def _normalize_note_item

```
AI 결과 아이템 후처리: 색상 태그, ※ 항목, 화살표 중복 제거.
    
    ★ 2026-07-27~ 스키마 확장:
      - item_id: md5(section_title + normalized_text)[:8] 자동 생성
      - due_date_auto: 파서가 뽑은 자동값 (매번 재계산)
      - due_date_override: 사용자 지정값 (있으면 유지)
      - due_date: override or auto (앱 호환용 최종값)

    쓰는 곳: _normalize_note_cards
    
```

## def _normalize_note_cards

```
parsed["cards"] 전체에 _normalize_note_item 적용 + 기타 특이사항 섹션 병합.

    쓰는 곳: _sync_report_to_notes · admin_notes_ai_parse · admin_save_note
    
```

## def _inject_photos_into_cards

```
정리된 카드 구조에 type:'photo' item 을 주입.
    1순위: placeholder 텍스트 ('__PHOTO_PLACEHOLDER_N__') 가진 item 을 photo item 으로 직접 치환 → 원문 위치 보존
    2순위(fallback): anchor 텍스트 매칭 (구버전 호환)

    쓰는 곳: admin_notes_ai_parse
    
```

## def admin_notes_ai_parse

```
자유 형식 텍스트를 AI로 구조화 JSON으로 변환 (증분 병합 지원).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_save_note

```
사업부별 노트 저장.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def get_notifications

```
# ─── 알림 히스토리 (앱 종 아이콘용) ───
최근 알람 목록. 최신순.

    부르는 곳: admin v2 — 없음 / 앱 — notifications_service.dart list()
    
```

## def mark_notifications_read

```
id 지정 시 해당 항목만, 없으면 전체 읽음 처리.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def get_notes

```
앱이 호출하는 공개 API. division_id 지정 시 해당 사업부만 반환.

    부르는 곳: admin v2 — _loadNotesForSchedule()
           · _reloadNotesCache() / 앱 — 없음 / static/note_loader.js
    
```

## def _find_item_by_id

```
# item 단위 due_date override (사용자 수동 지정)
#
# 규칙:
#   - due_date_auto: 파서 자동값 (매번 재계산)
#   - due_date_override: 사용자가 지정한 값 (있으면 유지)
#   - due_date: override or auto (최종 표시값)
#
# POST → override 지정, DELETE → override 제거 (자동값 복귀)
(item_ref, card_ref, section_ref) 반환. 못 찾으면 (None, None, None).

    쓰는 곳: admin_notes_item_due_override · admin_notes_item_due_override_reset
          · admin_notes_item_hide_auto_due · admin_notes_item_hide_auto_due_reset
    
```

## def _apply_effective_due_date

```
it 안의 override/auto 를 보고 최종 due_date 필드를 갱신.

    쓰는 곳: _sync_report_to_notes · admin_notes_item_due_override
          · admin_notes_item_due_override_reset · admin_notes_item_hide_auto_due 외 1곳
    
```

## def admin_notes_item_due_override

```
특정 item 의 due_date_override 지정.
    
    Request:
      { division_id, card_title, item_id, due_date: "YYYY-MM-DD" }

    부르는 곳: admin v2 — outsideClick() / 앱 — 없음
    
```

## def admin_notes_item_due_override_reset

```
item 의 due_date_override 제거 → 자동값(due_date_auto) 복귀.
    
    Request:
      { division_id, card_title, item_id }

    부르는 곳: admin v2 — outsideClick() / 앱 — 없음
    
```

## def admin_notes_item_hide_auto_due

```
특정 item 의 자동 파싱 날짜를 숨김 처리. 수동값이 있으면 그것도 함께 제거.
    
    Request:
      { division_id, card_title, item_id }

    부르는 곳: admin v2 — outsideClick() / 앱 — 없음
    
```

## def admin_notes_item_hide_auto_due_reset

```
item 의 auto_due_hidden 해제 → 자동값(due_date_auto) 복원.
    
    Request:
      { division_id, card_title, item_id }

    부르는 곳: admin v2 — outsideClick() / 앱 — 없음
    
```

## def admin_delete_note

```
노트 삭제.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_save_note_table

```
# ─── 노트 표/사진 첨부 API ───
표 생성/수정. payload = {division_id, table_ref?, table: {title, headers, rows}}

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def get_note_table

```
표 JSON 조회 (모바일/관리자 공용)

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_delete_note_table

```
노트에 붙인 표 하나 지우기 (잠김).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_upload_note_photo

```
사진 업로드 → photo_ref(예: 'semiconductor/2026-06-11_abcd1234.jpg') 반환

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / static/photo_drop.js
    
```

## def _norm_label

```
이름 비교용 — 기호·띄어쓰기를 빼고 대문자로.

    쓰는 곳: _apply_plan_matrix · _bloom_fold · _bloom_merge · _bloom_slice 외 5곳
    
```

## def _as_money

```
판가·재료비 같은 '금액'. 소수점을 살린다.

    예전에는 int() 로 잘라서 판가 3150.4 가 3150 으로 저장됐다.
    1,000대면 400달러가 사라진다. 소수 둘째 자리까지 반올림하고,
    딱 떨어지면 int 로 돌려 기존 데이터(3150)의 표기가 3150.0 으로
    바뀌지 않게 한다.

    쓰는 곳: _apply_price_change · _auto_diff · _df_apply_price · _df_price_preview 외 15곳
    
```

## def _as_int

```
수량 값을 정수로. 문자열/소수/None/콤마 어느 쪽이 와도 터지지 않는다.

    쓰는 곳: _apply_plan_matrix · _auto_diff · _board_month_qty · _board_week_qty 외 13곳
    
```

## def _split_pn

```
'키스톤 (556B)' -> ('키스톤', '556B'). 괄호가 없으면 (원문, '').

    쓰는 곳: _apply_plan_matrix
    
```

## def _board_group_rows

```
보드에서 여러 모델을 한 줄로 묶어둔 행. {정규화한 행 이름: [모델 id]}

    엑셀의 묶음 행('버스바/시트메탈류(11종)')을 어디에 넣을지 찾을 때 쓴다.

    쓰는 곳: _apply_plan_matrix
    
```

## def _apply_plan_matrix

```
'구분 x 주차' 엑셀을 모델별 주차 계획 + 프로젝트 주차 합계에 반영.
    같은 월/주차가 이미 있으면 이번 업로드 값으로 덮어쓴다(최신 우선).

    쓰는 곳: admin_upload_weekly_plan
    
```

## def _detect_marked_weeks

```
엑셀에서 빨간(유채색) 굵은 테두리로 표시한 주차 라벨을 찾아 ['W35'] 형태로 반환.

    쓰는 곳: admin_upload_weekly_plan
    
```

## def _excel_sheet_to_preview_data_url

```
엑셀 첫 시트를 그림(PNG)으로 그려 미리보기용 data URL 로 만든다.

    쓰는 곳: admin_upload_note_excel · admin_upload_weekly_plan
    
```

## def admin_upload_note_excel

```
엑셀(.xlsx/.xlsm) 업로드 → 첫 시트를 PNG 이미지로 변환 → 사진처럼 저장 → photo_ref 반환.

    부르는 곳: admin v2 — 없음 / 앱 — 없음 / static/excel_drop.js
    
```

## def admin_delete_note_photo

```
노트에 붙인 사진 하나 지우기 (잠김).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def list_divisions

```
공개 사업부 목록 + 각 사업부의 visible 프로젝트 리스트.
    매핑 관리 대시보드 / 모바일 사업부 화면에서 사용.

    앱에서 숨긴 사업부는 여기서 뺀다 (2026-10-27). 앱이 사업부를 받아
    가는 길은 이 하나뿐이라(DivisionsService) 여기서 빼면 홈·고르기·
    설정 어디에도 안 뜬다. admin 은 /admin/config/divisions 를 따로
    보기 때문에 그대로 다 보인다 — 자료는 계속 올려야 하니까.

    부르는 곳: admin v2 — fillDivisions() / 앱 — divisions_service.dart
    
```

## def get_divisions_updates

```
각 사업부의 최신 업데이트 타임스탬프 반환.
    카드의 project_key 가 없을 수 있으므로 텍스트 기반 분류기를 사용한다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def list_projects

```
프로젝트 버튼 목록 + 모델 데이터 유무

    부르는 곳: admin v2 — _npLoadProjectButtons() · loadProjectOptions() · loadModels()
           · _getCurrentProjectKey() 외 1곳 / 앱 — projects_service.dart
    
```

## def admin_models_template

```
모델 등록용 빈 엑셀 양식.

    예전에는 uploads/model_add_template.xlsx 라는 정적 파일을 그대로 내보냈고,
    없으면 모델·구분·유형·판가·재료비 다섯 칸짜리를 만들어 줬다. 둘 다 파트넘버가
    없다. 파트넘버가 없으면 임포터가 모델명으로 맞추는 수밖에 없고, 큐리처럼
    '버스바' 5줄 '시트메탈' 6줄인 파일은 16줄이 7종으로 뭉개진다.
    그래서 양식은 코드에서 만든다 (model_template.py). 임포터가 읽는 열과 항상 같다.

    project_key 를 주면 그 프로젝트의 유형 목록이 드롭다운으로 들어간다.

    부르는 곳: admin v2 — tplBtn.onclick() · _nm.onclick() / 앱 — 없음
    
```

## def admin_models_import

```
모델 목록 엑셀 올리기 (예전 방식).

    부르는 곳: admin v2 — doExcelUpload() / 앱 — 없음
    
```

## def _issues_fingerprint

```
issues 내용 기반 지문 — 변경 시에만 LLM 재호출

    쓰는 곳: _summarize_issues
    
```

## def _summarize_issues

```
모델별 이슈를 각각 1~2문장으로 요약. 반환: [{"model": str, "summary": str}, ...]
    summary 내 문장은 
으로 분리 (이슈 / 후속조치).

    쓰는 곳: get_issues_summary
    
```

## def get_issues_summary

```
앱 개요 화면용 이슈 AI 요약

    부르는 곳: admin v2 — 없음 / 앱 — project_overview_screen.dart _loadBloom()
    
```

## def get_project_models

```
프로젝트 모델 목록 + 그룹별 요약 (앱 8번 화면용)

    응답:
    {
      "project_key": "cup",
      "has_models": true,
      "total": 4,
      "groups": {"양산": {"count": 4, "models": [...]}, "개발": {...}},
      "models": [...]
    }

    부르는 곳: admin v2 — mdlRefresh() · loadModels() · saveModels()
           · _wpLoadModels() 외 1곳 / 앱 — model_cost_list_screen.dart initState()
           · model_list_screen.dart _massCard()
    
```

## def get_project_detail

```
프로젝트 상세

    부르는 곳: admin v2 — markClean() · reloadKpiSlot() · loadProjectTypes()
           · mdlRefresh() 외 35곳 / 앱 — model_cost_list_screen.dart initState()
           · dev_process_screen.dart initState()
           · project_overview_screen.dart _loadBloom() 외 9곳
    
```

## def admin_config_divisions

```
    admin 페이지의 사업부 dropdown 용.
    config_loader.get_divisions() 결과를 그대로 노출.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _load_learned_aliases

```
사람이 '이 이름은 이 프로젝트'라고 알려 준 별칭 목록을 읽는다.

    쓰는 곳: _find_project_by_learned_alias · admin_projects_add_alias · chat
    
```

## def _save_learned_aliases

```
배운 별칭 목록을 저장한다.

    쓰는 곳: admin_projects_add_alias
    
```

## def _find_project_by_learned_alias

```
배운 별칭으로 프로젝트를 찾는다.

    쓰는 곳: admin_projects_resolve · admin_projects_suggest
    
```

## def admin_projects_resolve

```
    fuzzy로 못 잡은 오타를 AI로 판정.
    payload: {"query": "참바", "division_id": "semiconductor" (optional)}

    부르는 곳: admin v2 — _onNewProjectNameInput() / 앱 — 없음
    
```

## def admin_projects_add_alias

```
    사용자 승인 alias를 learned_aliases.json에 저장.
    payload: {"project_id": "chamber", "alias": "참바"}

    부르는 곳: admin v2 — _npBuildAiSuggestBox() / 앱 — 없음
    
```

## def _en_to_ko

```
영문 자판으로 친 한글(예: 'qksehcp')을 한글로 바꾼다 (검색용).

    쓰는 곳: admin_projects_suggest
    
```

## def _ko_to_en

```
한글 자판으로 친 영문을 영문으로 바꾼다 (검색용).

    쓰는 곳: admin_projects_suggest
    
```

## def admin_projects_suggest

```
    프로젝트명 fuzzy match.
    - learned_aliases.json 우선 체크
    - 한글 자모 단위 유사도 (챕버 <-> 챔버)
    - 한/영 자판 변환 (xhffhs -> 톨론, coaqj -> 챔버)

    부르는 곳: admin v2 — _onNewProjectNameInput() / 앱 — 없음
    
```

## def admin_config_projects

```
    admin 페이지의 프로젝트 dropdown 용.
    division_id 가 주어지면 해당 사업부의 프로젝트만 반환.

    부르는 곳: admin v2 — _npLoadProjectButtons() · loadProjectOptions()
           · back.onclick() / 앱 — 없음
    
```

## def admin_config_sections

```
    admin 이미지 업로드 탭의 섹션 dropdown 용.
    현재 분석된 PPT 결과에서 해당 프로젝트의 실제 GPT 섹션 제목들을 가져옴.
    이것이 핵심 — 더 이상 자유 입력 안 함, GPT 가 만든 실제 섹션만 옵션으로 노출.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_config_stats

```
    매핑 관리 탭용 통계.
    - 현재 사업부/프로젝트 수
    - 자동 분류된 카드/실패 카드 수
    - 실패 카드의 product/category 샘플

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_v2_page

```
admin v2 화면(HTML) 자체를 내준다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_uploads_page

```
업로드 보관함 화면(HTML).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_uploads_summary

```
업로드 보관함 — 달별 건수 요약.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_uploads_list

```
업로드 보관함 — 목록.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_uploads_file

```
한 건 내려받기.

    경로를 바깥에서 받지 않는다 — 기록에 있는 id 로만 찾는다.
    '../' 같은 값으로 보관함 밖 파일을 읽히지 않게 하기 위해서다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_uploads_zip

```
한 달치를 zip 으로. 인수인계 때 통째로 넘기는 길.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_upload_page

```
예전 업로드 화면(HTML).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_uploads_history

```
업로드된 PPT 목록 (삭제 UI용)

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_list_reports_all

```
숨긴 것까지 포함한 보고서 전체 목록.

    부르는 곳: admin v2 — loadAdminV2Reports() · openReportEdit() / 앱 — 없음
    
```

## def admin_create_manual_report

```
보고서를 손으로 만든다 (잠김).

    부르는 곳: admin v2 — getISOWeek() / 앱 — 없음
    
```

## def admin_delete_manual_report

```
손으로 만든 보고서 지우기 (잠김).

    부르는 곳: admin v2 — executeDelete() · __moreBtn.onclick() · _loadSalesForSection()
           · _flushManualEditAlarmSession() 외 1곳 / 앱 — 없음
    
```

## def _extract_due_date

```
(clean_text, due_iso or None) 반환.
    
    ★ 원문 그대로 유지 정책 (2026-07-27~):
      - 사용자가 적은 문장을 그대로 앱에 표시하기 위해 텍스트는 건드리지 않음.
      - due_date 만 추출 (화살표 인식형 파서 사용).
      - 명시적 대괄호 [YYYY-MM-DD] / [YY-MM-DD] 는 우선순위로 처리.

    쓰는 곳: _html_body_to_items · _normalize_note_item
    
```

## def _collect_inline_runs

```
BeautifulSoup 노드를 재귀 순회하며 [(text, style_dict), ...] 반환.
    style_dict keys: color, bold, italic, underline, size_scale.
    부모의 스타일은 자식에게 상속됨.

    쓰는 곳: _html_body_to_items
    
```

## def _runs_to_output

```
runs [(text, style), ...] → (plain_text, text_runs 또는 None).
    연속된 동일 style은 병합. 스타일이 하나도 없으면 text_runs=None 반환.

    쓰는 곳: _html_body_to_items
    
```

## def _html_body_to_items

```
HTML(관리자 편집기 결과)을 모바일 앱이 이해하는 items 배열로 변환.
    
    우선 items가 이미 있으면 그대로 반환 (구조화된 저장 포맷).
    없으면 HTML 파싱 (기존 방식, 호환용).

    쓰는 곳: _products_to_note_cards
    
```

## def _products_to_note_cards

```
products[] → notes.json 형식의 cards[] 로 변환.

    쓰는 곳: _sync_report_to_notes
    
```

## def _sync_report_to_notes

```
수기 doc 하나를 notes.json에 upsert.
    
    - division_id 유추: it['division_id'] > product.name derive > semiconductor 폴백
    - cards는 title 기준 merge
    - _normalize_note_cards로 후처리

    쓰는 곳: _resync_notes_from_latest · admin_create_manual_report · admin_update_report
    
```

## def admin_division_columns

```
# 사업부마다 표에 세울 열 (2026-10-26)
#
# 양식 7종을 열어 보니 열 구성이 세 모양이었다. 어느 사업부가 어떤
# 열을 쓰는지는 division_columns.py 하나만 안다 — 파서와 화면이 각자
# 짐작하면 양식이 바뀔 때 한 곳을 빠뜨리고 숫자가 조용히 어긋난다.
# 화면(admin_v2)은 여기서 받은 열만 그린다.
사업부별 양식 열 구성 (division_columns).

    부르는 곳: admin v2 — _mdlColSpecLoad() / 앱 — 없음
    
```

## def admin_division_app_visibility

```
# 전에는 이 스위치가 네 곳에 흩어져 있었고, 그중 둘은 **앱 안**이라
# 하나 올리려면 앱을 새로 배포해야 했다. 이제 서버가 한 줄로 알려주고
# admin 과 앱이 그걸 받아 간다.
#
# 관리자 전용이 아니다 — 앱이 로그인 없이 읽어야 한다. 사업부 이름과
# 켜짐/꺼짐뿐이라 숨길 것이 없다.
#
# 앱에서 사업부 숨기기 (2026-10-27)
# admin 에서 끄면 **앱에서만** 그 사업부가 통째로 사라진다. admin 은
# 그대로 다 보인다 — 숨긴 사업부도 자료는 계속 올려야 한다.
#
# config/divisions.json 의 visible 을 쓰지 않는 이유는 그 값이 admin 과
# 앱을 같이 끄기 때문이다. 자세한 건 division_visibility.py 에 적었다.
사업부마다 앱에 보이나. admin 화면의 체크박스가 이걸 그린다.

    부르는 곳: admin v2 — saveAppVis() / 앱 — 없음
    
```

## def admin_set_division_app_visibility

```
숨김 목록을 통째로 갈아 끼운다.

    하나씩 켜고 끄는 창구로 두면, 화면에서 여러 개를 바꾸고 저장할 때
    요청이 여러 번 날아가고 중간에 하나 실패하면 반만 반영된다.
    화면이 '지금 숨길 것 전부' 를 보내고 서버가 그대로 적는다.

    부르는 곳: admin v2 — saveAppVis() / 앱 — 없음
    
```

## def division_terms

```
그 사업부의 용어 사전. 양식 '용어' 시트에서 온다.

    로그인 없이 내준다 — 약어와 뜻뿐이라 숨길 것이 없고, 앱이 화면에서
    'MPS' 옆에 뜻을 붙이려면 읽을 수 있어야 한다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def divisions_ui

```
어느 사업부에서 무엇을 보일까. 앱과 admin 이 같은 답을 본다.

    부르는 곳: admin v2 — _divUiLoad() / 앱 — 없음
    
```

## def admin_get_project_models

```
admin용 모델 목록 조회.

    지연 여부는 모델 안에 넣지 않고 따로 내려준다. 이 화면이 고친 모델을
    그대로 PUT 으로 돌려보내기 때문에, 계산해서 얹은 값이 models.json 에
    눌러앉는다. 한 번 저장되면 날짜가 지나도 안 바뀌는 가짜 지연이 된다.

    부르는 곳: admin v2 — mdlRefresh() · loadModels() · saveModels() / 앱 — 없음
    
```

## def _admin_model_alerts

```
모델 id → {kind, why}. 앱과 같은 규칙(_model_alert)을 쓴다.

    쓰는 곳: admin_get_project_models
    
```

## def _alert_why

```
왜 그렇게 봤는지 한 줄. 빈칸으로 두면 화면에서 따질 근거가 없다.

    쓰는 곳: _admin_model_alerts
    
```

## def admin_add_model

```
모델 단건 추가. 같은 id가 이미 있으면 409 반환.
    payload: {"id": "cup-100", "name": "CUP-100", "group": "양산", "progress": 35, "status": "지연"}

    부르는 곳: admin v2 — mdlRefresh() · loadModels() · saveModels() / 앱 — 없음
    
```

## def admin_update_model

```
모델 단건 수정 (부분 업데이트)
    payload: 변경할 필드만 {"name": "...", "progress": 50, ...}

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_delete_model

```
모델 단건 삭제

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _save_untouched

```
보낸 값이 '열 때 받은 값' 과 같은가 = 사람이 안 건드린 칸인가.

    화면은 숫자를 '1,117' 처럼 쉼표를 넣어 보여주고 보낼 때 떼는데, 떼는
    자리가 한 군데가 아니라서 글자로 올 수도 숫자로 올 수도 있다. 숫자로
    읽히면 숫자끼리, 아니면 글자끼리 본다.

    쓰는 곳: admin_put_project_models
    
```

## def _route_re

```
주소 틀('/admin/projects/{key}/models')을 맞춰 볼 정규식으로 바꾼다 (admin 잠금).

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _admin_locked

```
이 주소가 admin 잠금 목록에 있나 (고치기·지우기 막기).

    쓰는 곳: _admin_write_lock
    
```

## def _admin_write_lock

```
모든 요청이 지나가는 문 (미들웨어)
```

## def admin_write_lock_info

```
화면이 받아 가는 잠금 목록. 화면에 따로 적어 두면 서버와 갈린다.

    부르는 곳: admin v2 — fetch() / 앱 — 없음
    
```

## def _write_off

```
막혀 있으면 403 으로 돌려보낸다. 안 막혀 있으면 아무 일도 안 한다.

    쓰는 곳: admin_put_project_models · admin_put_week_reason · put_project_status_note
    
```

## def admin_put_project_models

```
admin용 모델 목록 저장 (전체 교체) - dev_type/process/weekly_plan/status_note 보존

    2026-10-22 — 막혀 있다. 모델 정보는 엑셀로만 바꾼다. 함수는 지우지
    않는다 — 지우면 되살릴 자리를 잊는다.

    부르는 곳: admin v2 — mdlRefresh() · loadModels() · saveModels() / 앱 — 없음
    
```

## def _get_project_types

```
프로젝트의 유형 목록.

    엑셀로 올라온 모델은 유형(dev_type)이 붙어 있는데 이 목록에는 없을 수
    있다. 챔버가 그랬다 — 모델 14개가 'DEP챔버' 인데 목록이 비어 있어서
    admin 표에서 유형 칸이 '—' 로 보였고(있는 값을 못 그림), 그 줄을 저장하면
    빈 값으로 덮여 주차별 현황의 'Dep 챔버' 줄이 통째로 비었다.
    그래서 실제로 쓰이는 유형을 목록에 합쳐서 돌려준다.

    2026-10-28 — 그 합치기 때문에 **삭제가 안 먹었다.**

    Min: "유형 삭제 안되고 추가도 안돼"

    목록에서 '함체' 를 지우면 저장은 됐는데, 다시 읽을 때 모델의
    dev_type 을 보고 '함체' 를 도로 끼워 넣었다. 지운 사람 눈에는
    아무 일도 안 일어난 것으로 보인다.

    그래서 **지운 것은 따로 적어 둔다**(types_removed). 모델에 그 값이
    남아 있어도 목록에는 안 올린다 — 모델 칸의 값은 그대로 둔다
    (화면에 "모델에 입력된 값은 유지됩니다" 라고 적혀 있다).
    나중에 손으로 다시 더하면 그 적어 둔 것에서 빠져 되살아난다.

    쓰는 곳: get_admin_project_types · get_project_types
    
```

## def get_project_types

```
프로젝트의 모델 유형 목록 (앱).

    부르는 곳: admin v2 — loadProjectTypes() · loadTypes() · saveTypes() / 앱 — 없음
    
```

## def get_admin_project_types

```
프로젝트의 모델 유형 목록 (admin).

    부르는 곳: admin v2 — loadProjectTypes() · loadTypes() · saveTypes() / 앱 — 없음
    
```

## def save_project_types

```
프로젝트별 유형 목록 저장.

    유형은 보드에서 줄을 묶는 기준이라, 통째로 갈아끼우면 그 유형으로 묶이던
    줄이 사라진다. 바로 위 GET 에는 관리자 확인이 걸려 있는데 이 PUT 만
    빠져 있었다.

    부르는 곳: admin v2 — loadProjectTypes() · loadTypes() · saveTypes() / 앱 — 없음
    
```

## def get_project_status_note

```
프로젝트 현황 메모 (앱 상세).

    부르는 곳: admin v2 — back.onclick() / 앱 — 없음
    
```

## def put_project_status_note

```
프로젝트 현황 메모 저장 (앱 프로젝트 화면에 표시).

    2026-10-22 — 막혀 있다. 현황 글은 프로젝트 전체를 보류 · 드롭으로
    돌리는 근거라서(_project_hold), 모델 정보와 같은 기준을 따라야 한다.

    부르는 곳: admin v2 — back.onclick() / 앱 — 없음
    
```

## def get_weekly_plan

```
프로젝트 주차별 계획 조회 (앱용)

    부르는 곳: admin v2 — loadWeekMarks() / 앱 — project_overview_screen.dart _loadBloom()
           · model_list_screen.dart _loadMarkedWeeks()
    
```

## def admin_upload_weekly_plan

```
주차별 계획 엑셀 업로드 → 첫 시트를 PNG로 변환 → 저장 (보고서 엑셀과 동일 방식)

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _plan_sheet_models

```
주차 양식의 왼쪽 칸에서 모델 정보를 읽는다.

    우리 양식은 한 줄이 한 모델이다 — 누구인지(파트넘버·모델명·유형·구분)
    와 그 모델 값(판가·재료비·PO·실적)이 주차 칸 왼쪽에 같이 있다.
    남이 만든 파일에는 이 머리글이 없으니 빈 목록이 나오고, 그러면
    예전처럼 주차 숫자만 들어간다.

    쓰는 곳: _plan_models_anywhere · admin_plan_file_apply · admin_plan_file_preview
    
```

## def _plan_models_anywhere

```
어느 시트든 모델 줄이 있는 곳 → (시트이름, [줄]).

    주차 머리글이 없는 파일(옛 모델 등록 양식)도 올리는 곳 하나로 받으려고
    쓴다. 모델 줄이 가장 많은 시트를 고른다.

    쓰는 곳: admin_plan_file_apply · admin_plan_file_preview
    
```

## def _plan_process_peek

```
개발 프로세스 일정표인가 → {'sheet','rows','steps'} 또는 None.

    단계 머리글('01 FA PO' 처럼 숫자로 시작)이 둘 이상이면 일정표로 본다.
    주차 양식에는 그런 머리글이 없어서 서로 헷갈리지 않는다.

    쓰는 곳: admin_plan_file_preview
    
```

## def _plan_over

```
'덮어쓰기' 체크를 눌렀는가. 안 보내면 False (= 빈 칸만 채움).

    쓰는 곳: admin_plan_file_apply
    
```

## def _plan_field_empty

```
그 칸이 '비어 있는가'.

    숫자 칸은 0 도 비어 있는 것으로 본다. PO 0 은 'PO 가 없다' 지
    '0 대를 받았다' 가 아니고, 화면에서도 빈 칸처럼 보인다.

    쓰는 곳: _plan_apply_models · _plan_model_changes
    
```

## def _plan_model_changes

```
등록된 모델과 대조 → (바뀌는 줄, 새로 생길 줄).

    빈 칸은 '그대로 둬라' 다. 매주 여는 파일에 원가가 같이 있으니,
    실수로 비운 칸이 값을 지우면 안 된다.

    쓰는 곳: admin_plan_file_preview
    
```

## def _plan_apply_models

```
모델 값을 넣는다. 없는 모델은 만든다 → {'updated','created','filled','over'}

    overwrite=False (기본) 면 **비어 있던 칸만** 채운다. 값이 있는 칸은
    건드리지 않는다 — 옛 파일을 다시 올려도 손으로 고친 값이 안 돌아간다.
    덮어쓰려면 미리보기에서 골라야 한다.

    쓰는 곳: admin_plan_file_apply
    
```

## def _plan_apply_week_notes

```
'미달 사유' 줄 → 화면의 주차 미달 사유와 같은 자리에 넣는다.

    2026-10-22 — 화면에서 하던 두 가지를 글자 규칙으로 옮겼다. 사유를
    적는 자리가 화면과 엑셀 두 군데라 서로 덮어쓰고 있었는데, 화면 쪽을
    닫으려면 화면에서만 되던 일이 엑셀에서도 돼야 한다.
      · 종류 — '참고:' 로 시작하면 참고, 아니면 문제.
               ('참고' 는 일부러 덜 출하한 주라 지연으로 안 센다)
      · 지우기 — '-' 한 글자면 그 주 사유를 지운다.
                 빈 칸은 '그대로 둬라' 이므로 지우는 뜻이 될 수 없다.
                 (전환주차 칸이 쓰는 규칙과 같다)

    쓰는 곳: admin_plan_file_apply
    
```

## def _pbx_diff

```
엑셀 행 ↔ 등록 모델 대조표를 만든다. 저장은 하지 않는다.

    쓰는 곳: _pbx_apply_rows · admin_plan_file_apply · admin_plan_file_preview
    
```

## def _pbx_apply_rows

```
읽어온 주차 행을 모델에 넣는다 → {'month','applied','unmatched'}.

    /plan-file/apply 가 하는 일과 같다. 하바 현황 엑셀처럼 '주차표가 딸려
    오는 다른 파일' 에서도 같은 계산을 쓰려고 떼어 놨다 — 두 벌로 두면
    언젠가 한쪽만 고쳐진다.

    쓰는 곳: _pbx_apply_sheet_months
    
```

## def _pbx_apply_sheet_months

```
시트 하나에 딸린 주차표를 달별로 반영한다. 없으면 빈 목록.

    시트 **하나**만 본다. 하바 현황 파일에는 W6~W40 스냅샷이 서른 몇 장
    들어 있고 장마다 그 시점의 주차표가 붙어 있다. 전부 반영하면 지난
    스냅샷이 최신 값을 덮는다. 올린 사람이 말하는 '지금' 은 마지막 장이다.

    쓰는 곳: admin_import_status_excel
    
```

## def _pbx_open_upload

```
업로드된 엑셀을 연다 → (원본 파일명, 워크북)

    여는 길에 원본을 보관함에 한 벌 남긴다(upload_store).

    쓰는 곳: _pbx_read_upload · admin_plan_file_apply · admin_plan_file_preview
    
```

## def _pbx_pick_sheet

```
주차표가 있는 시트를 고른다. 못 고르면 이유를 말하고 멈춘다.

    쓰는 곳: _pbx_pick_months · _pbx_read_upload
    
```

## def _pbx_pick_months

```
파일에 든 달을 전부 읽는다 → [parsed, ...]. 고른 달이 있으면 맨 앞.

    한 파일에 여러 달이 오는 건 드문 일이 아니다 — 양식 받기가 몇 달치를
    한 파일로 내려주고, 1년치 계획을 한 번에 올리기도 한다. 그때 화면이
    보고 있는 달 하나만 넣으면 나머지 열두 달이 조용히 버려진다.

    달을 하나도 못 찾으면 _pbx_pick_sheet 와 똑같은 말로 멈춘다 — 그 말을
    위에서 받아 '주차표 없는 파일' 로 넘긴다.

    쓰는 곳: admin_plan_file_apply · admin_plan_file_preview
    
```

## def _pbx_read_upload

```
열기 + 시트 고르기를 한 번에 (반영 단계에서 쓴다)

    쓰는 곳: main.py 안에서는 안 쓴다 (테스트 · 예전 코드)
    
```

## def get_automotive_summary

```
자동차사업부 제품 요약 — 앱 화면이 그리는 값.

    수량·금액을 앱에서 다시 계산하지 않게 여기서 낸다.
    Admin 과 앱이 같은 숫자를 보게 하려면 계산이 한 군데 있어야 한다.

        판가   = 재료비 + 공정비 + 관리이윤 + 감가상각 + 물류
        원가   = 판가 − 관리이윤 (관리이윤은 원가가 아니다)
        원가율 = 원가 ÷ 판가
        견적   = 엑셀 '판가' 열 — 외화 단가 × 환율로 적어 둔 참고값.
                 판가와 다를 수 있고, 개발품은 비어 있다.

    묶음 원가율은 제품별 원가율의 평균이 아니라 물량으로 가중한다.
    한 대 팔리는 제품과 백만 대 팔리는 제품을 같은 무게로 두면 안 된다.

        묶음 원가율 = Σ(원가 × 물량) ÷ Σ(판가 × 물량)

    부르는 곳: admin v2 — 없음 / 앱 — automotive_service.dart project()
    
```

## def get_automotive_division_summary

```
자동차사업부 전체 요약 — 앱 '고객사 목록' 화면이 그리는 값.

    고객사별 합계를 앱에서 다시 더하지 않게 여기서 낸다.
    제품 단위 계산은 /projects/{key}/automotive-summary 한 곳에만 두고
    여기서는 그 결과를 고객사별로 모으기만 한다. 두 화면이 갈리지 않게.

    부르는 곳: admin v2 — back.onclick() / 앱 — automotive_service.dart division()
    
```

## def _auto_projects

```
자동차사업부 프로젝트 (라벨·별칭까지) — 고객사 이름을 여기에 맞춘다.

    쓰는 곳: _auto_diff · admin_auto_import_apply · get_automotive_division_summary
    
```

## def _auto_read_upload

```
업로드된 엑셀을 열어 제품표를 읽는다 → (파일명, parsed, 시트목록)

    여는 길에 원본을 보관함에 한 벌 남긴다(upload_store).

    쓰는 곳: admin_auto_import_apply · admin_auto_import_preview
    
```

## def _auto_diff

```
엑셀 행 ↔ 등록된 제품 대조표. 저장은 하지 않는다.

    쓰는 곳: admin_auto_import_preview
    
```

## def admin_auto_import_preview

```
올린 파일이 무엇을 어디로 넣는지 먼저 보여준다. 저장하지 않는다.

    부르는 곳: admin v2 — aiFile.onchange() / 앱 — 없음
    
```

## def admin_auto_import_apply

```
미리보기에서 확인한 내용을 저장한다.

    부르는 곳: admin v2 — onclick() / 앱 — 없음
    
```

## def admin_add_model_alias

```
'이 품번도 그 모델이다' 를 적어 둔다.

    엑셀에 적힌 품번이 우리 쪽 등록 품번과 다를 때 쓴다. 안 적어 두면
    올릴 때마다 같은 물건이 새 모델로 하나씩 더 생긴다.

    부르는 곳: admin v2 — back.onclick() / 앱 — 없음
    
```

## def _form_only

```
사업부 양식이 대신하는 길이면 여기서 끊는다.

    각 업로드 함수의 **첫 줄**에서 부른다. 읽기 시작한 뒤에 막으면 파일을
    이미 받아 놓고 버리는 꼴이라, 보관함에도 쓸데없는 원본이 쌓인다.

    쓰는 곳: admin_auto_import_apply · admin_auto_import_preview · admin_import_status_excel
          · admin_models_import 외 2곳
    
```

## def _df_norm

```
고객사·프로젝트 이름 비교용 — 공백과 기호를 떼고 소문자로.

    엑셀에는 'EPC POWER' · 'EPC Power' · 'epc power' 가 섞여 들어온다.
    사람이 적는 칸이라 띄어쓰기도 제각각이다.

    쓰는 곳: _df_keys · _df_model_key · _df_pick_model · _ds_pick_model 외 1곳
    
```

## def _df_keys

```
이름 하나 → 맞춰 볼 열쇠들 (2026-10-27).

    Min: "TC 같은 경우 일 보고에는 TC라고 작성되어 있고 모델 목록에는
         TC (Tele...) 이렇게 적혀있는데도 연결이 안되는건가"

    같은 것을 세 가지로 적는다.
        일 보고        TC
        모델 목록      TC (Telemaetry Cabinet)
        프로젝트 이름  Telemaetry Cabinet

    _df_norm 은 괄호를 **지운다**. 그래서 'TC (Telemaetry Cabinet)' 이
    'tctelemaetrycabinet' 이 되는데, 이건 'telemaetrycabinet' 과도
    'tc' 와도 안 맞는다 — 괄호를 붙여 적을수록 더 안 맞았다.

    그래서 괄호를 기준으로 **앞·안을 따로** 열쇠로 만든다.
        'TC (Telemaetry Cabinet)' → ['tctelemaetrycabinet', 'tc', 'telemaetrycabinet']
    짧은 조각('tc')도 넣는다. 짧은 열쇠는 **정확히 같을 때만** 맞고
    (앞글자 비교는 세 자 이상일 때만 한다) 엉뚱한 데 안 걸린다.

    쓰는 곳: _df_find_project · _df_owner_index · _df_typo_project
    
```

## def _df_owner_index

```
사업부 안에서 '엑셀에 적힌 이름 → 프로젝트 키' 색인.

    프로젝트 설정에 이미 별칭(aliases)이 들어 있다. 거래처를 부르는 이름이
    사람마다 달라서 만들어 둔 것인데, 여기서도 그대로 쓴다.
      예) 'Stellantis' · '스텔란티스' · '스탈란티스' → auto_stellantis

    쓰는 곳: _daily_board_items · admin_dev_schedule_apply · admin_dev_schedule_preview
          · admin_division_form_apply 외 1곳
    
```

## def _df_slug

```
엑셀에 적힌 이름 → 프로젝트 키로 쓸 영문 토막.

    'CORVA BOP ASSY' → 'corva_bop_assy'. 한글만 있는 이름처럼 영문이
    하나도 안 남으면 짧은 지문을 쓴다 — 키는 주소에도 들어가서
    영문·숫자만 받는 자리가 있다.

    쓰는 곳: _df_new_project_rows
    
```

## def _df_new_project_rows

```
못 찾은 줄을 이름으로 묶어 '이런 프로젝트를 만들겠다' 목록을 낸다.

    만들지는 않는다. 미리보기가 먼저 보여 주고, 사람이 반영을 눌렀을 때
    같은 규칙으로 실제로 만든다. 오타로 생긴 이름(예: TC 가 있는데
    'Telemaetry Cabinet')도 여기 뜨니, 반영 전에 눈으로 걸러진다.

    쓰는 곳: admin_division_form_apply · admin_division_form_preview
    
```

## def _display_name

```
그 이름을 화면에 어떻게 띄울까. 모르면 빈 글자.

    쓰는 곳: _df_create_projects
    
```

## def _df_create_projects

```
_df_new_project_rows 가 낸 목록을 실제로 만든다 → 만든 것만 돌려준다.

    쓰는 곳: admin_division_form_apply
    
```

## def _df_project_sync

```
양식에 없는 프로젝트는 끈다. 다시 적히면 켠다 (2026-10-28).

    Min: "양식 엑셀에 있는 프로젝트만 떠야 되는데 왜 없는것도 그대로 있는거야"

    블룸 양식에서 이름이 바뀌었다.
        CORVA BOP          → BOP 기구
        CORVA BOP ASSY     → BOP ASSY
        Telemaetry Cabinet → TC (Telemaetry Cabinet)
        CORVA EFM KPE(PB)  → 아예 빠짐

    프로젝트 목록은 **양식이 만든다**. 그래서 이름이 바뀌면 새것이 하나
    생기고 옛것이 그대로 남는다 — 품목 10개짜리 양식을 올렸는데 화면에는
    15줄이 떴고, 어느 쪽이 지금 것인지 알 수가 없다.

    세 가지를 지킨다.
      1) **양식이 만든 것만** 건드린다. 가르는 기준은 '어디에 적혀
         있는가' 다 — /data 에 쌓인 것만 양식이 만든 것이고,
         config/projects.json 에 손으로 적은 목록(반도체·공용)은
         손대지 않는다 (_cl.is_runtime_project).

         처음에는 created_by 표시로 갈랐는데 하나도 안 걸렸다. 그 표시를
         넣기 전에 생긴 프로젝트가 이미 서버에 쌓여 있었다 — 정작 지워야
         할 옛것들이 전부 표시가 없는 것들이었다.
      2) **지우지 않고 끈다.** 쌓인 주차별 계획·실적이 그대로 남는다.
         이름이 한 달 빠졌다가 돌아오면 켜 주고 숫자는 살아 있다.
      3) 일 보고를 담는 자리(bloom_main)는 건드리지 않는다 — 그건
         프로젝트가 아니라 창고다. 꺼진 채로 돌아야 맞다.
      4) **한 장이 사업부 전체인 양식에서만** 한다. 반도체는 Chamber ·
         CUP · 엔클로저 · HRVA 를 **파일 따로** 올린다 — 거기서 이 규칙을
         돌리면 CUP 한 장 올렸다고 나머지 셋이 통째로 사라진다.
         반도체형은 한 장이 프로젝트 하나라서 아예 건너뛴다.

    품목이 한 건도 안 읽힌 양식에서는 아무것도 끄지 않는다. 빈 장을
    잘못 올렸을 때 사업부가 통째로 사라지는 게 제일 나쁘다.

    dry=True 면 아무것도 안 바꾸고 '무엇이 바뀔지' 만 돌려준다 —
    미리보기가 쓴다. 반영 전에 사라질 목록을 눈으로 보고 누른다.

    쓰는 곳: admin_division_form_apply · admin_division_form_preview
    
```

## def _df_price_preview

```
반영하기 전에 '판가가 바뀌는 품목' 만 뽑아 본다 (2026-10-28).

    저장은 안 한다. 판가는 지난 주차 매출까지 흔들 수 있는 값이라,
    누르기 전에 무엇이 얼마로 바뀌는지 눈으로 보고 들어가야 한다.

    쓰는 곳: admin_division_form_preview
    
```

## def _df_week_tag

```
양식의 기준 주차 → 판가 구간 시작점 ('2026-W43').

    못 읽으면 빈 글자 — 부르는 쪽이 오늘 주차로 떨어뜨린다.

    쓰는 곳: admin_division_form_apply · admin_division_form_preview
    
```

## def _df_apply_price

```
양식으로 판가·재료비가 바뀌면 **그 주차부터** 새 값 (2026-10-28).

    Min: "만약에 내가 W43주차에 변경된 금액으로 올렸어 그러면 W42까지는
         기존에 있던 금액 그대로 지표가 되어야 하고 43주차 부터 변경된
         금액으로 지표가 되기를 원하는거야"

    전에는 양식이 판가를 그냥 덮어썼다. 매출은 `판가 × 그 주차 실적` 이라,
    10월에 $7,243 → $7,800 으로 고쳐 올리면 **8월에 나간 물량 매출까지**
    $7,800 으로 다시 계산됐다. 지난달 보고서 숫자가 조용히 바뀐다.

    구간을 쌓을 자리(phases)는 처음부터 있었다 — 매출 계산도 그걸 본다
    (_phase_at). 그런데 구간을 만드는 길이 admin 모델 표 저장 한 곳뿐이었고
    그 길이 막혀 있어서(_write_off), 실제 데이터에는 구간이 **한 건도**
    없었다. 이제 양식이 만든다.

    tag 는 **양식의 기준 주차**다 (실적이 적힌 마지막 주차, as_of_week).
    오늘 주차로 찍으면 안 된다 — W43 양식을 다음 주 월요일에 올리면
    W44 부터 바뀌어서, 정작 W43 실적이 옛 판가로 계산된다.

    바뀐 게 없으면 아무것도 안 한다. 반환은 화면에 보여줄 요약.

    쓰는 곳: admin_division_form_apply
    
```

## def _df_digits

```
글자 속 숫자 묶음만 뽑는다 (고객사 오타 맞출 때).

    쓰는 곳: _df_typo_project
    
```

## def _df_dam1

```
글자 차이가 1 이내인가 (자리바꿈 포함). 넘으면 바로 False.

    쓰는 곳: _df_typo_project
    
```

## def _df_typo_project

```
오타로 보이는 이름 → 프로젝트 키. 애매하면 빈 글자.

    쓰는 곳: _df_find_project
    
```

## def _df_find_project

```
엑셀에 적힌 이름이 어느 프로젝트인가. 못 찾으면 빈 글자.

    notes 를 주면 오타로 붙인 이름을 {적힌 이름: 프로젝트 키} 로 담아 준다.

    쓰는 곳: _daily_board_items · _df_plan · _df_price_preview · _df_project_sync 외 4곳
    
```

## def _df_model_key

```
모델을 가리키는 열쇠 — (품번, 이름) 둘 다 다듬어서.

    쓰는 곳: main.py 안에서는 안 쓴다 (테스트 · 예전 코드)
    
```

## def _df_pick_model

```
이미 등록된 모델 중에서 이 줄에 해당하는 것을 찾는다.

    파트넘버가 먼저다 — 이 시스템에서 모델을 가르는 열쇠이기 때문이다.
    품번이 안 적혀 있을 때만 이름으로 찾는다.

    쓰는 곳: _df_issue_apply · _df_plan · _df_price_preview · admin_division_form_apply
    
```

## def _df_typo_warnings

```
오타로 붙인 이름을 사람이 읽을 줄로. 조용히 고치지 않는다.

    쓰는 곳: admin_division_form_apply · admin_division_form_preview
    
```

## def _df_plan

```
읽은 줄들을 프로젝트별로 묶고, 어떤 모델이 새로 생기는지 가린다.

    미리보기와 실제 반영이 **같은 함수**를 쓴다. 따로 두면 미리보기에서
    본 것과 저장되는 것이 어긋난다 — 그러면 미리보기가 쓸모없어진다.

    쓰는 곳: admin_division_form_preview
    
```

## def _df_issue_apply

```
양식 이슈 한 줄 → 진행/해결 반영 (issue_status). 결과 말을 돌려준다.

    품번이 가리키는 모델이 있으면 그 모델, 없으면 프로젝트 단위.
    dry 면 아무것도 안 바꾸고 '올리면 어떻게 되는지' 만 본다 (미리보기).

    쓰는 곳: admin_division_form_apply · admin_division_form_preview
    
```

## def _form_weekly_note

```
사업부 양식의 주차 계획이 보드에 안 뜨는 사업부면 한 줄 알려 준다.

    2026-10-25 결정 — ESS · 블룸의 주차 현황 보드는 **일 보고 자료만**
    읽는다. 두 사업부는 자료가 날마다 들어와서 그쪽이 늘 최신이고, 두
    곳에서 같은 주차를 받으면 화면의 숫자가 어느 엑셀에서 왔는지 아무도
    모르게 된다.

    그래서 사업부 양식의 W41·W42 칸은 모델에 저장은 되지만(판가·자재비와
    같이 쓰인다) 보드에는 안 뜬다. 올리는 사람이 "적었는데 왜 안 보이지"
    하고 헤매지 않게 미리보기에 적어 준다.

    쓰는 곳: admin_division_form_preview
    
```

## def _df_stale_models

```
양식에 한 번도 안 나온 기존 모델 → [{project_key, id, name}]

    왜 필요한가 (2026-10-26)
      양식 한 장이 그 사업부의 모델 목록을 통째로 바꾼다. 그런데 지금까지
      반영은 **더하고 고치기만** 했다. 그래서 옛 모델이 그대로 남아,
      양식에서 지운 줄이 화면에서는 안 지워졌다. 모델은 엑셀로만 바꾸게
      해 둔 터라(MODELS_READONLY) 화면에서 지울 길도 없어 막혔다.

    조심할 것
      · **양식에 나온 프로젝트만** 본다. 양식에 한 줄도 없는 프로젝트의
        모델까지 지우면, 한 사업부 파일로 옆 프로젝트가 비어 버린다.
      · 지우는 것은 사람이 눈으로 보고 고르게 한다 — 여기서는 '이런 게
        남았다' 목록만 만든다.

    seen 은 {프로젝트키: {그 양식이 건드린 모델의 id(파이썬 id)}} 다.
    이름이나 품번으로 맞추면 같은 이름이 둘일 때 틀린다.

    쓰는 곳: _df_plan · admin_division_form_apply
    
```

## def admin_division_form_download

```
그 사업부 양식을, **지금 등록된 내용을 채워서** 내려준다 (2026-10-27).

    Min: "엑셀 양식 다운받기 버튼을 엑셀 올리기 옆에 둬서 … 10월이랑
         11월 주차별이 보이게끔 … 이미 있는 내용들은 그대로 반영되어서"

    빈 양식을 주지 않는 이유 — 담당자가 처음부터 다시 적으면 (1) 있는
    품목을 또 타자 치고 (2) 오타가 나면 새 모델이 하나 더 생기고
    (3) 지난달 주차 계획이 사라진다. 채워 주면 고칠 것만 고쳐 올린다.

    month  기준 달 (YYYY-MM). 없으면 이번 달.
    months 몇 달치 주차 블록을 깔지 (1~6). 기본 2 — 이번 달과 다음 달.

    부르는 곳: admin v2 — fd.onclick() / 앱 — 없음
    
```

## def admin_dev_schedule_download

```
개발 일정 양식을, **적혀 있던 날짜를 채워서** 내려준다 (2026-11-02).

    Min: "양식 받기에 양식 올리기 양식이랑 개발 일정 양식 두 개 다운
         받을 수 있게 해야되는데"

    지금까지는 내가 손으로 만들어 보냈다. 사업부마다 한 번씩, 품목이
    늘 때마다 또. 받을 길이 화면에 없으면 결국 사람을 거쳐야 한다.

    구분이 **개발**인 품목만 담는다 — 양산은 이 양식에 설 자리가 없다.

    부르는 곳: admin v2 — fv.onclick() / 앱 — 없음
    
```

## def admin_division_form_preview

```
올린 양식이 무엇을 바꾸는지 먼저 보여준다. 저장하지 않는다.

    부르는 곳: admin v2 — fd.onclick() · _divFormSend() / 앱 — 없음
    
```

## def admin_division_form_apply

```
미리보기에서 확인한 내용을 저장한다.

    create_projects  양식에 처음 보는 프로젝트 이름이 있으면 만들까
      (2026-10-26) 기본은 True 다. 전에는 등록 안 된 이름의 줄을 통째로
      버렸다 — 블룸 양식 84줄 중 81줄이 그렇게 사라졌다. 이제는 그
      이름으로 프로젝트를 만들고 거기에 넣는다. 무엇이 생길지는
      미리보기가 먼저 보여 준다.

    remove_missing  양식에 없는 기존 모델도 지울까 (2026-10-26)
      기본은 False 다. 양식 한 장으로 옛 모델이 조용히 사라지면,
      다음 달 양식을 덜 채워 올린 날 그 프로젝트가 통째로 비어 버린다.
      그래서 미리보기로 '지울 목록' 을 보여 주고, 사람이 켰을 때만 지운다.

    부르는 곳: admin v2 — fd.onclick() · _divFormSend() / 앱 — 없음
    
```

## def admin_plan_file_preview

```
올린 파일이 무엇을 바꾸는지 먼저 보여준다. 저장하지 않는다.

    부르는 곳: admin v2 — _pfRerun() · pfFile.onchange() / 앱 — 없음
    
```

## def admin_plan_file_apply

```
미리보기에서 확인한 내용을 저장한다.

    overwrite 를 보내지 않으면 모델 칸은 **비어 있던 것만** 채운다.

    부르는 곳: admin v2 — _pfModelsOnly() · onclick() / 앱 — 없음
    
```

## def admin_delete_weekly_plan

```
주차별 계획 삭제

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_update_report

```
보고서 고치기 (잠김).

    부르는 곳: admin v2 — executeDelete() · __moreBtn.onclick() · _loadSalesForSection()
           · _flushManualEditAlarmSession() 외 1곳 / 앱 — 없음
    
```

## def admin_report_edit_done

```
편집 완료: 저장된 before snapshot과 현재 상태 비교 → 알람 1회 발송

    부르는 곳: admin v2 — _flushManualEditAlarmSession() / 앱 — 없음
    
```

## def admin_upload_section_file

```
보고서 섹션에 파일 붙이기 (잠김).

    부르는 곳: admin v2 — _flushManualEditAlarmSession() / 앱 — 없음
    
```

## def admin_parse_section_xlsx

```
섹션에 첨부된 xlsx 파일을 파싱해서 models/weeks 리턴 (판가 입력용).

    부르는 곳: admin v2 — _loadSalesForSection() / 앱 — 없음
    
```

## def admin_download_section_file

```
보고서 섹션에 붙인 파일 내려받기.

    부르는 곳: admin v2 — _loadXlsxPreviews() / 앱 — 없음
    
```

## def admin_xlsx_preview

```
보고서에 붙인 엑셀을 표로 미리보기.

    부르는 곳: admin v2 — _loadXlsxPreviews() / 앱 — 없음
    
```

## def admin_polish_text

```
보고서 글을 AI 로 다듬기 (잠김).

    부르는 곳: admin v2 — _flushManualEditAlarmSession() / 앱 — 없음
    
```

## def admin_toggle_hide

```
보고서 숨기기/보이기 (잠김).

    부르는 곳: admin v2 — __moreBtn.onclick() / 앱 — 없음
    
```

## def _resync_notes_from_latest

```
reports_latest.json 기준으로 notes.json 자동동기화 카드를 재생성

    쓰는 곳: admin_delete_manual_report · admin_toggle_hide
    
```

## def admin_delete_doc

```
PPT 파일 단위 삭제: reports_latest.json + 관련 폴더/파일 전부 정리

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_delete_docs_batch

```
PPT doc_id 여러 개 일괄 삭제

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_delete_card

```
카드(product) 1장 단위 삭제

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_reset

```
자료 초기화 (잠김).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _kmonth

```
'2026-09' → '9월'. 경영진 답변에는 ISO 표기 대신 이걸 쓴다.

    쓰는 곳: _month_shipment_answer · _week_shipment_answer
    
```

## def _week_shipment_answer

```
주차 단위 출하 수량/매출 확정 답변(LLM 우회). 데이터가 없으면 None.

    쓰는 곳: chat
    
```

## def _month_shipment_answer

```
월 단위 출하 수량/매출 확정 답변(LLM 우회). 데이터가 없으면 None.

    쓰는 곳: chat
    
```

## def chat

```
admin v2 전체 데이터 기반 챗봇

    부르는 곳: admin v2 — 없음 / 앱 — chat_service.dart ask()
    
```

## def rag_status

```
벡터 인덱스 상태 (몇 조각이 언제 만들어졌는지).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def rag_rebuild

```
지금 데이터로 벡터 인덱스를 다시 만든다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _extract_tables_from_pptx

```
PPT 파일에서 모든 표를 추출.

    반환 형식: [
      {
        "slide_index": int,   # 1부터 시작
        "slide_title": str,   # 첫 번째 텍스트 도형(있으면)
        "nearby_text": str,   # 슬라이드의 모든 텍스트를 이어붙인 것
        "rows": [[cell, cell, ...], ...]
      },
      ...
    ]

    쓰는 곳: _find_shipping_plan_tables
    
```

## def _is_shipping_plan_table

```
표가 '출하 계획 및 실적' 관련인지 판정.

    쓰는 곳: _find_shipping_plan_tables
    
```

## def _find_shipping_plan_tables

```
PPT에서 출하 계획 관련 표만 추출.

    쓰는 곳: _auto_extract_kpi_from_pptx
    
```

## def _pick_primary_shipping_table

```
여러 표 중 진짜 출하 계획 표를 하나만 선택.

    판별 기준:
    1. R1 첫 셀에 '구분' 포함
    2. R1에 '누적 합계' 또는 '누적합계' 포함
    3. 데이터 행 첫 컬럼에 프로파일 등록 모델명 존재

    쓰는 곳: _auto_extract_kpi_from_pptx
    
```

## def _shipping_table_to_kpi_data

```
표 → KPI 스키마로 변환.

    반환:
    {
      "project_key": "major_module",
      "report_month": "2026-07",
      "report_year": 2026,
      "models": [
        {
          "model_id": "major_module::EFEM",
          "display_name": "EFEM",
          "months": {"2026-04": {"plan": 16, "actual": 9}, ...},
          "weeks": {"2026-W27": {"plan": 2, "actual": 2}, ...},
          "cumulative": {"po": 74, "shipped": 37}
        }
      ],
      "warnings": [...]
    }

    쓰는 곳: _auto_extract_kpi_from_pptx
    
```

## def _load_project_profiles

```
프로젝트 프로파일 전체 로드.

    쓰는 곳: _get_project_profile
    
```

## def _get_project_profile

```
특정 프로젝트 프로파일 반환. 없으면 None.

    쓰는 곳: _auto_extract_kpi_from_pptx · _pick_primary_shipping_table
          · _shipping_table_to_kpi_data
    
```

## def _auto_extract_kpi_from_pptx

```
PPT 업로드 후 자동 KPI 추출 훅.

    실패해도 예외를 던지지 않음 (업로드는 성공 유지).
    프로파일이 등록된 프로젝트만 파싱 시도.

    쓰는 곳: upload_ppt
    
```

## def _apply_kpi_from_pptx

```
PPT에서 추출한 KPI 데이터를 kpi_history.json에 병합.

    - 기존 필드(efem, vtm, type, source, updated_at) 유지
    - 신규 필드(models, cumulative) 추가
    - dry_run=True: 실제 저장 안 하고 변경 예정 결과만 반환
    - dry_run=False: 실제 저장

    쓰는 곳: _auto_extract_kpi_from_pptx
    
```

## def _load_kpi_history

```
kpi_history.json 로드. 없으면 빈 구조.

    쓰는 곳: _apply_kpi_from_pptx · _build_major_module_issue_lines
          · _build_major_module_kpi_card · admin_kpi_get 외 4곳
    
```

## def _save_kpi_history

```
KPI(출하 실적 · 손익) 기록을 저장한다.

    쓰는 곳: _apply_kpi_from_pptx · admin_kpi_replace_issue_lines · admin_kpi_upload_excel
          · admin_kpi_upsert_month 외 1곳
    
```

## def _iso_week_of

```
date -> 'YYYY-Wnn'.

    쓰는 곳: _build_major_module_kpi_card
    
```

## def _month_key

```
날짜 → 'YYYY-MM'.

    쓰는 곳: _build_major_module_kpi_card · _shipping_table_to_kpi_data
    
```

## def _month_label

```
'2026-07' -> '7월'.

    쓰는 곳: _build_major_module_kpi_card · chat
    
```

## def _week_label

```
'2026-W28' -> 'W28'.

    쓰는 곳: _build_major_module_kpi_card
    
```

## def _slice_window

```
    items: dict[key -> row], key는 정렬 가능한 문자열
    key_fn_today: 오늘의 기준 key
    past 개 이전 ~ future 개 이후까지 반환. 실제 있는 것만.

    쓰는 곳: _build_major_module_kpi_card
    
```

## def _build_major_module_kpi_card

```
    kpi_history.json 기반으로 메이저모듈 KPI 카드 생성.
    - 판가 기준 매출 계산
    - 월: 오늘 기준 직전 1개월(실적) + 향후 2개월 = 최대 3개
    - 주: 오늘 기준 직전 0주 + 향후 4주 = 최대 5개

    쓰는 곳: get_project_detail
    
```

## def _build_major_module_issue_lines

```
이슈 라인 로드.
    1) kpi_history.json 에 수동 등록된 값이 있으면 그걸 우선.
    2) 없으면 notes.json 의 메이저모듈 sections 에서 자동 생성:
       - type='sub' 이거나 due_date 있는 아이템을 추출
       - due_date 있으면 severity/show_dday 자동 계산

    쓰는 곳: get_project_detail
    
```

## def _ensure_project

```
KPI 기록에 그 프로젝트 자리가 없으면 빈 틀을 만든다.

    쓰는 곳: admin_kpi_replace_issue_lines · admin_kpi_upsert_month · admin_kpi_upsert_week
    
```

## def _should_overwrite

```
    같은 key가 이미 있을 때 덮어쓸지 판단.
    - existing이 없으면 True
    - actual > plan (actual이 들어오면 무조건 덮음)
    - 같은 type이면 최신 upload가 덮음 (True)

    쓰는 곳: admin_kpi_upsert_month · admin_kpi_upsert_week
    
```

## def admin_kpi_get

```
프로젝트 KPI(손익) 자료.

    부르는 곳: admin v2 — closeModal() / 앱 — 없음
    
```

## def admin_kpi_upsert_month

```
KPI 월 자료 고치기 (잠김).

    부르는 곳: admin v2 — closeModal() / 앱 — 없음
    
```

## def admin_kpi_upsert_week

```
KPI 주 자료 고치기 (잠김).

    부르는 곳: admin v2 — closeModal() / 앱 — 없음
    
```

## def admin_kpi_upload_excel

```
    출하실적 엑셀 업로드 → 자동 파싱 → KPI 히스토리 반영.

    엑셀 스키마 (major_module 기준):
    - R1: 빈 행
    - R2: 카테고리 헤더 (PO/실적/잔량/6월/7월/W27~W31 등)
    - R3: 주차 헤더 (W27, W28, ...)
    - R4: 계획/실적 서브헤더
    - R5: EFEM 데이터
    - R6: VTM 데이터
    - R7: 합계 (파생, 저장 안 함)

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_kpi_replace_issue_lines

```
KPI 이슈 줄 바꾸기 (잠김).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _iso_week_number

```
날짜 → ISO 주차 번호.

    쓰는 곳: _compute_sales_summary
    
```

## def _week_to_month

```
W-번호 → 그 주의 목요일이 속한 월 (ISO 규칙)

    쓰는 곳: _compute_sales_summary
    
```

## def _compute_sales_summary

```
    각 주차별로:
      - 과거 → 실적
      - 현재 → 실적 우선, 없으면 계획
      - 미래 → 계획
    매출 = 수량 × 판가
    반환: "7월 74.0만불 · 8월 407.0만불 · W30 89.0만불"

    쓰는 곳: compute_sales_from_data · compute_sales_from_input
    
```

## def parse_sales_excel

```
출하계획 xlsx를 읽어서 models / weeks(plan/actual) 구조로 반환.

    쓰는 곳: _sync_report_to_notes · admin_parse_section_xlsx
    
```

## def compute_sales_from_parsed

```
parsed(xlsx) + prices(만불) → 3박스 요약 문자열 + 구조화 데이터.

    쓰는 곳: _sync_report_to_notes
    
```

## def _find_xlsx_in_section_items

```
섹션 items에서 첫 번째 .xlsx 파일의 서버 URL 추출.

    쓰는 곳: _sync_report_to_notes
    
```

## def _xlsx_url_to_local_path

```
/admin/manual-files/{doc_id}/{filename} → 실제 파일 경로.

    쓰는 곳: _products_to_note_cards · _sync_report_to_notes
    
```

## def compute_sales_from_input

```
외부에서 호출하는 진입점

    쓰는 곳: _sync_report_to_notes · admin_recompute_all_sales · admin_set_sales_input
    
```

## def admin_set_sales_input

```
    body: { division_id, card_title, section_title, sales_input }
    → notes.json 의 해당 section 에 sales_input/sales_summary/sales_computed_at 저장
    → 계산 결과 반환

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def compute_sales_from_data

```
구조화된 sales_data → summary 계산.
    sales_data = {
      "prices": {"EFEM": 65, ...},
      "weeks": [{"week": 27, "models": {"EFEM": {"plan": 2, "actual": 2}}}, ...]
    }

    쓰는 곳: _sync_report_to_notes
    
```

## def admin_recompute_all_sales

```
모든 section의 sales_input 재계산 (판가 정책 바뀔 때 등)

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def register_device_token

```
Flutter 앱이 앱 시작 시 FCM 토큰을 서버에 등록.

    부르는 곳: admin v2 — 없음 / 앱 — fcm_service.dart initialize()
    
```

## def admin_fcm_test

```
알람 시스템 동작 테스트용 엔드포인트.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _default_process

```
개발 공정 13단계의 빈 틀 (반도체 기준).

    쓰는 곳: _apply_dev_status · _apply_report_workbook · _ensure_process
          · admin_import_status_excel 외 3곳
    
```

## def _known_weeks

```
실제로 데이터가 들어 있는 주차 집합. (weekly_summary + 모델 weekly_plan)

    쓰는 곳: chat
    
```

## def _model_key_alias

```
예전 프로젝트 키를 지금 키로 (havaplate → hrva_plate 등).

    쓰는 곳: _apply_report_workbook · _bloom_board_for · _daily_project_board
          · _daily_ship_weeks 외 38곳
    
```

## def _merge_process_keep

```
엑셀에서 읽은 공정을 기존 입력 위에 얹는다 — 빈 칸은 덮지 않는다.

    프로세스 엑셀은 아직 안 채운 칸이 그냥 비어 있다. 그걸 그대로 덮어쓰면
    화면에서 손으로 넣어 둔 예정일·실적일이 통째로 사라진다 (하바플레이트
    17종이 이렇게 비었다). 엑셀에 값이 있는 칸만 반영하고, 빈 칸은 둔다.

    단계 짝은 key → 이름 순으로 맞춘다. 단계 수가 달라도 있는 만큼만 얹는다.

    쓰는 곳: admin_import_unified
    
```

## def _set_fair_dates

```
'FAIR 제출' 단계에 예정일·실제일을 적는다.

    하바플레이트 주간보고·개발현황의 두 칸이 여기로 온다.
      고객요청일 → FAIR 제출 예정일
      가공 완료  → FAIR 제출 실제일 (단, 오늘까지 지난 날짜일 때만)

    가공 완료가 앞으로의 날짜면 아직 한 게 아니다. 예정일만 적고 진행중으로
    둔다. 지난 날짜(오늘 포함)면 그날 한 것으로 보고 완료로 적고, 바로
    다음 단계를 진행중으로 올린다 — 완료 밑이 계속 '대기' 면 지금 무엇을
    하고 있는지가 화면에 안 나온다.

    빈 값은 덮지 않는다 (엑셀에 아직 안 적힌 칸이 기존 입력을 지우면 안 된다).

    쓰는 곳: _apply_dev_status · _apply_report_workbook
    
```

## def _dev_steps_blank

```
단계 이름만 서 있고 날짜 · 상태가 한 칸도 없는가.

    쓰는 곳: get_project_models_detail
    
```

## def _ensure_process

```
개발 품목의 공정 단계. 없으면 기본 13단계를 깔아 준다.

    ── 기본값은 반도체 것이다 (2026-11-02)
    Min: "이거 없어야 되는데 잇는 이유가 뭐야"

    DEV_PROCESS_STEPS 13단계는 반도체사업부의 승인 절차다 (PO 접수 …
    FAIR 승인 … 최종 승인 완료). 그런데 사업부를 안 보고 **모든** 개발
    품목에 깔았다. 자동차 KEFICO INDIA 를 열면 자기 단계(01 T-car …
    06 SOP) 옆에 쓰지도 않는 반도체 13단계가 같이 서 있었다 — 개발
    진행현황 표는 품목들의 단계 이름을 합집합으로 모으기 때문이다.

    게다가 이 함수는 부른 쪽에서 곧바로 저장하는 자리가 많아서, 한 번
    열어 보기만 해도 반도체 단계가 자료에 박혔다.

    그래서 사업부를 안다면 반도체일 때만 깔아 준다. 다른 사업부는 개발
    일정 양식이 올라오기 전까지 단계가 **없는 게 맞다** — 앱도 admin 도
    '공정 데이터 없음' 을 그릴 줄 안다.

    쓰는 곳: _admin_model_alerts · _alert_why · _apply_dev_status · _enrich_model 외 3곳
    
```

## def _ensure_mass_progress

```
양산 모델 weekly_plan 기반 진행률(%)

    쓰는 곳: _apply_plan_matrix · _pbx_apply_rows · admin_plan_file_apply
          · get_weekly_plan 외 1곳
    
```

## def _get_month_weeks

```
YYYY-MM 월의 주차 목록. 규칙 본문은 week_calendar 에 있다.

    쓰는 곳: _board_month_qty · _daily_project_board · _delta_periods
          · _month_of_week_key 외 11곳
    
```

## def _month_of_week

```
'W40' → 그 주차를 소유한 'YYYY-MM'. 규칙 본문은 week_calendar 에 있다.

    쓰는 곳: _week_shipment_answer · chat · hrva_import.py
    
```

## def _latest_data_month

```
모델 weekly_plan / weekly_summary에 데이터가 있는 가장 최근 'YYYY-MM'.

    쓰는 곳: _week_shipment_answer · chat
    
```

## def _note_says_done

```
칸에 적힌 글자가 '끝났다' 는 뜻인가 ('완료' · 'PO 완료').

    '완료 예정' · '미완료' 는 아직 안 끝난 것이다.

    쓰는 곳: admin_dev_schedule_apply (_process_step_done 에도 같은 규칙)
    
```

## def _process_step_done

```
실적일이 있거나, 상태가 '완료' 거나, 칸에 '완료' 라고 적혔으면 완료다.

    양식 머리에 "*완료되었으나 날짜 확인이 어려운 경우 '완료'로 작성" 이라고
    적혀 있다. 그래서 실적 칸뿐 아니라 계획 칸에 '완료' 라고 적힌 것도
    끝난 것으로 센다 (2026-11-05 — 반도체 양식에 계획 줄 '완료' 가 205칸).
    Min: "완료라고 적혀 있는것도 실적 (완료)로 표기해주고"

    쓰는 곳: _enrich_model · _model_alert · _process_rolled · _process_step_active
    
```

## def _process_step_active

```
끝났거나 하고 있는 중.

    쓰는 곳: _process_rolled
    
```

## def _process_rolled

```
지금 어디까지 왔는지 한 자리로 정하고, 뒤는 대기로 맞춘 사본.

        현재 위치 앞  → 적힌 그대로 (실적일 · '완료' 가 있는 단계만 완료)
        현재 위치     → 그대로
        현재 위치 뒤  → 대기 (아직 오지 않은 자리다)

    ── 앞 단계를 완료로 채우지 않는다 (2026-11-05)
    전에는 '지나온 자리' 라며 현재 위치 앞을 전부 완료로 칠했다. 그런데
    715-156359-006 은 05 LA 입고가 끝났어도 03 자재 입고는 '카이저 입고
    필요', 04 가공은 '진행중' 이다 — 끝난 게 아니다.
    Min: "715-156359-006 예시 보니까 전에 완료로 두면 안 될것 같아"
         → "앞 단계 채우기 전부 빼기"
    예외 둘 — 둘 다 '적힌 것' 으로 이미 알 수 있는 경우다.
      · **최종 승인이 끝난 품목은** 앞이 전부 완료다. 다 끝난 건인데
        진행률이 80% 로 남으면 화면이 '진행중' 이라고 말한다.
      · '○○ 승인' 이 끝났으면 바로 앞 '○○ 작성/제출' 도 끝난 것이다
        (LAIR · FAIR · CDR/PRR). 승인은 낸 것을 받는 일이다.

    현재 위치를 정하는 순서
      1) 최종 승인이 진행중이거나 끝났으면 거기가 현재 위치다.
         다 끝난 건이라 앞이 전부 완료가 된다.
      2) 아니면 '진행중' 으로 골라 둔 첫 자리. BV2 를 진행중으로 바꿔 놓으면
         그 뒤는 아직 안 한 일이므로 전부 대기로 내린다.
      3) 그것도 없으면 마지막으로 끝난 자리.

    단계 이름이나 순서에 기대지 않는다 — LAIR 과 FAIR 은 순서가 바뀌고
    BV 는 BV1 에서 끝나기도 한다. 그런 자리는 현재 위치 앞뒤에 놓이면서
    저절로 정리된다.

    저장된 값은 건드리지 않는다. 보여줄 때만 맞춘다.

    쓰는 곳: _model_progress · _process_progress · get_model_process
    
```

## def _process_progress

```
완료로 맞춰진 단계 수 ÷ 전체 단계 수.

    현재 위치 뒤는 대기로 내려가므로 진행률에 안 들어간다.
    진행중도 끝난 게 아니라서 안 센다.

    쓰는 곳: _admin_model_alerts · _apply_dev_status · _apply_report_workbook
          · _cleanup_cdr_prr 외 9곳
    
```

## def _model_progress

```
모델 1개 진행률: 양산=출하/PO, 개발=프로세스 완료율 (0~100)

    쓰는 곳: dashboard · chat_intents.py
    
```

## def _combined_project_progress

```
양산(출하/PO) + 개발(프로세스) 가중 평균 진행률

    쓰는 곳: enrich_card
    
```

## def _inject_weekly_summary

```
양산 모델: weekly_plan이 있으면 앱 표시용 요약 텍스트 생성 (앱 수정 불필요)

    쓰는 곳: get_project_models_detail
    
```

## def _process_current

```
현재(다음) 진행 단계. 계획일·실적일·상태가 하나도 없는 단계는
    아직 일정이 안 잡힌 것으로 보고 '진행중'으로 표시하지 않는다.

    쓰는 곳: _admin_model_alerts · _alert_why · _enrich_model · admin_put_model_process 외 3곳
    
```

## def _model_progress_value

```
모델 1건의 진행률(%). 데이터가 없으면 None → 집계에서 제외.
    - 양산: PO 수량(계획)이 있어야 집계. 출하 0이면 0%.
    - 개발: 공정 단계에 계획일/실적일/상태 중 하나라도 입력돼야 집계.
      (13단계 틀은 자동 생성되므로 단계 존재만으로는 데이터로 보지 않음)

    쓰는 곳: _project_progress_entry
    
```

## def _project_progress_entry

```
프로젝트 하나의 진행률 한 줄 (모델 진행률 평균 · 지연 수).

    쓰는 곳: get_admin_overview · get_projects_progress_summary
    
```

## def get_projects_progress_summary

```
프로젝트별 진행률 요약 (앱 사업부 화면용).
    데이터 없는 모델은 제외하고 계산하며, progress=None 이면 '-' 로 표시할 것.
    division_id 를 주면 그 사업부 프로젝트만 + 가중 평균(weighted)을 함께 반환.

    부르는 곳: admin v2 — back.onclick() / 앱 — progress_service.dart fetch()
    
```

## def _display_project_label

```
프로젝트 표시 이름.

    PROJECT_LABELS 는 초창기 8개만 담고 있는 고정 맵이라
    이후에 추가된 프로젝트(플레이팅 셀 / 톨론 / EOS챔버 / 페러데이 4T /
    CURIE)는 'plating_cell' 같은 키가 그대로 화면에 노출됐다.
    운영 설정(config/projects.json)의 라벨을 먼저 본다.

    쓰는 곳: _calendar_events · _ds_plan · _issue_answer · _month_shipment_answer 외 11곳
    
```

## def get_overview

```
앱 홈 화면용 요약 (admin/overview 와 동일).

    부르는 곳: admin v2 — renderHomeDashboard() / 앱 — overview_service.dart fetch()
    
```

## def _split_weeks_closed_open

```
주차를 '끝난 주' 와 '남은 주' 로 가른다.

    월 달성률만 보면 9월 초에는 늘 20~30% 다. 아직 안 온 주차의 계획이
    분모에 들어가 있어서다. 끝난 주만 놓고 보면 계획을 지켰는지가 보이고,
    남은 주를 따로 보면 앞으로 얼마가 남았는지가 보인다.

    끝난 주 = 그 ISO 주의 일요일이 오늘보다 앞선 주.

    쓰는 곳: get_admin_overview
    
```

## def get_admin_overview

```
Admin 홈 대시보드용 요약: 프로젝트별 진행률 + 해당 월 수량/매출.

    부르는 곳: admin v2 — renderHomeDashboard() / 앱 — 없음
    
```

## def _parse_any_date

```
'2026-08-13', '2026/08/13', '26-08-13', '8/13' 같은 값을 date 로.

    쓰는 곳: _alert_why · _model_alert · _model_progress_asof · _set_fair_dates 외 1곳
    
```

## def _week_end_date

```
'2026-08' + 'W33' → 그 ISO 주의 일요일(주 마감일).

    연말·연초는 달의 연도와 ISO 연도가 어긋난다. 2025년 12월 보드의
    마지막 열은 'W01' 인데 그건 2026년 1주다. 달의 연도를 그대로 쓰면
    2025-01-05 가 나오고, 12월 한 달 내내 '이미 끝난 주' 로 잡혀서
    시작도 안 한 주가 통째로 미달로 올라온다. _week_ord 와 같은 규칙으로
    연도를 보정한다.

    쓰는 곳: _closed_week_labels · _model_progress_asof · _split_weeks_closed_open
    
```

## def _model_progress_asof

```
cutoff(date) 시점 기준 모델 진행률. 데이터 없으면 None.

    쓰는 곳: get_progress_trend
    
```

## def get_progress_trend

```
진행률 추이. 주차별 실적(양산) / 공정 실적일(개발) 누적으로 과거 시점을 재구성한다.
    period: day(최근 7일) | week(최근 N주) | month(최근 N개월)

    부르는 곳: admin v2 — 없음 / 앱 — progress_service.dart fetch()
    
```

## def _model_hold

```
'드롭예정' · '보류' · ''.

    파워박스 VCTR-XPRSMS 는 비고에 '드롭 예정' 이라고 적혀 있었는데
    앱이 비고를 안 읽어서, 자재 입고 예정일만 지나 보이고 그냥 지연으로
    잡혔다. 적어둔 말이 화면까지 이어지게 한다.

    쓰는 곳: _calendar_events · _div_counts · _enrich_model · _issue_answer 외 1곳
    
```

## def _project_hold

```
프로젝트 전체가 멈춰 있으면 '보류' · '드롭예정', 아니면 ''.

    CUP 은 현황에 '*컵 이슈 해결될 때까지 개발 컵 또한 LAIR 작성 홀딩'
    이라고 적혀 있는데도 모델 15종이 전부 '지연' 으로 세어졌다.
    멈춰 세운 일정을 늦었다고 하면 숫자가 거짓말을 한다.

    쓰는 곳: _calendar_events · _issue_answer · admin_plan_form · get_home_alerts 외 2곳
    
```

## def _hold_from_note

```
현황 문구에서 읽어낸 (종류, 근거 문장). 없으면 ('', '').

    쓰는 곳: _project_hold · _project_hold_reason · _stamp_project_hold
          · admin_plan_file_apply 외 1곳
    
```

## def _stamp_project_hold

```
현황에 적힌 보류를 프로젝트 필드로 새겨 둔다.

    문구는 주간보고를 다시 올리거나 현황을 고치다 사라질 수 있다.
    그때 보류가 조용히 풀리면 멈춰 세운 일정이 다시 지연으로 세어진다.
    한 번 읽어낸 보류는 필드로 남기고, 풀 때는 현황에 '홀딩 해제' 라고
    적거나 admin 에서 상태를 '진행' 으로 바꾸면 된다.

    쓰는 곳: _stamp_holds_once · put_project_status_note
    
```

## def _project_hold_reason

```
보류라고 판단한 근거 문장 한 줄. 화면에 그대로 보여준다.

    쓰는 곳: _issue_answer · get_project_models_detail · get_project_status_note
    
```

## def _dev_final_day

```
최종 승인이 끝난 날 (date) — 모르면 None.

    실적 칸의 날짜가 먼저다. 날짜 없이 '완료' 만 적혀 오면, 개발 일정
    양식을 올리다 처음 끝난 것을 본 날(final_done_seen)을 쓴다.

    쓰는 곳: _dev_po_wait
    
```

## def _dev_po_wait

```
최종 승인이 끝난 개발품을 PO 대기로 넘길 때가 됐나 (2026-11-05).

    Min: "최종 승인 완료 되면 1주일동안 두고 PO 대기로 넘어가게끔 하고
         만약에 1주일 전에 양산에 파트넘버가 올라오는거면 그냥 바로
         넘어가게끔 해주면 돼"

        최종 승인 끝  ─ 7일 동안 ─→  '완료' 로 보인다 (개발)
                       7일 지나면 →  PO 대기
        그 사이 품목정보 양식에서 양산으로 올라오면 → 그날 바로 양산
        (구분이 양산이 되므로 _model_po_wait 가 맡는다)

    끝난 날을 모르면(예전 자료) 기다릴 근거가 없으니 바로 PO 대기다.

    쓰는 곳: _enrich_model
    
```

## def _model_po_wait

```
양산으로 넘어왔는데 PO 가 아직 안 들어온 모델.

    최종 승인까지 끝내고 PO 접수를 기다리는 자리다. 진행률로 보면
    0% 라 늦은 것처럼 보이지만 우리가 늦은 게 아니다.

    쓰는 곳: _enrich_model
    
```

## def _issue_says_delay

```
이슈 칸에 사람이 '지연' 이라고 적었으면 일정 문제로 본다.

    양산품은 개발품과 달리 공정 완료예정일이 없어서, 늦었는지 따질
    근거가 손으로 적는 status 밖에 없다. 그래서 메이저모듈 EFEM 은
    '2대 고객 사급자재 지연 (ETA: 9/20)' 이라고 적혀 있는데도 화면에는
    특이사항으로만 떴다. 사람이 이미 판단해서 적어 둔 것을 안 읽을
    이유가 없다.

    쓰는 곳: _alert_why · _model_alert
    
```

## def _model_alert

```
'지연' · '주의' · '정상'.

    카드의 지연/주의 개수와 목록 줄의 '지연중 · 06 BV2' 가 서로 다른 값을
    보고 있었다. 카드는 손으로 적는 status 만 보고, 줄은 완료예정일로 따졌다.
    그래서 목록에는 지연이 다섯인데 카드는 0 이었다.

    여기서 한 번만 정하고 양쪽이 이걸 쓴다.
      - 손으로 '지연'/'주의' 를 적어뒀으면 그게 우선
      - 개발: 완료예정일이 지났으면 지연, SOON_DAYS 이내면 주의
      - 진행률 100% 면 정상

    쓰는 곳: _admin_model_alerts · _div_counts · _enrich_model · _issue_answer
    
```

## def _frame_group

```
앱이 이 모델을 **어느 틀로 그릴까** (2026-10-28).

    Min: "아리스타 같은 경우에는 그냥 양산이랑 동일하게 틀 적용해주면 될 것 같아"

    개발 품목은 반도체 기준으로 공정 13단계 화면을 쓴다 — PO 접수부터
    FAIR 승인까지. 아리스타는 PCB 라 그 단계가 아예 없어서, 개발 품목에
    들어가면 빈 단계표만 떴고 진행률도 '—' 였다.

    구분(display_group)과 틀(frame)은 다른 이야기다.
      구분 — 목록이 양산 · 개발 두 묶음으로 나뉘는 기준
      틀   — 그 묶음에 들어갔을 때 어떤 카드 · 어떤 상세 화면으로 보나

    Min: "양산 개발을 나뉘는데 개발에 들어가더라도 양산처럼 틀 똑같이
         맞춰달라는거였어"

    그래서 여기는 **틀만** 정한다. 아리스타 개발은 '개발' 묶음에 그대로
    있고, 안에서만 양산처럼 주차별 계획 · 실적으로 본다.
    저장된 구분(group)은 당연히 안 건드린다 — admin 표도 엑셀도 그대로다.

    쓰는 곳: _enrich_model
    
```

## def _enrich_model

```
모델 하나를 화면에 내보낼 모양으로 — 상태 · 지연 판정 · 공정 · 보류 를 붙인다. 홈·목록·상세가 다 이 판정을 쓴다.

    쓰는 곳: _calendar_events · get_home_alerts · get_project_models_detail
    
```

## def _has_week_plan

```
이 달에 주차 계획이 한 칸이라도 적혀 있나 (2026-11-02).

    홈 '전체 현황' 이 전 사업부로 넓어지면서 통째로 못 불러오게 됐다
    (Min: "지금 현황 retrieve 못 하고 있는 것 같아"). 재어 보니
    사업부 하나에 7~70초였다 —

        반도체  7s · 자동차 45s · 블룸 44s · PCB 69s   → 전사는 150초 넘게

    범인은 '주차 미달' 을 세는 자리였다. 프로젝트마다 주차 보드를 한 장씩
    통째로 만들어 보고 미달 한 줄만 꺼내 썼다. 프로젝트가 200개가 되니
    보드를 200장 만들고 있었다.

    이 달 주차 계획이 아예 없는 프로젝트는 미달이 나올 수가 없다.
    보드를 만들기 전에 그것부터 본다 — 사전 검사는 메모리만 훑는다.

    쓰는 곳: get_home_alerts
    
```

## def _weekly_shortfall_cached

```
그 달 **마지막 마감 주차의 미달 한 줄**만 캐시해 둔다.

    홈 화면은 앱이 열릴 때마다 부르고, 주차 보드 한 장을 만드는 건
    비싸다. 그래서 캐시를 뒀는데 — 처음에는 **보드를 통째로** 들고
    있었다. 보드 한 장이 수십~수백 KB 라 프로젝트 200곳이면 금방
    100MB 가 넘는다. 그게 메모리 부족으로 서버가 죽은 원인 중 하나다
    (2026-11-03, anon-rss 408MB 에서 OOM).
    (Min: "flutter 도 그렇고 admin v2도 그렇고 연결 하는데 왜이렇게
     오래 걸리는거야")
    돌려받아 쓰는 건 미달 한 줄과 마감주차뿐이라, 그것만 들고 있는다.

    models.json 이 바뀐 시각이 열쇠다 — 엑셀이 올라오면 저절로 버려진다.

    쓰는 곳: get_home_alerts
    
```

## def get_home_alerts

```
홈 화면 한 눈 요약 — 모델 기준.

    예전 홈은 /dashboard 의 주간보고 카드(RED/YELLOW)로 사업부 상태를 셌다.
    주간보고가 없는 사업부는 아예 집계에서 빠져서 '12개 중 정상 2' 처럼
    나왔고, 프로젝트 안에는 지연이 널려 있는데 홈은 '지연 0' 이었다.
    여기서는 프로젝트 안에서 보는 값과 똑같은 모델 alert 를 그대로 센다.

    세는 범위는 반도체사업부다. 카드에도 '(반도체 기준)' 이라고 적혀 있는데
    실제로는 전 사업부를 세고 있었다 — 적힌 것과 세는 것이 다르면 숫자를
    믿을 수 없다. division= 로 다른 사업부를, 빈 값으로 전사를 볼 수 있다.

    부르는 곳: admin v2 — 없음 / 앱 — home_alerts_service.dart fetch()
    
```

## def _cal_date

```
'2026-11-07' · '2026.11.7' · '2026/11/07' → date. 날짜가 아니면 None.

    단계 칸에는 '진행 중' · 'Lam측 날짜지정' 같은 글자도 들어 있다
    (dev_schedule_import 가 일부러 남긴다). 그건 달력에 올릴 날짜가 아니다.

    쓰는 곳: _calendar_events
    
```

## def _cal_week_monday

```
weekly_plan['2026-11']['W46'] → 그 주 월요일.

    자리는 달(YYYY-MM) 밑에 있지만 W 번호는 ISO 주차다. 12월 밑의 W01 은
    다음 해, 1월 밑의 W52·W53 은 앞 해 주차다.

    쓰는 곳: _calendar_events
    
```

## def _cal_category

```
단계 이름 → 캘린더 분류. 앱 필터(출하·입고·보고·승인·마일스톤)와 같은 말.

    쓰는 곳: _calendar_events
    
```

## def _calendar_events

```
운영 자료 → (날짜 있는 일정, 날짜 없는 지연·임박). 같은 자료면 다시 쓴다.

    쓰는 곳: get_calendar_events
    
```

## def get_calendar_events

```
캘린더 일정. start · end(YYYY-MM-DD)로 자르고 division 으로 거른다.

    아무것도 안 주면 전부 준다 — 많아야 천 줄 남짓이고, 앱은 달을 넘길 때마다
    다시 부르지 않고 한 번 받아 둔 것에서 고른다.

    부르는 곳: admin v2 — 없음 / 앱 — calendar_service.dart fetch()
    
```

## def _model_mix_note

```
프로젝트 현황 한 줄 — 사람이 적던 글 대신 숫자로 (2026-10-28).

    Min: "프로젝트 현황 모든 프로젝트에 다 빼주고 flutter app에 프로젝트
         현황에 작성되어 있던 내용을 알아서 반영되게 할거야 ...
         총 00종 중 양산 00종, 개발 00종"

    현황 글은 사람이 손으로 적는 칸이었다. 그런데 모델이 늘고 줄 때마다
    같이 고쳐 주는 사람이 없어서, 앱에는 몇 달 전 문장이 그대로 떠 있었다.
    숫자는 모델 목록에 이미 있다 — 그걸 세서 쓰면 늘 맞는다.

    구분은 저장된 group 이 아니라 _display_group 으로 센다. '개발→양산
    W37' 이력이 있으면 오늘 기준으로 양산이다 — 화면의 구분 칸과 같은
    기준이어야 표와 한 줄이 안 어긋난다.

    쓰는 곳: get_project_models_detail
    
```

## def get_project_models_detail

```
앱용 확장 모델 목록: dev_type, 자동 진행률, 현황(현재 단계), 완료예정일, status_note 포함

    부르는 곳: admin v2 — _devProgRender()
           · loadStatusNote() / 앱 — project_overview_screen.dart _loadBloom()
    
```

## def get_model_weekly_plan_q

```
모델 하나의 주차별 계획·실적 (모델 id 를 ?model_id= 로).

    부르는 곳: admin v2 — _wpLoadOne() · _sbEl.onclick() · loadModelWeeklyData() / 앱 — 없음
    
```

## def put_model_weekly_plan_q

```
모델 하나의 주차별 계획·실적 고치기 (잠김).

    부르는 곳: admin v2 — _sbEl.onclick() / 앱 — 없음
    
```

## def get_model_process_q

```
모델 하나의 개발 공정 (앱).

    부르는 곳: admin v2 — openProcessEditor()
           · renderProcessEditor() / 앱 — dev_process_screen.dart initState()
    
```

## def admin_get_model_process_q

```
모델 하나의 개발 공정 (admin).

    부르는 곳: admin v2 — openProcessEditor() · renderProcessEditor() / 앱 — 없음
    
```

## def admin_put_model_process_q

```
모델 하나의 개발 공정 고치기 (잠김).

    부르는 곳: admin v2 — openProcessEditor() · renderProcessEditor() / 앱 — 없음
    
```

## def admin_set_process_step_status_q

```
공정 한 단계 상태 바꾸기 (잠김).

    부르는 곳: admin v2 — renderProcessEditor() / 앱 — 없음
    
```

## def get_model_weekly_plan

```
양산 모델 월별 주차별 계획/실적 조회

    부르는 곳: get_model_weekly_plan_q (admin v2 의 ?model_id= 길) / 앱 — 없음
    
```

## def _norm_group

```
구분 글자 → '양산' 또는 '개발'.

    쓰는 곳: _all_actual_sum · _board_row_models · _board_row_status
          · _dev_models_have_weeks 외 6곳
    
```

## def _group_bucket

```
프로젝트의 주차 요약(weekly_summary)에서 양산/개발 묶음.

    쓰는 곳: _all_actual_sum · _dev_week_totals · get_group_summary
          · get_group_weekly_plan 외 1곳
    
```

## def _mass_week_totals

```
양산 주차 합계는 모델별 weekly_plan 이 정본.

    쓰는 곳: get_weekly_board
    
```

## def _dev_models_have_weeks

```
그 달에 '개발' 모델이 주차 숫자를 들고 있나.

    2026-10-27 — 양식에 '구분' 칸이 생기기 전에는 개발을 모델별로 가릴
    수가 없어서, 하바플레이트는 개발을 **그룹 총계 한 줄**로 손으로
    넣었다. 이제는 양식이 모델마다 양산/개발을 적어 오고 주차 계획도
    모델별로 들어온다.

    그런데 보드는 여전히 그룹 총계를 먼저 봤다. 그래서 양식으로 들어온
    숫자가 화면에 안 떴다 — 하바플레이트 10월 W43 이 모델별로는 84/74
    인데 보드에는 50/0 으로 떴다. 실적 74가 통째로 안 보인 것이다.

    그래서 **모델이 들고 있으면 모델이 정본**으로 바꾼다. 개발을 여전히
    그룹으로만 넣는 프로젝트는 모델에 숫자가 없으니 예전 그대로 돈다.

    쓰는 곳: _all_actual_sum · _dev_week_totals
    
```

## def _dev_week_totals

```
개발 주차 합계.

    모델이 그 달 주차를 들고 있으면 모델별 합이 정본이고, 없으면
    손으로 넣은 그룹 총계를 쓴다 (_dev_models_have_weeks 참고).

    쓰는 곳: get_weekly_board
    
```

## def _model_qty_sums

```
모델 목록에 직접 적은 PO 수량 / 실적 수량의 그룹 합계.

    쓰는 곳: get_weekly_board
    
```

## def _all_actual_sum

```
전 기간 주차 실적 합. 누적 실적 = base_actual + 이 값.

    쓰는 곳: get_weekly_board
    
```

## def get_group_weekly_plan

```
그룹(개발) 주차 합계 조회. 모델별 조회와 같은 모양이라 화면을 그대로 재사용한다.

    부르는 곳: admin v2 — loadModelWeeklyData() · _sbEl.onclick() / 앱 — 없음
    
```

## def put_group_weekly_plan

```
그룹(개발) 주차 합계 저장.

    부르는 곳: admin v2 — _sbEl.onclick() / 앱 — 없음
    
```

## def get_group_summary

```
PO 수량 / 기초 누적 실적 / 종수 / 다음달 계획 (그룹별).

    부르는 곳: admin v2 — openBoardEditor() · onclick() / 앱 — 없음
    
```

## def put_group_summary

```
PO 수량 등 저장. PO 수량이 바뀌면 증감 이력을 자동으로 남긴다.

    부르는 곳: admin v2 — onclick() / 앱 — 없음
    
```

## def _enrich_from_status

```
현황 표(1번 섹션)에서 PO증감 이력·진행중/완료 종수·그룹 누적 출하를 채운다.

    쓰는 곳: admin_models_import
    
```

## def admin_import_status_excel

```
하바플레이트 주간 현황 엑셀(W6~W35 시트)을 읽어 PO 수량·출하수량을 맞춘다.

    - 섹션 2~5 (모델별 표)  → 모델의 판가·PO 수량·출하수량·개발종류
    - 섹션 1 (현황)         → 그룹 PO 수량·누적 출하·진행중/완료 종수
    - 각 시트의 '변동' 열   → PO증감 이력 (주차별)
    기존 모델은 그대로 두고, 엑셀에만 있는 모델은 새로 만든다.

    부르는 곳: admin v2 — _pfStatusImport() / 앱 — 없음
    
```

## def _load_board_spec

```
config/boards.json 의 행 구성. 없으면 None → 예전 양산/개발 2줄 방식.

    쓰는 곳: _board_group_rows · _week_shipment_answer · chat · get_board_rows 외 1곳
    
```

## def _spec_claimed_models

```
보드 안에서 이미 품번으로 지목된 모델들.

    유형·구분으로 쓸어담는 행(Dep 챔버 15종, 양산19종 …)은 자기 조건에만
    맞으면 다 가져가므로, 다른 행이 품번으로 콕 집어둔 모델까지 같이 가져가
    두 행에 겹쳐 잡히고 PO·실적이 두 번 세어진다. 챔버에서 205(개발, 자기 행이
    있음)의 dev_type 이 DEP챔버 라서 Dep 행에도 들어가 '15종'인데 16개가
    잡히던 게 그 경우다.

    그래서 품번으로 지목된 모델은 쓸어담기 행에서 자동으로 뺀다.
    (boards.json 에 손으로 적어둔 exclude 는 그대로 둬도 결과가 같다.)

    쓰는 곳: _spec_board
    
```

## def _board_row_models

```
행이 가리키는 모델 목록.

    models    품번 지정
    dev_type  그 유형 전체
    exclude   유형으로 묶되 그중 뺄 품번 (009 직납 = 009 유형 − 자빌)
    claimed   다른 행이 품번으로 지목한 모델 (쓸어담기 행에서 자동 제외)

    쓰는 곳: _spec_board
    
```

## def _row_actual_after

```
기준 주차 '다음' 주차부터의 실적 합.

    담당자는 '지금 37주차니까 36주차까지의 누적'을 기준 실적으로 적는다.
    그 뒤로 나가는 실적은 주차 계획에 입력되므로 여기서 더한다.
    기준 주차를 안 적었으면 주차 실적을 더하지 않는다(누적값만 씀).

    쓰는 곳: _spec_board
    
```

## def _board_week_qty

```
그 달 주차별 계획/실적 합계.

    쓰는 곳: _spec_board
    
```

## def _board_row_status

```
'현황' 칸.

    보드에서 직접 넣은 값 > boards.json 에 적힌 값 > 모델로 자동 판정 순.
    자동만으로는 틀리는 경우가 있다. 205 는 FAIR 승인이 끝나 진행률이 100%
    라서 자동으로는 '완료'가 되지만 실제로는 아직 개발 건이고, 내재화처럼
    모델이 아직 등록 안 된 행은 근거가 없어 빈칸이 된다.

    쓰는 곳: _spec_board
    
```

## def _note_groups

```
행에 묶인 모델들의 메모를 같은 문구끼리 묶는다.

    [(문구, 종수)] 를 많은 순으로 돌려준다. 줄바꿈은 한 칸 띄어쓰기로 편다.

    쓰는 곳: _board_row_note
    
```

## def _note_rollup_text

```
AI 없이 묶는 기본형: '카이저 원소재 11월말 입고 예정 10종 · 1EA 황삭 완료 1종'.

    쓰는 곳: _ai_board_note · _board_row_note
    
```

## def _note_total_ok

```
요약문의 'N종' 합이 실제 종수와 같은지.

    AI 가 종수를 지어내면 보드 숫자와 어긋나므로, 안 맞으면 요약을 버린다.

    쓰는 곳: _ai_board_note
    
```

## def _ai_board_note

```
묶음 행(Dep 챔버 15종 등)의 메모를 상태별 종수로 요약한다.

    모델이 열몇 개씩 묶인 행은 메모를 그대로 이으면 읽을 수가 없다.
    '원소재 입고 대기 10종 · 조립 완료 3종' 처럼 상태별로 접어서 보여준다.
    같은 입력이면 캐시를 쓰고, 키가 없거나 실패하면 _note_rollup_text 로 떨어진다.

    쓰는 곳: _spec_board
    
```

## def _board_row_note

```
'비고' 칸.

    보드에서 직접 넣은 값 > boards.json 에 적힌 값 > 모델에 적어둔 메모 순.
    모델 목록의 '그 외 특이사항 · 메모'(m['note'])를 적어놓고 보드에는 안 뜬다는
    얘기가 나와서 마지막 단계를 붙였다. '문제 · 리스크'(m['issues'])는 따로
    이슈 화면에서 쓰는 값이라 여기로 끌어오지 않는다.

    메모가 붙은 모델이 _NOTE_ROLLUP_MIN 개 이상인 묶음 행은 그대로 이으면
    읽을 수가 없어서 상태별 종수로 접는다(summarize, 보통 _ai_board_note).
    그보다 적으면 지금처럼 나열하고, 모델이 여럿이면 모델명을 앞에 붙인다.

    쓰는 곳: _spec_board
    
```

## def _board_month_qty

```
그 달 계획/실적 합계. 모델별 weekly_plan 을 월 소유 규칙대로 더한다.

    쓰는 곳: _spec_board
    
```

## def _board_months

```
오늘 달을 마지막으로 하는 월 목록. span=2 → ['2026-08','2026-09'].

    쓰는 곳: _spec_board
    
```

## def _has

```
직접 입력 칸이 '채워져 있는가'. 0 은 유효한 값이므로 None/빈문자만 비었다고 본다.

    쓰는 곳: _apply_price_change · _pick_manual · _spec_board · put_board_rows
    
```

## def _spec_section_rows

```
섹션의 행 목록.

    rows_from: "models" 면 등록된 모델 하나가 행 하나가 된다. 큐리처럼
    엑셀이 '모델명 x 주차' 한 장으로 오는 곳은 행을 설정에 미리 적어둘 수가
    없다 — 모델이 늘면 보드도 같이 늘어야 한다.

    보이는 순서는 모델 목록 순서 그대로. 담당자가 엑셀에 적은 순서다.

    쓰는 곳: _spec_board
    
```

## def _pick_manual

```
사람이 직접 적은 값이 있으면 그것, 없으면 계산한 값.

    보드의 거의 모든 칸이 이 규칙을 따른다. 직접 적은 값이 '0' 일 수도
    있어서 `store.get(field) or calculated` 로 쓰면 안 된다 — 0을 '안
    적었다'로 읽어 계산값으로 덮어써 버린다. 그래서 _has 로 '칸이
    있는가'를 따로 본다.

    쓰는 곳: _spec_board
    
```

## def _sum_pair

```
여러 줄의 {bucket}[{key}] 안에 있는 계획·실적을 각각 더한다.

    예) _sum_pair(rows, "weeks", "W41")
        → {'plan': 모든 줄의 W41 계획 합, 'actual': 실적 합}

    쓰는 곳: _spec_board
    
```

## def _spec_board

```
boards.json 스펙대로 그린 보드 (섹션 + 행).

    쓰는 곳: get_weekly_board
    
```

## def admin_put_week_reason

```
주차 미달 사유를 적는다.

    body: {month, week, kind: '문제'|'참고', text}
    text 가 비면 그 주의 사유를 지운다 (미입력으로 되돌린다).

    2026-10-22 — 막혀 있다. 같은 자리를 엑셀의 '미달 사유' 줄도 쓴다.
    두 군데서 적으면 올릴 때마다 서로 덮어쓴다. 엑셀 하나로 모았다.

    부르는 곳: admin v2 — saveWeekReason() / 앱 — 없음
    
```

## def get_board_rows

```
보드 행별 직접 입력값 (PO수량·실적·월·비고).

    부르는 곳: admin v2 — _wbOpenRowEditor() · onclick() / 앱 — 없음
    
```

## def put_board_rows

```
보드 행별 직접 입력값 저장.

    빈 문자열로 보내면 그 칸은 '직접 입력 없음'이 되어 모델 합계로 돌아간다.
    (0 은 유효한 값이라 지우기와 구분해야 한다)

    부르는 곳: admin v2 — onclick() / 앱 — 없음
    
```

## def _bloom_pick

```
새 값이 비어 있으면 옛 값을 지킨다. 0 은 유효한 값이다.

    쓰는 곳: _bloom_fold_steps · _bloom_merge
    
```

## def _bloom_last_day

```
품목·공정에서 숫자가 적힌 마지막 날 — 둘 중 어느 쪽이 새 것인지 가른다.

    쓰는 곳: _bloom_fold · _bloom_fold_steps
    
```

## def _bloom_fold_steps

```
같은 공정이 이름만 달리 두 번 있으면 (NCT(박장) / NCT(박닌)) 하나로.
    옛 것 위에 새 것을 덮는다 — 날짜 칸은 합치고, 나머지는 새 값이 있으면 새 값.

    쓰는 곳: _bloom_fold · _bloom_merge
    
```

## def _bloom_fold

```
'Corva KPE' 와 'Corva KPE (117품목)' 처럼 이름만 다른 같은 품목을 하나로.

    쓰는 곳: _bloom_merge · _cleanup_bloom_dupes
    
```

## def _bloom_merge

```
(합쳐진 보드, 무엇이 바뀌는지).

    쓰는 곳: _bloom_apply_months · _bloom_fold
    
```

## def _bloom_with_month_totals

```
'월 합계' 가 비어 있으면 날짜 칸을 더해서 채운 사본.

    파일마다 '9월 합계' 열이 있기도 하고 없기도 하다. 없는 달은
    month_plan / month_actual 이 통째로 None 이라, 날짜별 계획·실적이
    21일치 들어 있어도 월간 보기가 텅 빈 채로 보였다.

    저장된 값은 건드리지 않는다 — 엑셀에 없는 숫자를 보드에 적어 두면
    다음에 진짜 합계가 올라올 때 무엇이 사람이 적은 값인지 알 수 없다.
    화면에 내보낼 때만 더해서 채운다.

    쓰는 곳: _daily_prev_by_group · _daily_project_board · get_daily_board
    
```

## def _bloom_summary

```
그 날 공정별 계획/실적 합계 + 직전에 실적이 있던 날.

    실적 칸이 비어 있는 것과 0 은 다르다. 계획은 있는데 실적이 하나도
    안 적혔으면 pending=True — 오전에 화면이 0% 로 보이면 안 된다.

    쓰는 곳: _bloom_chat_answer · get_daily_board · get_home_alerts
    
```

## def _bloom_item_of

```
그 프로젝트가 맡은 품목 이름. 품목 프로젝트가 아니면 빈 문자열.

    쓰는 곳: _bloom_board_for · _daily_board_items · _daily_project_board
          · _daily_ship_weeks 외 3곳
    
```

## def _bloom_slice

```
품목 하나만 남긴 보드. 날짜·요약도 그 품목 기준으로 다시 낸다.

    쓰는 곳: _bloom_board_for · _daily_ship_weeks · get_daily_board
    
```

## def _bloom_board_for

```
블룸 프로젝트 하나가 볼 보드 (품목 프로젝트면 자기 몫만).

    쓰는 곳: _bloom_chat_answer · admin_bloom_template · get_home_alerts
    
```

## def _bloom_item_totals

```
그 날 품목별 계획/실적 합계.

    쓰는 곳: _bloom_chat_answer
    
```

## def _bloom_chat_answer

```
블룸 질문 즉답. 모델이 없는 프로젝트라 일 보고 보드를 직접 읽는다.

    챗봇은 경영진이 쓴다. 숫자 한 줄 + 막힌 곳 한 줄이면 충분하다.

    쓰는 곳: chat
    
```

## def get_daily_board

```
블룸 일 보드. Admin 도 앱도 이걸 읽는다.

    month  'YYYY-MM'. 없으면 가장 최근 달. 10월이 되어도 9월 계획 대비
           실적을 볼 수 있어야 해서 달을 고를 수 있게 뒀다.

    부르는 곳: admin v2 — renderDailyBoard() / 앱 — bloom_service.dart board()
    
```

## def _bloom_month_of

```
그 보드가 어느 달 것인가. **날짜**가 기준이다 — 제목은 못 믿는다.

    9월 시트의 제목도 '블룸 계획 대비 실적 보고(10/01)' 이라 적혀 있다.
    마지막으로 손댄 날이 제목에 남은 것이라, 제목으로 달을 잡으면 9월
    자료가 10월 자리로 들어간다.

    쓰는 곳: _bloom_parse_months · _bloom_store_months
    
```

## def _bloom_store_months

```
{'2026-09': 보드, '2026-10': 보드} — 지난 달 + 이번 달.

    이번 달은 daily_board 에 그대로 있다. 그걸 읽는 곳이 여럿이라
    (챗봇·매출 집계·RAG) 자리를 안 옮긴다. 지난 달만 따로 쌓는다.

    쓰는 곳: _bloom_apply_months · _daily_prev_by_group · _daily_project_board
          · _daily_ship_weeks 외 2곳
    
```

## def _bloom_parse_months

```
파일에 든 달 전부. {'2026-09': parsed, ...}

    금액 실적 시트는 파일에 한 장뿐이라 **가장 늦은 달**에만 붙인다.

    쓰는 곳: admin_bloom_daily_apply · admin_bloom_daily_preview · admin_division_daily_apply
          · admin_division_daily_preview
    
```

## def _bloom_apply_months

```
달별로 합친다 → ({'2026-09': 보드}, {'2026-09': diff}, 최신달).

    저장은 안 한다 — 미리보기와 저장이 **같은 계산**을 쓰게 하려고
    여기서 끊었다. 미리보기에 보인 숫자와 저장되는 숫자가 다르면
    무엇을 보고 눌렀는지 알 수 없게 된다.

    쓰는 곳: admin_bloom_daily_apply · admin_bloom_daily_preview · admin_division_daily_apply
          · admin_division_daily_preview
    
```

## def _bloom_months_brief

```
화면에 '어느 달이 얼마나 바뀌는지' 한 줄씩.

    쓰는 곳: admin_bloom_daily_apply · admin_bloom_daily_preview · admin_division_daily_apply
          · admin_division_daily_preview
    
```

## def _bloom_parse_upload

```
블룸 일 보고 엑셀을 읽어 보드 자료로.

    쓰는 곳: main.py 안에서는 안 쓴다 (테스트 · 예전 코드)
    
```

## def _daily_store_key

```
그 사업부의 일 보고 자료가 어디에 담기는가. 없으면 빈 글자.

    쓰는 곳: _daily_div_money · _daily_need_store · _daily_prev_by_group
          · _daily_project_board 외 6곳
    
```

## def _daily_need_store

```
담을 자리가 없으면 여기서 끊는다.

    쓰는 곳: admin_division_daily_apply · admin_division_daily_preview
    
```

## def admin_division_daily_preview

```
올린 일 보고 자료가 무엇을 바꾸는지 먼저 보여준다. 저장하지 않는다.

    부르는 곳: admin v2 — _dailySend() / 앱 — 없음
    
```

## def admin_division_daily_apply

```
미리보기에서 확인한 내용을 저장한다.

    부르는 곳: admin v2 — _dailySend() / 앱 — 없음
    
```

## def get_division_daily_view

```
일 보고 자료를 **접어서** 내보낸다.

    한 달치를 날짜 그대로 주면 열이 31개라 화면이 못 그린다.
    지난 주차는 주 한 칸으로 합치고, 이번 주차만 날짜로 펼친다.
    접는 규칙은 daily_view.py 가 갖고 있다 — 화면마다 따로 접으면
    앱과 admin 이 다른 모양이 된다.

    부르는 곳: admin v2 — 없음 / 앱 — daily_board_card.dart _pickMonth()
    
```

## def admin_bloom_daily_preview

```
저장하지 않고 무엇이 바뀌는지만 보여준다.

    부르는 곳: admin v2 — fl.onchange() / 앱 — 없음
    
```

## def admin_bloom_daily_apply

```
합쳐서 저장한다.

    부르는 곳: admin v2 — _bdConfirm() / 앱 — 없음
    
```

## def _week_reasons_of

```
{'W37': {'kind': '참고', 'text': '...', 'at': '...'}}

    쓰는 곳: _daily_project_board · _spec_board · admin_plan_form · admin_put_week_reason 외 2곳
    
```

## def _closed_week_labels

```
마감된 주차 = 그 ISO 주의 일요일이 오늘보다 앞선 주.

    쓰는 곳: _mark_board_shortfalls
    
```

## def _mark_board_shortfalls

```
마감된 주차에서 합계가 계획에 못 미치면 표시를 달고 목록으로 돌려준다.

    미달은 '합계' 기준이다. 품목별로 따지지 않는다.
    하바플레이트 W37 이 그 경우다 — 양산이 19대 모자랐는데 개발이 그만큼
    더 나가서 합계(97 → 117)는 넘겼다. 행마다 빨갛게 칠하면 설명할 것도
    없는 주에 사유를 적으라고 조르게 된다.

    칸에 붙는 것
      closed  그 주가 끝났는지 (앱은 안 끝난 주의 실적을 '·' 로 그린다)
      short   합계가 모자란 수량 (계획 - 실적). 끝난 주의 합계 행에만.

    돌려주는 것은 (마감 주차 목록, 미달 목록). 미달은 주차당 한 건이다.

    쓰는 곳: _daily_project_board · _spec_board · get_weekly_board
    
```

## def _sum_of

```
여러 줄에서 같은 칸을 더한다.

    보드는 '칸마다 전부 더하기'가 반복된다. 더하는 자리를 한 군데로
    모아 두면, 더하는 규칙이 바뀔 때 한 곳만 고치면 된다.

    쓰는 곳: _spec_board · get_weekly_board
    
```

## def _only_these_weeks

```
주차 묶음에서 이번 달 주차만 남긴다.

    주차 합계에는 옆 달 주차가 섞여 들어올 수 있다. 표에 그릴 열은
    이번 달 것뿐이라 여기서 걸러 낸다.

    쓰는 곳: get_weekly_board
    
```

## def _bloom_step_weeks

```
# 블룸은 다른 사업부와 자료가 들어오는 모양이 다르다.
#
#   반도체·자동차 — 프로젝트 안에 모델(품번)이 있고, 모델마다 '양산/개발'
#                  이 붙는다. 그래서 보드의 '구분' 열이 양산 · 개발이다.
#   블룸         — 모델이 아예 없다. 프로젝트 하나가 품목 하나다
#                  (bloom_yfp = 품목 'YFP'). 대신 일 보고 자료에 품목마다
#                  **공정**이 적혀 온다 — YFP 면 NCT(박닌) · 조립(박닌) ·
#                  출하 세 줄이다.
#
# 그래서 블룸 프로젝트의 '구분' 열은 **공정**이다. 양산/개발로 그리면
# 두 줄 다 0 이 뜬다 — 데이터에 그런 구분이 없기 때문이다.
#
# 숫자가 오는 길
#   일 보고 자료(날짜별) → daily_board 에 저장 → 여기서 ISO 주차로 묶는다.
#   '40주차' 같은 보고 자료의 주차 표기와 같은 번호다 (daily_view 와 동일).
#
# 없는 열
#   PO수량 · 잔량 · 다음달 계획 · PO증감 은 일 보고 자료에 없는 숫자다.
#   0 으로 채우면 '0개 주문'처럼 읽히고, '-' 로 채우면 빈 열이 네 개 선다.
#   그래서 앱에 '이 열은 빼고 그려라'(hide_cols)를 같이 보낸다.
공정 한 줄의 날짜 자료를 주차 칸으로 묶는다 → {'W41': {plan, actual}}

    weeks 는 이번 달이 가진 주차 목록이다. 거기 없는 주차(옆 달 주차)에
    들어온 날짜는 버린다 — 이번 달 표에 옆 달 숫자가 섞이면 합계가 틀린다.

    쓰는 곳: _daily_board_rows
    
```

## def _daily_slice_by_project

```
품목 이름에 프로젝트 이름이 들어간 줄만 남긴다.

    일 보고 엑셀 한 장이 품목을 전부 싣고 와서 한 자리에 담긴다
    (bloom_main · ess_main). 프로젝트 화면은 거기서 제 몫만 잘라 본다.

    ── 못 고르면 빈 보드다 (2026-10-26)

    전에는 한 줄도 못 고르면 자르지 않고 **다 보여 줬다**. 그래서 양식으로
    생긴 'SM' 프로젝트에 들어가면 블룸 품목 여덟 개가 통째로 떴다 —
    일 보고에 'SM' 이라는 품목이 없어서 고르기에 실패한 것이었다.

    남의 자료를 보여 주느니 비워 둔다. 일 보고에 그 이름이 없으면
    그 프로젝트는 일 보고를 안 받는 것이다.

    쓰는 곳: _daily_ship_weeks · get_daily_board
    
```

## def _daily_board_division

```
그 프로젝트가 일 보고로 보드를 그리는 사업부인가. 아니면 빈 글자.

    쓰는 곳: _daily_div_money · _daily_project_board · _daily_ship_weeks · get_daily_board 외 1곳
    
```

## def _daily_step_group

```
그 공정이 어느 줄인가 ('NCT(박닌)' → 'NCT').

    쓰는 곳: _daily_board_rows · _daily_prev_by_group · _daily_report_rows · _daily_ship_weeks
    
```

## def _daily_report_rows

```
'구분' 열에 세울 공정 — 일 보고의 '공정구분' 칸에 적힌 그대로 (2026-10-26).

    전에는 _DAILY_BOARD_ROWS 에 박아 둔 세 줄을 늘 세웠다. 그러면 일 보고에
    '도장' 같은 공정이 새로 적혀 와도 맨 뒤에 덧붙고, 일 보고에서 빠진 공정은
    빈 줄로 남았다. 구분은 일 보고가 정한다 — 적힌 순서대로 세운다.

    한 프로젝트 몫이 아니라 **그 달 일 보고 전체**에서 뽑는다. 품목마다 뽑으면
    BOP Assy(NCT 없음)만 두 줄이 되어 옆 품목과 줄이 안 맞는다.
    자료가 없으면 박아 둔 줄로 간다.

    쓰는 곳: _daily_project_board
    
```

## def _daily_board_items

```
그 프로젝트가 맡은 품목 자료만 골라낸다.

    블룸은 품목 하나(bloom_item), ESS 는 일 보고의 '고객사' 칸이 프로젝트
    이름이라 그걸로 고른다.

    쓰는 곳: _daily_prev_by_group · _daily_project_board
    
```

## def _daily_stock_of

```
품목 단위로 쌓여 있는 재고 → {'wait_ship':.., 'wait_part':..}

    출하대기(만들어 놓고 못 나간 것)와 구매품 대기(부품이 안 와서 못 만드는
    것)는 **품목**에 붙는 숫자다. 공정마다 따로 적혀 오지 않는다. 그래서
    공정 줄에는 못 넣고, 프로젝트 전체 값으로 합계 줄에만 적는다.

    적힌 품목이 하나도 없으면 None — 0 으로 두면 '대기 없음' 으로 읽힌다.

    쓰는 곳: _daily_project_board
    
```

## def _daily_board_rows

```
품목들을 공정별로 더해 보드 행을 만든다.

    ESS 는 한 프로젝트가 품목을 여럿 맡는다 (플루언스 8종). 품목마다 줄을
    세우면 24줄이 되어 못 읽는다. 공정이 같으면 한 줄로 더한다.

    쓰는 곳: _daily_project_board
    
```

## def _daily_prev_by_group

```
지난달 그 프로젝트의 공정별 실적. 지난달 자료가 없으면 빈 묶음.

    쓰는 곳: _daily_project_board
    
```

## def _daily_project_board

```
일 보고로 그리는 프로젝트 보드. 해당 없으면 None (옛 방식으로 간다).

    돌려주는 모양은 반도체 보드와 같다 (앱이 같은 위젯으로 그린다).
    다른 것은 '구분' 열이 공정이라는 것과, 일 보고에 없는 열을 hide_cols
    로 빼 달라고 적어 보낸다는 것뿐이다.

    쓰는 곳: get_weekly_board
    
```

## def _weekly_filtered

```
주차별 계획에 세울 모델만 남긴 프로젝트 (설정이 없으면 그대로).

    조건은 division_columns.WEEKLY_ONLY 가 들고 있다. 한 줄도 안 남으면
    거르지 않은 원본을 돌려준다 — 조건이 바뀌었거나 아직 안 적은 것인데,
    빈 표를 띄우면 "자료가 사라졌다" 가 된다.

    쓰는 곳: main.py 안에서는 안 쓴다 (테스트 · 예전 코드)
    
```

## def _weekly_match

```
그 조건에 맞는 모델만.

    쓰는 곳: _weekly_filtered · _weekly_rule_live · get_division_weekly_board
    
```

## def _weekly_rule_live

```
그 사업부 어딘가에 조건에 맞는 줄이 하나라도 있나.

    쓰는 곳: _weekly_filtered · get_division_weekly_board
    
```

## def get_weekly_board

```
엑셀로 올리던 '주차별 계획 원본' 표를 데이터에서 계산해 돌려준다.

    열 구성: PO수량 / 누적실적 / 잔량 / 지난달 / 이번달 주차별(계획·실적) /
             이번달 합계 / 다음달 계획 / PO증감

    부르는 곳: admin v2 — renderWeeklyBoard() / 앱 — division_board_service.dart
           · weekly_board_card.dart _setMonth()
    
```

## def get_division_weekly_board

```
사업부 화면에 띄울 주차 현황 보드 (2026-10-26).

    프로젝트 화면 보드와 같은 표인데 '구분' 열이 **프로젝트 이름**이다.
    프로젝트마다 보드를 만들고 그 합계 줄을 한 줄로 접는다.

    세울 프로젝트는 사업부가 정한 조건(WEEKLY_ONLY)이 고른다. 아리스타는
    렉(랙)이 든 일곱 프로젝트뿐이다 — 전에는 앱이 프로젝트를 하나씩
    받아다 제가 골랐는데, 그러면 조건이 서버와 화면 두 곳에 생긴다.

    부르는 곳: admin v2 — 없음 / 앱 — division_board_service.dart
    
```

## def _month_of_week_key

```
주차 번호가 어느 달에 속하는지. 월별 주차 배정 규칙(_get_month_weeks)을 그대로 쓴다.

    쓰는 곳: _po_delta_summary · _project_manual_deltas
    
```

## def _delta_periods

```
PO증감 입력 칸. 지난 6개월은 월 단위, 이번 달은 주차 단위로 고정한다.

    10월이 되면 W36~W40 은 자동으로 '9월' 한 줄로 접히고
    W41, W42 … 가 새로 열린다. 사용자가 기간을 직접 만들 필요가 없다.

    쓰는 곳: get_group_summary
    
```

## def _project_manual_deltas

```
직접 입력한 PO증감. 예전에 그룹별로 저장된 값도 합쳐서 한 벌로 돌려준다.

    쓰는 곳: get_group_summary · get_weekly_board
    
```

## def _po_delta_summary

```
PO 증감 요약.

    지난 달까지는 월 단위, 이번 달은 주차 단위로 보여준다.
    (9월이면 '9월: N' 이 아니라 'W36: N / W37: N')
    엑셀에서 읽은 이력(history)과 직접 입력한 값(manual)을 합친다.

    쓰는 곳: get_weekly_board
    
```

## def put_weekly_plan

```
월별 주차별 계획/실적 저장

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _lead_by_position

```
자리로 맞춘 소요 → {단계 이름: (주, 보여 줄 글자)}.

    개월을 주로 바꿔 둔다 — 저장은 한 단위(주)로 모아야 파워박스 ·
    블룸 값과 같이 더할 수 있다. 보여 줄 때는 개월 그대로 적는다:
    '21개월' 을 '91주' 로 적어 놓으면 아무도 안 읽는다.

    쓰는 곳: get_process_steps
    
```

## def _canon_step

```
'04 CB' → 'CB'. 엑셀마다 번호를 붙이기도 하고 안 붙이기도 한다.

    쓰는 곳: _merge_process_keep · _project_steps · _set_fair_dates · _unify_cdr_prr 외 1곳
    
```

## def _unify_cdr_prr

```
바꾼 사본, 바꿀 게 없으면 None.

    쓰는 곳: _cleanup_cdr_prr · admin_import_unified
    
```

## def _project_steps

```
이 프로젝트가 실제로 쓰는 단계 이름. 모델마다 틀이 달라질 수 있어
    가장 많이 쓰이는 것을 고른다. 하나도 없으면 기본 13단계.

    쓰는 곳: get_process_steps
    
```

## def get_process_steps

```
앱 칩 줄 — 단계 이름 + 표준 소요(주).

    weeks 가 None 이면 아직 안 정한 것이라 칩에 아무것도 안 붙인다.

    부르는 곳: admin v2 — leadBtn.onclick() / 앱 — model_list_screen.dart _loadSteps()
    
```

## def admin_set_process_lead

```
단계별 표준 소요(주) 저장. 빈 값은 '안 정함' 으로 둔다.

    부르는 곳: admin v2 — onclick() / 앱 — 없음
    
```

## def get_model_process

```
앱용 개발 승인 프로세스 조회

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_get_model_process

```
admin v2 'Process 입력' 화면용 조회 (앱용과 같은 형식).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_set_process_step_status

```
공정 단계 하나의 상태만 바꾼다 (표의 상태 드롭다운).
    payload = {step_key, status}  status: '' | '대기' | '진행중' | '완료' | '미승인' | '미제출'
    '완료'로 바꿨는데 실적일이 비어 있으면 오늘 날짜를 채워 진행률에 반영되게 한다.

    부르는 곳: admin v2 — procInput.onchange() · _pfProcess() / 앱 — 없음
    
```

## def admin_put_model_process

```
admin v2 'Process 입력' 저장.
    payload = {dev_type, steps:[{key, expected, actual, status}, ...]}
    단계 이름·순서는 서버가 가진 것을 유지하고 입력값만 덮어쓴다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_price_import_xlsx

```
파워박스 판가/재료비 엑셀 업로드 (PBX/MajorModule/EMA 시트 자동 인식)

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _looks_auto_note

```
비고가 사람 글이 아니라 예전 업로드가 적어 둔 단계 나열인가.

    쓰는 곳: _cleanup_auto_notes · admin_import_unified
    
```

## def _step_date

```
날짜면 'YYYY-MM-DD', 아니면 빈칸. 날짜 칸에 글자를 넣지 않는다.

    쓰는 곳: _step_actual · admin_import_unified
    
```

## def _step_actual

```
실적 칸 → (실적일, 상태).

    쓰는 곳: admin_import_unified
    
```

## def admin_import_unified

```
통합 업로드: MajorModule/PBX/EMA 시트 자동 인식, 프로세스+가격 한번에

    관리자 확인이 빠져 있었다 — 로그인 없이 모델 데이터를 바꿀 수 있었다.
    다른 업로드 라우트와 같은 것을 건다.

    부르는 곳: admin v2 — procInput.onchange() · _pfProcess() / 앱 — 없음
    
```

## def admin_import_weekly_summary

```
하바플레이트 주차별 현황 엑셀 업로드 (양산/개발 총량 구조).
    행5=양산, 행6=개발 / F~M열 = W32~W35 계획·실적 / P열=다음달 계획

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_restore_process

```
백업 models.json 에서 개발 공정(process) 입력만 골라 현재 데이터에 되살린다.
    모델 ID 로 매칭하며, 계획일/실적일/상태가 하나라도 채워진 공정만 복구한다.
    다른 필드(판가·PO·주차 등)는 건드리지 않는다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_import_weekly_report

```
주간 보고 엑셀(W##.xlsx) 한 장으로 모델·판가·PO·출하·비고·주차별 계획을 한 번에 반영.

    - 시트: W 번호가 가장 큰 것을 자동 선택 (sheet 로 지정 가능)
    - 모델: 엑셀 기준으로 교체. 기존 공정(process)·이슈(issues)는 모델 ID 로 승계
    - 주차: 엑셀에 있는 월만 갱신하고, 엑셀에 없는 월의 기존 데이터는 보존
    - dry_run=true 면 저장하지 않고 변경 예정 내역만 돌려준다

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _is_rpm_model

```
엑셀에서 빠지면 지워도 되는 모델인지.

    RPM 개발품은 주 단위로 들고 나서 이력을 붙들 이유가 없다.
    반대로 양산(HVM)과 HVM 개발품은 엑셀에 안 보여도 절대 지우지 않는다
    (주차별 계획·개발 공정 이력이 같이 날아가기 때문).

    쓰는 곳: _apply_report_workbook
    
```

## def _apply_dev_status

```
개발현황 엑셀(dev_status_import)을 모델에 반영한다.

    하바플레이트 '260919_하바플레이트 개발현황.xlsx' 같은 파일.
    모델 등록 양식과 열 이름이 겹쳐서 일반 파서에 맡기면 'PO 잔량' 이
    'PO 수량' 을 덮고 개발품이 양산으로 들어간다 — 그래서 따로 읽는다.

      · 모델명(= 파트넘버) 으로 맞추고, 없으면 개발품으로 새로 만든다
      · '가공 완료' 날짜 → 개발 공정 '가공 (조립)' 단계 계획일
        (앱의 '완료예정' · 지연/집중관리 판정이 이 날짜로 돈다)
      · '고객요청일' 이 'PO 취소' 면 상태를 '드롭예정' 으로
      · 판가 · 개발종류 · PO 수량 · 출하수량 · 비고

    쓰는 곳: admin_models_import
    
```

## def _apply_report_workbook

```
주간 보고 엑셀 파싱 결과를 models.json 에 병합한다.
    엑셀을 정본으로 교체하되 기존 공정(process)/이슈(issues)는 ID 로 승계하고,
    엑셀에 없는 월의 주차 데이터는 그대로 둔다.

    쓰는 곳: admin_import_weekly_report · admin_models_import
    
```

## def _week_ord

```
('2026-08','W36') → 202636. 연말/연초 주차는 ISO 연도로 보정.

    쓰는 곳: _df_week_tag · _phase_row_at · _row_actual_after
    
```

## def _phase_ord

```
'2026-W36' → 202636. 못 읽으면 None.

    쓰는 곳: _display_group · _norm_phases · _phase_row_at · admin_models_import
    
```

## def _norm_phases

```
저장/조회용 정규화. from 오름차순, 잘못된 항목은 버린다.

    쓰는 곳: _apply_price_change · _df_apply_price · _display_group · _phase_row_at 외 2곳
    
```

## def _this_week_tag

```
오늘이 속한 주차를 구간 시작점 형식으로.

    쓰는 곳: _apply_price_change · admin_division_form_apply · admin_division_form_preview
    
```

## def _apply_price_change

```
판가·재료비가 바뀌었으면 구간으로 남긴다.

    mode 'from_now'  이번 주부터 새 구간. 지난 주차 매출은 그대로.
    mode 'retro'     지금 적용 중인 구간의 값을 덮는다 (입력 오류 정정).

    sent 은 화면이 실제로 보낸 원본 dict. 이게 중요한 이유: ESS 프로젝트는
    모델 표에 판가·재료비 칸 자체가 없어서 저장할 때 늘 0 을 보낸다. 보낸
    0 을 '판가를 0 으로 고쳤다' 로 읽으면, ESS 모델을 한 번 저장하는 것만으로
    판가 이력이 통째로 0 이 된다. 그래서 '칸이 있었던' 항목만 비교한다.

    바뀐 게 없으면 아무것도 안 한다. 반환은 화면에 보여줄 요약.

    쓰는 곳: admin_put_project_models
    
```

## def _phase_row_at

```
그 주차에 유효한 구간 {group, price, material_cost}.
    이력이 없으면 모델의 현재 값 (기존 동작 그대로).

    쓰는 곳: _phase_at · _phase_cost_at
    
```

## def _phase_cost_at

```
그 주차의 재료비.

    쓰는 곳: main.py 안에서는 안 쓴다 (테스트 · 예전 코드)
    
```

## def _phase_at

```
그 주차에 유효한 (구분, 판가). phases 가 없으면 모델의 현재 값.

    쓰는 곳: _all_actual_sum · _dev_week_totals · _mass_week_totals · get_weekly_revenue
    
```

## def _display_group

```
오늘 기준으로 '보이는' 구분.

    '개발→양산 W37' 이력이 있는데 이번 주가 W38 이면 구분 칸에 양산으로
    보여야 한다. 저장된 group 은 개발 그대로 둔다 — 진행률은 계속 공정
    단계로 세고, 지난 주차 매출도 그때 구분/판가로 남아야 한다.
    바뀌는 건 '지금 어느 단계인가' 하나뿐이다.

    ref 를 주면 그 날짜 기준. 과거 추이를 그릴 때는 '그때' 무엇이었는지를
    써야 한다 — 오늘 기준으로 세면 지난달 그래프가 통째로 바뀐다.

    쓰는 곳: _admin_model_alerts · _board_row_models · _div_counts · _enrich_model 외 8곳
    
```

## def _dev_weeks_from_models

```
개발 주차값을 '모델별 입력'에서 읽을지, '그룹 총계'에서 읽을지.

    모델별로 0 이 아닌 값이 하나라도 있으면 모델이 정본이다.

    weekly_summary['개발'] 은 하바플레이트처럼 개발을 그룹 총계로만 관리하는
    프로젝트를 위한 값이다. 예전에는 이게 있기만 하면 무조건 그쪽을 썼는데,
    파워박스처럼 개발도 모델별로 입력하는 프로젝트에서는 옛 주간보고에서 들어온
    0 짜리 그룹 총계가 모델 값을 통째로 덮었다. 853-043648-115 는 9월 W36 실적
    1대가 저장돼 있는데도 매출·수량 집계에서 0 으로 잡혀, 파워박스 9월 실적이
    52대 대신 51대로 나왔다.

    하바플레이트는 개발 모델 40종에 주차 칸만 있고 값은 전부 0 이라
    이 규칙에서도 그대로 그룹 총계를 쓴다.

    쓰는 곳: get_weekly_revenue
    
```

## def _daily_unit_price

```
#  블룸·ESS 는 모델에 주차별 계획이 없다. 양식은 품목 정보(판가·PO)까지만
#  읽고, 주차 숫자는 일 보고 자료가 날마다 싣고 오기 때문이다. 그래서
#  주차별 매출이 늘 $0 이었다 — 수량을 모델에서만 찾고 있었다.
#
#  나눠 받는다.
#      수량  일 보고 자료의 **출하** 공정 (나간 수량이 곧 매출이다)
#      판가  사업부 양식 (그 프로젝트 모델의 판가)
#
#  판가가 여러 개면 평균을 쓴다. 일 보고 수량은 품목 단위라 모델별로
#  쪼갤 수가 없다. 지금 일 보고에 잡히는 블룸 품목은 모두 모델이 하나라
#  평균이 곧 그 값이다 — 여럿이 되는 날에도 숫자가 뛰지 않게 평균으로 둔다.
그 프로젝트 모델들의 판가 평균. 적힌 게 없으면 0.

    쓰는 곳: _daily_div_money · get_weekly_revenue
    
```

## def _daily_ship_weeks

```
일 보고 자료의 '출하' 줄 → {주차: {plan, actual}}

    날짜를 ISO 주차로 묶는다. 보고 자료에 적힌 '41주차' 와 같은 번호다.
    안 적은 주는 아예 넣지 않는다 — 0 으로 넣으면 '안 적음' 이 '0' 이 된다.

    쓰는 곳: _daily_div_money · get_weekly_revenue
    
```

## def get_weekly_revenue

```
주차별 현황+매출:
    양산 = 모델별 weekly_plan 실적 합산 x 각 모델 판가
    개발 = weekly_summary 그룹 실적 x $3,400 고정 (모델별 주차 데이터 없음)

    부르는 곳: admin v2 — renderRevenueCard() / 앱 — api_service.dart fetchWeeklyRevenue()
    
```

## def _cleanup_plan_originals

```
서버 켤 때 — 반도체 주차 계획 원본 이미지 정리.

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _cleanup_auto_notes

```
서버 켤 때 — 자동으로 붙었던 옛 메모 정리.

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _restore_curie_busbar

```
서버 켤 때 — CURIE 버스바 품목을 백업에서 되살린다 (한 번만).

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _stamp_holds_once

```
현황 문구에 적힌 보류를 프로젝트 필드로 한 번 새겨 둔다.

    문구는 주간보고를 다시 올리거나 현황을 고치다 사라진다. 그때 보류가
    조용히 풀리면 멈춰 세운 일정이 다시 지연으로 세어진다 (CUP 15종).

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _cleanup_legacy_status

```
# '진행' 은 지금 쓰는 상태(MODEL_STATUSES)에 없는 옛 값이다. 예전 엑셀
# 가져오기가 남긴 것으로, 지연/집중관리 판정에서는 '정상' 과 똑같이 셌다.
# admin 드롭다운에만 따로 보여서 '둘이 뭐가 다르냐' 가 됐다.
# (2026-09-21 기준 파워박스 36종 · 메이저모듈 1종. Min 확인 후 바꿈)
#
# 모델의 status 만 본다. 공정 단계의 '진행중' 은 다른 값이라 안 건드린다.
# 한 번 바꾸고 나면 걸리는 게 없어 다음 기동부터는 아무 일도 안 한다.
서버 켤 때 — 옛 상태 글자 정리.

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _cleanup_cdr_prr

```
서버 켤 때 — 파워박스 CDR/PRR 공정을 한 틀로 맞춘다.

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _cleanup_bloom_dupes

```
이미 저장된 블룸 보드에 'Corva KPE' / 'Corva KPE (117품목)' 가 따로
    쌓인 것을 한 번 합친다. 합칠 게 없으면 파일을 건드리지 않는다.

    쓰는 곳: (파일 맨 위에서 바로 씀)
    
```

## def _seed_customer_groups

```
지금 있는 고객사의 묶음을 자료(customer_group)에 한 번 적는다.

    쓰는 곳: 서버 켤 때 한 번
    
```

## def _orders_load

```
홈 '수주' 자료를 읽는다.

    쓰는 곳: admin_home_orders · admin_home_summary · get_home_orders
    
```

## def get_home_orders

```
앱 홈이 읽는다 — 완료는 빼고, 급한 것부터.

    부르는 곳: admin v2 — saveOrders() / 앱 — 없음
    
```

## def admin_home_orders

```
admin 편집 화면 — 완료한 줄까지 다 준다.

    부르는 곳: admin v2 — saveOrders() / 앱 — 없음
    
```

## def _div_targets

```
사업부별 월 매출 목표(직접 입력분)를 읽는다.

    쓰는 곳: _div_target_set · _home_division_rows
    
```

## def _div_target_set

```
사업부 월 매출 목표 하나를 저장한다.

    쓰는 곳: admin_home_division_target
    
```

## def _div_model_money

```
모델의 판가 × 출하 실적. 달을 나눌 수 없어서 누계다.

    쓰는 곳: main.py 안에서는 안 쓴다 (테스트 · 예전 코드)
    
```

## def _div_actual_money

```
그 달 주차별 **실적**을 다 더한 금액 (판가 × 실적 수량).

    2026-10-27 — 전에는 _div_model_money 하나뿐이었다. 그건 판가 × 출하
    **누계**라 달을 나눌 수 없었다. 그래서 매출 관리에서 달을 10월로
    골라도 숫자가 안 바뀌었다 — 고르는 칸이 있는데 아무 일도 안 일어나면
    고장 난 것으로 읽힌다.

    주차별 실적은 달마다 칸이 나뉘어 있어서 달을 가릴 수 있다.
    타겟(_div_plan_money)과 같은 자리에서 같은 방식으로 센다 — 한쪽은
    계획, 한쪽은 실적이다. 그래야 달성률이 같은 잣대로 나온다.

    그 달 주차 실적이 **한 칸도 없으면 None** 을 돌려준다. 0 으로 돌려주면
    '그 달에 하나도 안 나갔다' 로 읽히는데, 사실은 '주차별로 안 적는
    사업부' 일 뿐이다. 부르는 쪽이 누계로 되돌아갈 수 있어야 한다.

    쓰는 곳: _div_revenue_view · _div_ytd_money · _home_division_rows
    
```

## def _div_plan_money

```
그 달 주차별 계획을 다 더한 금액 (판가 × 계획 수량).

    2026-10-27 — Min: "만약에 내가 타겟을 적지 않은 이상 그냥 그 달 계획
    다 합쳐서 타겟으로 해주고".

    타겟을 손으로 안 적은 사업부는 홈 관리에서 영영 '미등록' 이었다.
    그런데 주차별 계획은 이미 양식으로 들어와 있다 — 그걸 다 더하면
    그 달에 하기로 한 금액이고, 그게 곧 타겟이다. 손으로 적은 값이
    있으면 그게 먼저다 (사람이 정한 숫자를 계산이 덮으면 안 된다).

    실적(_div_model_money)과 달리 **그 달만** 더한다. 주차별 계획은
    달마다 칸이 나뉘어 있어서 달을 가릴 수 있다.

    쓰는 곳: _home_division_rows
    
```

## def _daily_div_money

```
# ====  일 보고로 도는 사업부의 그 달 계획·실적 금액 (2026-11-04)
#
# 매출 상세 11월에 블룸이 통째로 빠졌다. 목표를 '파일 → 직접 입력 → 그 달
# 계획 합계' 순서로 찾는데, 마지막 계산(_div_plan_money)이 품목의 주차 칸만
# 본다. 블룸은 계획·실적이 품목이 아니라 일 보고 보드에 있어서 0 이 나왔다.
# 사업부 목록 화면은 같은 보드로 11월 계획 $3,344만 · 실적 $127만을 그리는데
# 매출 화면만 비어 있었다.
#
# Min: "사업부 밑에 리스트는 있어야 되지 않을까? 그래도 어떤 목표들이
#       있는지를 알아야지"
#
# 계산은 /overview 와 **같은 함수**를 쓴다 — 출하 줄만(_daily_ship_weeks) ×
# 그 프로젝트 평균 판가(_daily_unit_price). 따로 세면 목록 카드와 숫자가 또
# 갈린다. 저장소 프로젝트(bloom_main)는 뺀다 — 보드 전체가 한 번 더 더해진다.
(그 달 출하 계획 금액, 출하 실적 금액). 일 보고 사업부가 아니면 (0, 0).

    쓰는 곳: _home_division_rows
    
```

## def _div_counts

```
정상 · 지연 · 특이사항 · 집중관리. 모델 관리에 적은 값을 그대로 센다.

    쓰는 곳: _home_division_rows
    
```

## def _home_division_rows

```
홈 사업부 매출 카드 한 줄씩 — 목표 · 실적 · 어디서 온 숫자인지.

    쓰는 곳: _all_division_revenue_view · _div_revenue_view · admin_home_division_target
          · admin_home_summary
    
```

## def admin_home_summary

```
admin '홈 관리' 화면 — 앱 홈에 뜨는 것을 한자리에서.

    부르는 곳: admin v2 — renderHomeAdmin() / 앱 — 없음
    
```

## def admin_home_division_target

```
자료에 계획이 없는 사업부의 그 달 타겟. 0 이면 지운다.

    부르는 곳: admin v2 — sv.onclick() · saveTarget() / 앱 — 없음
    
```

## def admin_home_orders_save

```
목록을 통째로 저장한다. 줄이 몇 개 안 되고 순서도 뜻이 있어서
    한 줄씩 고치는 것보다 통째로 주고받는 쪽이 어긋날 일이 없다.

    부르는 곳: admin v2 — saveOrders() / 앱 — 없음
    
```

## def _check_month

```
'2026' 이나 '2026-9' 가 들어오면 그 달이 통째로 0 으로 보인다.

    쓰는 곳: admin_division_revenue · admin_home_division_target · admin_home_summary
          · admin_revenue_estimate 외 4곳
    
```

## def _load_revenue

```
매출 실적 자료(revenue.json)를 읽는다.

    쓰는 곳: _div_breakdown · _home_division_rows · admin_revenue_estimate
          · admin_revenue_estimate_import 외 4곳
    
```

## def _save_revenue

```
매출 실적 자료를 저장한다.

    쓰는 곳: admin_revenue_estimate · admin_revenue_estimate_import · admin_revenue_import
          · admin_revenue_target
    
```

## def _year_hint

```
파일 이름에서 연도(20xx)를 뽑는다. 없으면 올해.

    쓰는 곳: admin_revenue_import
    
```

## def _div_breakdown

```
# ─── 전사 매출 한 장 ──────────────────────────────────────────────
#
# Min: "첫 번째 사진에 보이는 내용들 반도체 기준이 아니라 이제 전체적인
#      사업부 다 내용도 포함시켜주고"
#
# 사업부별 숫자는 이미 _home_division_rows 가 낸다 — 매출 파일이 있으면
# 그 값, 없으면 판가 × 실적. 여기서 다시 계산하면 admin 홈 관리 화면과
# 앱이 서로 다른 숫자를 들게 된다. 그래서 더하기만 한다.
#
# 앱에서 숨긴 사업부는 뺀다. 앱 화면에 안 뜨는 사업부가 합계에만 들어가
# 있으면, 줄을 다 더해도 합이 안 맞는다.
사업부 하나를 더 쪼갠 줄들. 없으면 빈 목록.

    쪼개는 기준이 사업부마다 다르다 —
        반도체        주간보고의 묶음 (반도체 · 데이터 센터 · 우주항공)
        그 밖         매출 파일의 '구분'
    여기서 숫자를 새로 세지 않는다. 각자 제 원본에서 가져다 붙이기만
    한다 — 다시 계산하면 사업부 줄 합계와 안 맞는 날이 온다.

    쓰는 곳: _all_division_revenue_view
    
```

## def _all_division_revenue_view

```
매출 상세 화면 — 사업부별 목표 · 실적 표.

    쓰는 곳: get_revenue
    
```

## def get_revenue

```
그 달의 묶음별 실적 + 사람이 넣은 예상. 앱 홈의 매출 카드가 쓴다.

    division 이 비면 전 사업부 합계다 (2026-11-02). 기본값은 그대로
    'semiconductor' 로 둔다 — 아직 안 올린 앱이 이 칸을 안 보내기 때문에,
    기본을 전사로 바꾸면 그 앱들의 숫자가 말없이 바뀐다.

    부르는 곳: admin v2 — renderRevenuePage() / 앱 — revenue_service.dart fetch()
    
```

## def admin_revenue_state

```
매출 관리 화면이 처음 켜질 때 받는 것.

    부르는 곳: admin v2 — renderRevenuePage() / 앱 — 없음
    
```

## def admin_revenue_import

```
주간보고 엑셀을 받는다.

    mode=preview 면 읽기만 하고 무엇이 달라지는지 돌려준다. mode=commit
    이어야 저장한다. 파일 한 장이 한 해 전체라 그 해를 통째로 갈아 끼운다.

    부르는 곳: admin v2 — send() / 앱 — 없음
    
```

## def admin_revenue_estimate

```
그 달 예상 매출을 Commodity 별로 넣는다.

    합계는 서버가 더한다. 화면이 보낸 합계를 믿으면 둘이 어긋났을 때
    어느 쪽이 맞는지 알 수 없다. 다 비우면 그 달 예상을 지운다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_revenue_target

```
그 달 타겟을 금액 하나로 넣는다. 0 이면 지운다.

    예상과 따로 둔다 — 예상은 지금 그렇게 될 것 같은 값이고 타겟은
    그렇게 만들기로 한 값이다. 한 칸에 담으면 목표를 낮춰 잡았는지
    전망이 나빠진 건지 구분이 안 된다.

    부르는 곳: admin v2 — tgs.onclick() / 앱 — 없음
    
```

## def admin_revenue_estimate_import

```
Estimate 파일을 받아 그 달 예상 매출로 넣는다.

    주간보고와 달리 한 달짜리라서, 어느 달인지는 화면에서 받는다.

    부르는 곳: admin v2 — sendEst() / 앱 — 없음
    
```

## def _pur_load

```
사업부 매입·지급 자료를 읽는다.

    쓰는 곳: admin_division_purchase · admin_division_purchase_import
          · admin_division_purchase_save · get_division_purchase
    
```

## def get_division_purchase

```
앱 카드 한 장이 필요한 전부 — 월별 + 누적.

    region: total(합계) · overseas(해외) · domestic(국내).
    안 주면 합계다 — 예전 앱은 이 인자를 모르므로 지금과 똑같이 본다.

    부르는 곳: admin v2 — save() · renderPurchasePage() / 앱 — purchase_service.dart fetch()
    
```

## def admin_division_purchase

```
사업부 매입·지급 자료 보기.

    부르는 곳: admin v2 — save() · renderPurchasePage() / 앱 — 없음
    
```

## def admin_division_purchase_save

```
사업부 매입·지급 자료 고치기 (잠김).

    부르는 곳: admin v2 — save() · renderPurchasePage() / 앱 — 없음
    
```

## def admin_division_purchase_import

```
매입·지급 엑셀 올리기.

    부르는 곳: admin v2 — upload() / 앱 — 없음
    
```

## def _div_ytd_money

```
# revenue.json 은 반도체사업부 주간보고 한 장이 원본이다. 그런데 매출
# 관리가 사이드바 '사업부' 그룹에 있어서, PCB 를 골라도 반도체 숫자가
# 떴다. 사업부를 고른 사람에게 다른 사업부 숫자를 보여주면 안 된다.
#
# 반도체가 아닌 사업부는 홈 카드가 쓰는 것과 같은 자리에서 온다 —
# 블룸은 보고자료 금액, 나머지는 모델 판가 × 출하. 타겟만 사람이 넣는다.
#
# 사업부 누계 매출
그 해 1월부터 이 달까지의 매출 (2026-10-28).

    반도체 화면에는 '연간 누적' 칸이 있는데 다른 사업부 화면에는 없었다.
    같은 화면인데 칸이 다르면 사업부를 바꿀 때마다 눈이 다시 적응해야 한다.

    달마다 같은 규칙으로 센다 — 매출 파일이 있으면 그 값, 없으면 그 달
    주차 실적 × 판가. 한 해 안에서 파일이 있는 달과 없는 달이 섞여도
    각자 제 출처로 더해진다.

    쓰는 곳: _all_division_revenue_view · _div_revenue_view
    
```

## def _div_revenue_view

```
사업부 하나의 매출. 홈 카드와 같은 숫자를 쓴다.

    쓰는 곳: admin_division_revenue
    
```

## def _ds_plan

```
# Min: "참고로 저 양식대로 개발 업로드 될거라 미리 세팅 부탁할게"
#
# 한 품목이 세 줄이다 — 프로세스 · 계획 · 실적.
# 단계 개수는 사업부마다 다르다 (반도체 13 · 메이저모듈 12 · 블룸 3).
# 그래서 머리글에 '단계 N' 이 적힌 만큼 읽는다 (dev_schedule_import).
#
# 개발 일정 양식 올리기
양식의 줄들을 등록된 모델에 붙여 본다. 저장은 안 한다.

    돌려주는 것
        {"hit": [{"project_key","label","part_number","steps",
                  "plan","actual","before_steps"}],
         "miss": [{"row","project","part_number"}]}

    쓰는 곳: admin_dev_schedule_preview
    
```

## def _ds_open

```
개발 일정 엑셀을 받아 연다 (원본은 보관함에 남긴다).

    쓰는 곳: admin_dev_schedule_apply · admin_dev_schedule_preview
    
```

## def admin_dev_schedule_preview

```
개발 일정 양식이 무엇을 바꾸는지 먼저 보여준다. 저장하지 않는다.

    부르는 곳: admin v2 — fv.onclick() · _devSend() / 앱 — 없음
    
```

## def admin_dev_schedule_apply

```
개발 일정 양식을 실제로 반영한다.

    양식에 **없는 품목은 안 건드린다.** 한 프로젝트만 적어 올려도 나머지
    품목의 공정 날짜가 사라지면 안 된다.

    양식에 **있는 품목은 파일이 정본이다** (2026-11-05).
    Min: "새로운 파일이 올라가면 기존에 있던 내용 지워지고 최신 내용
         기준으로 내용 업로드 되어야 하는데"
    전에는 빈 칸을 '안 적음' 으로 보고 옛 값을 남겼다. 그래서 새 파일에서
    'No need' 를 지워 올려도 화면에는 그대로 남았다 (플라스틱 챔버 양식 —
    비운 칸 2,404개가 하나도 안 지워졌다). 이제 그 품목의 계획 · 실적 ·
    글자 · 완료 표시는 전부 새 파일 것으로 바꾼다. 빈 칸은 빈 칸이다.

    단계 이름도 양식이 기준이다 — 블룸은 13단계가 3단계로 바뀐다.

    부르는 곳: admin v2 — fv.onclick() · _devSend() / 앱 — 없음
    
```

## def _pn_variants

```
품번 한 칸 → 맞춰 볼 열쇠들 (2026-11-02).

    Min: "KEFICO KR 파트넘버 보니까 매칭 됐는데 왜 매칭을 못 시키는건지"

    맞다 — 품번은 같았다. 괄호가 달랐을 뿐이다.

        양식   9109020119 (VCU BASE)
        등록   9109020119

    _df_norm 은 괄호를 '떼는' 게 아니라 **없애고 붙인다**. 그래서
    '9109020119vcubase' 가 되어 '9109020119' 과 안 맞았다. 품번 뒤에
    품명을 괄호로 달아 주는 양식에서는 한 줄도 안 맞는다.

    세 가지를 다 만들어 두고 하나라도 겹치면 같은 품목으로 본다.
        whole  칸 전체            9109020119vcubase
        head   괄호 앞            9109020119
        inner  괄호 안            vcubase

    inner 까지 보는 건 'PART NO : (SX3_1800 ...)' 처럼 괄호 앞이
    라벨뿐인 양식 때문이다 — 거기선 괄호 안이 곧 품번이다.

    쓰는 곳: _ds_pick_model
    
```

## def _ds_pick_model

```
개발 일정 양식 한 줄 → 등록된 모델.

    _df_pick_model 은 칸이 글자 그대로 같을 때만 찾는다. 개발 일정
    양식은 품번 뒤에 품명을 괄호로 달아 오기 때문에 그걸로는 못 찾는다.

    느슨하게 찾되 **딱 하나일 때만** 짝으로 본다. 괄호 안('HOUSING')
    같은 흔한 글자로 여럿이 걸리면, 아무거나 고르느니 안 고르는 게 낫다
    — 남의 품목에 남의 날짜가 박히는 쪽이 훨씬 나쁘다.

    쓰는 곳: _ds_pick_in_division · _ds_plan · admin_dev_schedule_apply
    
```

## def _ds_div_projects

```
그 사업부의 (프로젝트키, 프로젝트) 목록.

    쓰는 곳: _ds_pick_in_division
    
```

## def _ds_pick_in_division

```
사업부 전체에서 품번으로 찾는다 → (프로젝트키, 모델) 또는 (None, None).

    ── 왜 프로젝트를 넘어서 찾나 (2026-11-02)
    Min: "애초에 파트넘버가 다른 사업부들 다 보면 같은 수가 없는데
         왜 사업부에 맞춰서 안 바뀌는거야"

    맞는 말이라 세어 봤다. 자동차 모델 173종에 서로 다른 품번이 162개,
    겹치는 건 2개뿐이었다 — 그 2개도 'Schaeffler' 와 'Schaefller' 가
    같은 품목을 두 번 들고 있어서 생긴 것이지 진짜 겹침이 아니다.
    품번은 사실상 품목의 이름값을 한다.

    그런데 찾기는 '양식에 적힌 고객사 → 그 프로젝트 안에서만' 이었다.
    그래서 고객사를 조금 다르게 적거나(SCHAEFFLER ↔ Schaefller),
    프로젝트가 두 번 등록돼 있으면, 품번이 멀쩡히 있는데도 못 찾았다.

    이제 적힌 프로젝트에 없으면 사업부 전체를 본다. 단 **딱 하나일
    때만** 붙인다 — 둘 이상이면 어느 쪽인지 사람이 정해야 한다.

    쓰는 곳: _ds_plan · admin_dev_schedule_apply
    
```

## def _ds_show_notes

```
보여 줄 때만, 날짜가 없는 칸에 적혀 있던 글자를 채워 넣는다.

    Min: "완료 라고 적힌 부분들은 그냥 진행률에도 추가하고 완료 되었다고
         표기만 해두면 되잖아"

    진행률은 이미 센다 — 양식의 실적 칸에 '완료' 라고 적히면 그 단계의
    status 를 '완료' 로 두기 때문이다. 앱도 status 를 보고 초록 체크를
    그린다. 남은 건 글자 한 줄뿐이었다: 앱은 actual(날짜 칸)만 읽어서
    '실제 미완료' 라고 적었다.

    그래서 **보여 주는 사본에만** 글자를 날짜 자리에 채운다. 저장은
    그대로다 — expected · actual 은 날짜를 담는 칸이고, '완료' 를 거기
    적어 두면 다음에 날짜로 읽으려 할 때 깨진다.

    앱을 다시 올리지 않아도 바로 바뀐다.

    쓰는 곳: get_model_process
    
```

## def _ds_key

```
단계 이름 → 저장용 열쇠.

    영문 단계는 보던 그대로 쓴다 ('FA PO' → fa_po). 한글이 섞이면 영문만
    남겨서는 서로 구별이 안 된다 — 'PO 발주' 와 'PO 승인' 이 둘 다 'po' 가
    된다. 그래서 한글이 있으면 이름의 짧은 지문을 뒤에 붙인다. 같은 이름은
    늘 같은 열쇠라, 같은 양식을 다시 올려도 단계가 새로 생기지 않는다.

    쓰는 곳: admin_dev_schedule_apply
    
```

## def _rv_file_open

```
# Min: "ESS 매출 같은 경우에는 내가 준 그 매출 양식들 기준에서 따오면 되고"
#      "통화는 USD로 통일 시킬거고 환율은 그 주 기준 평균 금액으로"
#
# 한 해를 통째로 싣고 오는 파일이다. 그래서 올릴 때도 그 해만 갈아 끼운다.
#
# 매출 파일 올리기
매출 파일 엑셀을 받아 연다 (원본은 보관함에 남긴다).

    쓰는 곳: admin_division_revenue_file_apply · admin_division_revenue_file_preview
    
```

## def _rv_file_view

```
미리보기·반영이 같은 글자를 쓰게 한 자리에서 만든다.

    쓰는 곳: admin_division_revenue_file_apply · admin_division_revenue_file_preview
    
```

## def admin_division_revenue_file_preview

```
매출 파일이 무엇을 바꾸는지 먼저 보여준다. 저장하지 않는다.

    부르는 곳: admin v2 — inp.onchange() / 앱 — 없음
    
```

## def admin_division_revenue_file_apply

```
매출 파일을 실제로 담는다. 그 해만 갈아 끼운다.

    부르는 곳: admin v2 — go.onclick() / 앱 — 없음
    
```

## def admin_division_revenue

```
매출 파일로 들어온 사업부 매출 보기.

    부르는 곳: admin v2 — renderRevenuePage() / 앱 — 없음
    
```

## def _restore_file

```
백업 파일 이름을 안전하게 (경로 빼고 .json).

    쓰는 곳: admin_models_restore_missing
    
```

## def admin_models_restore_files

```
backend/restore/ 에 있는 복구 파일 목록.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_models_restore_missing

```
복구 파일에서 '지금 없는 모델만' 더한다.

    payload = {name, projects?: [키...], mode: "preview"|"commit"}

    같은 id 가 이미 있으면 건너뛴다. 값을 덮지 않으므로 여러 번 돌려도
    결과가 같다. 저장 직전 상태는 _save_models 가 자동 백업으로 남긴다.

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def _ot_load

```
특근 자료를 읽는다.

    쓰는 곳: admin_overtime_get · admin_overtime_import · admin_overtime_put
          · overtime_division 외 1곳
    
```

## def overtime_week

```
전사 화면 — 주차 하나, 지표 하나, 범위 하나.

    부르는 곳: admin v2 — 없음 / 앱 — overtime_service.dart fetchWeek()
    
```

## def overtime_division

```
사업부 하나 — 요일별까지.

    부르는 곳: admin v2 — 없음 / 앱 — overtime_service.dart fetchDivision()
    
```

## def admin_overtime_get

```
특근 자료 보기.

    부르는 곳: admin v2 — save() · load() / 앱 — 없음
    
```

## def admin_overtime_put

```
주차 하나를 통째로 갈아끼운다 — 다른 주는 건드리지 않는다.

    통째 교체라, 화면이 사업부를 덜 들고 저장하면 나머지가 지워진다.
    모델이 그렇게 68종 날아간 적이 있어서, 줄어드는 저장은 막는다.

    부르는 곳: admin v2 — save() · load() / 앱 — 없음
    
```

## def admin_overtime_import

```
취합 엑셀 올리기. preview 로 먼저 보여 주고 commit 이어야 저장한다.

    부르는 곳: admin v2 — upload() / 앱 — 없음
    
```

## def _daily_backup_mw

```
모든 요청이 지나가는 문 (미들웨어)
```

## def _run_in_threadpool_safe

```
오래 걸리는 일을 별도 일꾼에서 돌린다 (서버가 멈추지 않게).

    쓰는 곳: _daily_backup_mw
    
```

## def admin_backups

```
백업 목록 + 지금 보관 계획. name 을 주면 그 안을 들여다본다.

    부르는 곳: admin v2 — load() / 앱 — 없음
    
```

## def admin_backups_run

```
지금 한 벌 뜬다. 오늘 것이 있으면 그 위에 덮어쓴다.

    부르는 곳: admin v2 — run.onclick() / 앱 — 없음
    
```

## def admin_backups_prune

```
보관 기간 지난 것 정리. dry_run 이면 무엇을 지울지만 알려준다.

    부르는 곳: admin v2 — pr.onclick() / 앱 — 없음
    
```

## def admin_backups_restore

```
되돌리기. payload = {name, files?: [파일명...]}

    files 를 주면 그 파일만 바꾼다. 덮어쓰기 전에 지금 상태를 먼저
    한 벌 떠 두므로 되돌린 게 잘못이어도 다시 되돌릴 수 있다.

    부르는 곳: admin v2 — el.onclick() / 앱 — 없음
    
```

## def admin_backups_download

```
백업 파일 내려받기. 서버 밖에도 한 벌 두고 싶을 때.

    부르는 곳: admin v2 — detail() / 앱 — 없음
    
```

## def admin_weekly_template

```
그 프로젝트의 주차별 계획·실적 양식.

    month  기준 달 (YYYY-MM). 없으면 이번 달.
    months 몇 달치 시트를 넣을지 (1~6).

    부르는 곳: admin v2 — 없음 / 앱 — 없음
    
```

## def admin_plan_form

```
작성용 양식 — 한 해 한 장, 고른 달만 주차 칸이 열린다.

    달마다 한 장이던 때는, 이번 주를 적는 사람이 '지난 달까지 얼마나
    나갔더라' 를 보려면 시트를 넘기거나 보드를 따로 띄워야 했다. 한 해를
    한 장에 놓고 지난 달은 월 합계 두 칸만 둔다 — 보는 자리지 고치는
    자리가 아니다. 지난 달 주차 칸을 같이 두지 않는 이유는 분명하다.
    올리는 쪽은 시트 이름으로 달을 정하고 그 달 주차만 읽으니, 지난 달
    칸은 적어도 조용히 안 들어간다. 적을 수 있게 생겼는데 안 먹는 칸이
    제일 나쁘다.

    부르는 곳: admin v2 — el.onclick() / 앱 — 없음
    
```

## def admin_plan_export_months

```
그 해에 주차 숫자가 적힌 달. 고르는 창의 기본 체크에 쓴다.

    부르는 곳: admin v2 — back.onclick() · done() / 앱 — 없음
    
```

## def admin_plan_export

```
그 프로젝트 한 해치 주차별 계획·실적 엑셀.

    months  주차를 펼쳐 둘 달 ('2026-09,2026-10'). 안 주면 주차 숫자가
            적힌 달만 펼친다. 나머지는 접혀서 월 합계 두 칸만 보인다 —
            쉰두 주를 다 늘어놓으면 눈이 어디를 봐야 할지 모른다.

    부르는 곳: admin v2 — onclick() / 앱 — 없음
    
```

## def admin_bloom_template

```
블룸 일 보고 자료 빈 양식 (품목 칸은 채워서).

    부르는 곳: admin v2 — fm.onclick() / 앱 — 없음
    
```

## def _pick_worst_item

```
카드 안 아이템 중 상태가 가장 위험한 것 하나 반환.
```

## def _collect_hot_items

```
카드 안 RED/ORANGE 아이템 전체 수집 (신규 지연 항목 감지용).
```

## def _collect_dates

```
문자열 s 에서 모든 날짜 후보를 date 리스트로 반환. done_scope 검사 없음(마커 없이 자동판단).
```

## def _side_accent

```
    # 셀별 선을 그대로 그리면 병합 셀 때문에 한 변이 빠져 박스가 끊긴다.
    # 그래서 '강조 테두리가 걸린 셀 덩어리'를 찾아 그 덩어리의 바깥선을 그린다.
(색, 두께) — 유채색이거나 굵은 선일 때만. 평범한 검정 얇은 선은 None.
```

## def marker_for_depth

```
depth+index+is_ul로 실제 표시 문자 생성.
```

## def get_ol_depth

```
ol의 effective depth 계산 (data-depth-override 우선).
```

## def process_ol

```
ol의 li들을 순회하며 items에 추가 (nested ol도 재귀). data-depth-override 우선.
```

## def emit_runs

```
[(text, style), ...] 리스트 → bullet 아이템으로 emit.
        text_runs가 있으면 함께 저장. '*'/'★'/'※' 특별 취급 없음.
```

## def process_element

```
editor 직속 자식 처리 (div, ol, ul 등). 인라인 태그는 상위 flush에서 처리됨.
        '*' / '★' / '※' 특별 취급 없이 원문 그대로 유지.
```

## def _pick_value

```
수량 값 결정: actual 우선, 없으면 plan
```

## def _pick_efem_vtm_and_type

```
월/주차 데이터에서 efem, vtm, type 결정.

        period_dict: {"major_module::EFEM": {"plan": x, "actual": y}, ...}
        
```

## def _group_week_totals

```
그 달 주차별 합계 {'W41': {'plan':.., 'actual':..}, ...}

        양산과 개발은 숫자가 들어오는 길이 달라서 세는 함수도 다르다.
          · 양산 — 모델마다 주차 계획을 적는다
          · 개발 — 종(種) 단위로 적는다
        
```

## def month_actual

```
그 달 실적을 한 숫자로 (주차별 실적을 다 더한다).
```

## def month_plan

```
그 달 계획을 한 숫자로 (주차별 계획을 다 더한다).
```

## def _filled

```
그 칸에 사람이 뭔가 적었나.

            빈 칸은 '그대로 둬라' 다. 예전에는 빈 칸이 0 으로 들어가서,
            양식을 받아 PO 만 고쳐 올리면 판가가 전부 0 이 됐다. 정말
            0 으로 만들고 싶으면 0 을 적으면 된다.
            
```

## def _phases_from_switch

```
전환주차 한 칸을 '개발 → 양산' 두 구간으로 펴 준다.

            전환 전 판가는 이미 쌓아 둔 이력의 첫 구간을 쓴다. 없으면 지금
            판가를 쓴다 — 없는 값을 지어내면 지난달 매출이 흔들린다.
            
```

## def _apply_tint

```
openpyxl tint(-1.0~1.0)를 근사 반영.
```

## 주석 (i 근처)

```
        # 괄호 부연과 뒤에 이어 붙인 줄만 떼어낸다.
        #
        # 화살표에서 자르면 안 된다. '계획 77 → 실적 66' 처럼 화살표
        # 자체가 뜻을 가진 문장이 있어서 '계획 77' 로 끊긴다. 괄호만
        # 잘라도 '2대 고객 사급자재 지연 (ETA: 9/20) → W39 …' 은
        # '2대 고객 사급자재 지연' 으로 정리된다.
```

## 주석 (_keep_upload 근처)

```
# 엑셀은 열어서 읽고 버려 왔다. 그래서 숫자가 이상할 때 "엑셀이 원래
# 그랬나, 우리가 잘못 읽었나" 를 가릴 수가 없었다. 이제 올라온 파일을
# 손대지 않은 그대로 한 벌 남긴다 — 자세한 규칙은 upload_store.py.
#
# 읽기와 보관을 한 줄로 묶어 두는 이유는, 업로드 경로가 스무 곳이 넘어서
# 각자 보관을 따로 부르면 한 곳만 빼먹어도 그 파일이 영원히 안 남기
# 때문이다. 파일을 읽는 통로를 하나로 둔다.
```

## 주석 (_DATA_VERSION_FILES 근처)

```
# ─── 자료 버전 — 앱이 "새 자료 들어왔나" 묻는 창구 ───────────────
#
# 관리자가 엑셀을 올리면 앱이 알아서 당겨받게 하려고 둔다. 앱은 이 한 줄만
# 자주 물어보고, 값이 바뀐 때에만 전체를 다시 받는다. 매번 전부 받으면
# 통신량이 수십 배가 되고 서버도 버티지 못한다.
#
# 쓰는 쪽에는 손을 대지 않는다 — 자료 파일의 수정 시각과 크기만 본다.
# 그래서 엑셀 업로드든 화면에서 고친 것이든 터미널로 넣은 것이든 똑같이
# 잡힌다. 저장 경로마다 '버전 올리기'를 심어 두면 언젠가 한 곳을 빠뜨린다.
```

## 주석 (APP_VERSION_FILE 근처)

```
# APK 와 버전 파일은 볼륨(/data)에 둔다. 이미지에 넣으면 80MB 짜리를
# 배포마다 같이 굽게 되고, 버전만 바꾸려 해도 배포를 해야 한다.
# 볼륨에 있으면 올리는 즉시 반영된다.
#
# 저장소가 비공개면 GitHub 릴리스 주소는 로그인 없이 못 받는다.
# 그래서 앱이 이미 쓰는 이 서버가 APK 를 직접 내려준다.
```

## 주석 (_CHANGELOG_FILE 근처)

```
# 변경 내역 (CHANGELOG.md)
#
# 전에는 app_version.json 에 release_notes 한 줄만 있었다. 버전을 올려도
# 그 줄을 안 고치면 옛 노트가 그대로 나갔고, 실제로 2.3.10 이 몇 버전 전의
# 블룸 일 보고 얘기를 띄우고 있었다. 게다가 '2.3.9 와 2.3.10 이 뭐가
# 다른가' 는 어디에도 안 남아서 답할 수가 없었다.
#
# 이제 버전별로 CHANGELOG.md 에 쌓고, release.sh 가 배포하는 버전의
# 항목이 없으면 배포를 멈춘다.
```

## 주석 (m 근처)

```
        # '## 2.3.10 — 2026-09-16' 도 '## 2.3.9 이전' 도 받는다.
        # 날짜 자리를 엄격하게 잡으면 뒤엣것이 머리로 안 잡혀서
        # 앞 버전의 본문에 통째로 딸려 들어간다.
        # 줄 맨 앞의 ## 만 머리다. 들여쓴 건 머리말의 형식 예시라서
        # 머리로 잡으면 있지도 않은 버전이 생긴다.
```

## 주석 (_load_models 근처)

```
# 운영 파일을 읽은 것 한 벌. 파일이 바뀐 시각이 열쇠다 (2026-11-03).
#
# 서버가 메모리 부족으로 죽고 있었다 —
#   Out of memory: Killed process (uvicorn) anon-rss:408448kB
# 22분쯤 돌다 죽고, 다시 뜨고, 또 죽었다. 죽기 직전엔 느려지니까
# "연결이 너무 느리다" 로 먼저 보인다.
#
# _load_models 를 부르는 데가 104곳이고, /revenue 한 번에도 홈 줄 ·
# 사업부별 연간 누적 … 으로 여러 번 불린다. 큰 JSON 을 한 요청에 여러 번
# 새로 만들면, 파이썬이 그 자리를 운영체제에 바로 안 돌려줘서 쓰는
# 메모리가 계속 는다.
#
#
# 돌려주는 것은 **같은 객체**다 — 복사본을 만들면 메모리를 아끼려던
# 뜻이 없어진다. 그래서 고치는 쪽은 고친 뒤 반드시 _save_models 를
# 부른다 (그 안에서 이 자리도 새로 맞춘다). 고쳐 놓고 저장을 안 하면
# 다음에 읽는 사람이 그 고친 것을 보게 된다.
```

## 주석 (_ck 근처)

```
    # 캐시를 보는 일은 **try 밖**에서 한다. 아래 try 의 except 는
    # '파일을 못 읽었으니 씨앗으로 간다' 는 뜻이다. 캐시 코드를 그 안에
    # 두면, 캐시가 한 번 삐끗했을 때 조용히 몇 달 전 씨앗 자료가
    # 서비스된다 — 화면은 멀쩡한데 숫자만 옛날인, 아무도 못 알아채는
    # 상태다. 그 사고를 막으려고 있는 블록이니 그 안에 뭘 더 넣지 않는다.
```

## 주석 (tmp 근처)

```
    # 운영 파일을 직접 열어서 쓰지 않는다. 쓰는 도중에 서버가 죽거나 배포로
    # 교체되면 JSON 이 반만 적힌 파일이 남고, 그건 다시 읽을 수 없다.
    # 옆에 다 쓰고 → 디스크에 앉히고 → 이름만 바꾼다. os.replace 는 같은
    # 파일 시스템 안에서 원자적이라, 어느 순간에 죽어도 파일은 '옛날 것'
    # 아니면 '새 것'이지 중간이 없다.
```

## 주석 (_ESS_LEGACY 근처)

```
# ====  ESS 프로젝트가 두 벌이던 것을 한 벌로 (2026-11-03)
#
# ESS 사업부에 프로젝트가 여섯 개로 보였다. 손으로 만든 sdi · fluence ·
# epc_power 와, 사업부 양식이 만든 ess_sdi · ess_fluence · ess_epc_power 가
# 나란히 있었다. 숫자는 두 벌이 똑같았고(PO · 출하 · 판가 전부 확인),
# 다른 것은 품목 이름뿐이었다 — 옛 벌은 'SSTK_SKID' 같은 영문/약어,
# ess_ 벌은 '스마트스택 SKID' 처럼 일 보고 엑셀에 적힌 한글 이름.
#
# 그래서 일 보고가 ess_ 벌에만 붙는다. 옛 벌은 보드를 아예 못 찾았다
# (has_board: False). 민님:
#   "sdi는 어디서 나왔는지 모르겠지만 만약에 ESS 에 있는 SDI 데이터라면
#    ess_sdi랑 합쳐야 될텐데..."
#
# 지우는 쪽은 옛 벌이다. 숫자가 같으니 합칠 알맹이가 없고, 일 보고가
# 도는 쪽을 남겨야 한다.
#
# **왜 코드에서 지우나** — 이 자료는 /data 볼륨의 models.json 에 있다.
# 저장소 파일을 고쳐도 서버 것은 안 바뀌고, 프로젝트를 통째로 지우는
# 관리자 화면도 없다. 그래서 배포하면 서버가 스스로 한 번 정리한다.
# _save_models 가 직전 파일을 백업하니 되돌릴 수 있다.
#
# **안전장치** — 짝이 되는 ess_ 쪽에 품목이 실제로 있을 때만 지운다.
# 양식을 아직 안 올린 상태에서 돌면 자료만 날아간다.
#
# 정리가 끝나면 이 블록은 할 일이 없다. 다음에 손볼 때 지워도 된다.
```

## 주석 (_AUTO_ORDER_MOVE 근처)

```
# ====  자동차 수주 자료를 양식 품목으로 옮긴다 (2026-11-03)
#
# 자동차사업부에 프로젝트가 두 벌 있었다. 사업부 양식이 만든
# automotive_* 32개(198품목 — 파트넘버 · PO · 출하 · 주차 계획 · 개발
# 단계)와, 수주 엑셀('양산주요제품' 시트)이 만든 auto_* 4개(9품목 —
# 최종고객사 · 차종 · 납품위치 · SOP · 중량 · 톤수 · 불량률 · 원가
# 다섯 항목 · 2026~2031 연도별 수주 수량·금액)다.
#
# 중복이 아니라 **서로 다른 자료**였다. 그런데 auto_* 키는
# config/projects.json 에도 projects_extra.json 에도 없어서
# _auto_projects() 에 안 잡혔다. 그래서 /divisions/automotive/summary 가
# with_contract 0 · revenue 0 을 내고 있었다 — 수주 자료가 들어 있는데도
# 어느 화면에도 안 보였다.
#
# 민님: "auto는 안 될것 같아 나중에 자동화도 생길수도 있어서 그땐
#        automation_* 써야돼서 auto면 겹칠수도 있어"
#
# 그래서 auto_ 라는 접두사 자체를 없앤다. 수주 자료를 같은 품목에 얹고
# auto_* 프로젝트는 지운다.
#
# **어느 품목에 얹나** — 수주 엑셀의 납품위치가 프로젝트를 정하고, 품목은
# 이름과 판가(외화)로 맞췄다. 여섯 건은 확실하다:
#   · 오일펌프하우징 → Oil pump        판가 27.23 = 27.23
#   · V2LC HOUSING   → HOUSING ASSY V2LC  판가 33.63 = 33.6328
#   · SVCT · OV1     → 이름이 같다
#   · OBC HOUSING    → CEER OBC_HOUSING ASSY (CEER · OBC 일치)
#   · EREV ICCU HOUSING → EREV ICCU_HOUSING ASSY (ICCU 일치)
#
# 나머지 셋(KEFICO 'DCDC HOUSING' · 'HE ICCU ASSY' · VALEO
# 'DCDC HOUSING')은 같은 프로젝트 안에 후보가 둘씩 있어서 가릴 수 없었다.
# 개발품은 판가가 비어 있어 숫자로도 못 가른다. 민님이 셋은 버리라고
# 했다 — "엑셀에 있는 내용 아니면 그냥 삭제시켜". 수주 엑셀 원본이
# 서버에도 저장소에도 안 남아 있어서 확인할 길이 없었다.
#
# **안전장치** — 얹을 자리를 하나라도 못 찾으면 아무것도 안 지우고
# 그대로 둔다. 자리를 못 찾는 것은 양식 품목이 바뀌었다는 뜻이고,
# 그 상태에서 지우면 수주 자료가 사라진다.
#
# 정리가 끝나면 이 블록은 할 일이 없다. 다음에 손볼 때 지워도 된다.
```

## 주석 (normalized 근처)

```
    # 저장 전 카드/아이템 정규화
    # - text 안의 due_date 패턴 추출
    # - item 구조 표준화
    # - 향후 AI 정리/수기 저장/직접 API 호출 모두 동일 규칙 적용
```

## 주석 (idx 근처)

```
    #    한 모델을 세 가지로 부를 수 있다 — 모델명 · id · 파트넘버.
    #    엑셀에 어느 쪽으로 적혀 와도 찾히게 셋 다 열쇠로 넣는다.
    #    setdefault 를 쓰는 이유: 같은 열쇠가 두 번 나오면 **먼저 등록된**
    #    모델을 지킨다. 나중 것으로 덮으면 먼저 쓰던 모델이 사라진다.
```

## 주석 (agg_rows 근처)

```
    # 묶음 행('버스바/시트메탈류(11종)')은 모델로 만들지 않는다. 모델 목록에는
    # 품번별로 다 남기고, 보드에서만 한 줄로 묶어 보는 게 담당자가 쓰는 방식이다.
    # 그 행의 주차 계획은 묶인 모델 중 첫 번째에 얹는다 — 보드가 행 안을
    # 더하므로 줄 합계는 맞는다. PO·출하는 이미 모델별로 있으니 건드리지 않는다.
```

## 주석 (target 근처)

```
        # '키스톤 (556B)' 는 이름으로도 품번으로도 찾아본다.
        # 담당자가 품번만 모델명으로 넣어둔 경우가 있다 (큐리 556B).
        # ── 2. 이 줄이 어느 모델인지 찾는다 (세 번 시도)
        #    '키스톤 (556B)' 처럼 이름과 품번이 한 칸에 같이 오는 일이
        #    많아서, 통째로 → 품번만 → 이름만 순서로 본다.
```

## 주석 (target 근처)

```
        # 앞뒤가 겹치면 같은 모델로 본다. 단 묶음 행에는 쓰지 않는다 —
        # '버스바/시트메탈류(11종)' 이 기존 '버스바' 한 개에 붙어버려서
        # 1,740 이 그 모델로 들어가고 나머지 10개가 따로 남았다.
        # ── 3. 그래도 못 찾았으면 '앞부분이 겹치는가' 로 한 번 더
        #    글자가 4자 이상일 때만 한다. 짧으면 엉뚱한 모델에 붙는다.
        #    묶음 줄에는 쓰지 않는다 — '버스바/시트메탈류(11종)' 이
        #    기존 '버스바' 한 개에 붙어서 1,740 이 그 모델로 다 들어가고
        #    나머지 10개가 따로 남은 적이 있다.
```

## 주석 (ids 근처)

```
        #    묶음 줄('버스바/시트메탈류(11종)')은 모델로 만들지 않는다.
        #    모델 목록에는 품번별로 다 남아 있어야 하고, 보드에서만 한 줄로
        #    묶어 보는 게 담당자가 쓰는 방식이기 때문이다.
        #    주차 계획은 묶인 모델 중 첫 번째에 얹는다 — 보드가 줄 안을
        #    더해서 그리므로 줄 합계는 그대로 맞는다.
```

## 주석 (target 근처)

```
            # 만들지 않고 '못 찾았다'로 넘기는 두 경우
            #   · 묶음 줄 — 그 밑에 개별 모델이 따로 있어서 또 만들면
            #     같은 수량이 두 번 세어진다
            #   · 숫자가 하나도 없는 줄 — 만들어 봐야 빈 모델이다
```

## 주석 (_po_x 근처)

```
        # po_qty / shipped_qty 는 '지금까지 받은 주문 전체 / 지금까지 나간 전체'다.
        #
        # 예전에는 바로 위 _p / _a (이번 달 주차 합계)를 여기에 대입했다.
        # 9월 매트릭스를 올리면 PO 3,427 / 출하 2,098 이 PO 240 / 출하 41 이 되고,
        # 엑셀에는 그 달 주차만 있으니 누적값을 되살릴 방법이 없었다.
        # (같은 버그가 put_weekly_plan 에는 이미 고쳐져 있었다)
        #
        # 우선순위: 시트의 누적 칸 > 기존 값 유지 > (신규 모델일 때만) 주차 합계
```

## 주석 (has_numbers 근처)

```
            # due_text 는 담당자가 직접 적는 납기 칸이다 (예: '8월 24일').
            # 여기서 '2026-09 주차계획 · 잔여 N개' 로 덮어쓰면 입력해 둔 납기가
            # 사라지고, _parse_due_text 가 날짜를 못 읽어 마감 추적에서도 빠진다.
            # 비어 있을 때만 채운다.
            # 숫자가 들어온 달이고, 납기 칸이 비어 있을 때만 채운다
```

## 주석 (ws_out 근처)

```
    # 시트에는 개별 모델 행과 그것을 요약한 집계 행('양산 19종', '개발 22종')이
    # 같이 들어 있다. 예전에는 둘을 한꺼번에 더해서 그룹 PO·출하·주차 계획이
    # 정확히 두 배가 됐다. 집계 행은 개별 행을 이미 합한 값이므로 제외한다.
    #
    # 단, 하바플레이트 개발처럼 개별 모델 없이 총 수량만 적는 방식도 있다.
    # 그 경우 집계 행이 유일한 데이터이므로 그대로 쓴다.
```

## 주석 (_parsed 근처)

```
                # 예전에는 여기만 원문을 그대로 비교해서, '개발유형' 처럼
                # 공백이 없거나 셀에 공백이 낀 머리글을 통째로 놓쳤다.
                # 놓치면 dev_type 이 빈 채로 들어가고, 그 모델은 주차 보드
                # 어느 줄에도 안 잡힌다.
```

## 주석 (_parsed 근처)

```
                # '재료비율' 은 양식에서 수식 칸이다. 읽으면 안 된다 —
                # 그런데 '재료비' 로 시작해서 아래 가지에 먼저 걸리면
                # 재료비 자리를 빼앗고, 수식 칸이라 값이 None 이라
                # 재료비가 통째로 0 이 됐다. 그래서 먼저 걸러낸다.
```

## 주석 (by_name 근처)

```
    # 파트넘버가 있으면 그게 열쇠다.
    #
    # 예전에는 모델명으로만 맞췄다. 큐리 파일은 '버스바' 5줄, '시트메탈' 6줄이
    # 파트넘버로만 갈리는데, 16줄이 7종으로 뭉개져 들어갔다. 마지막 줄만 남았다.
```

## 주석 (_pn_seen 근처)

```
    # 한 파일 안에서 같은 파트넘버가 두 번 이상 나오면, 그 파트넘버는
    # 열쇠로 못 쓴다.
    #
    # 아리스타 PCB 가 그렇다. 품번 하나가 출하처(Foxconn·Jabil·Sanmina)
    # 마다 한 줄씩, 많으면 세 줄이다. 파트넘버로만 맞추면 세 줄이 한
    # 모델로 합쳐지고 마지막 줄만 남는다 — 조용히 사라져서 더 나쁘다.
    # 그런 파트넘버만 모델명으로 맞춘다. 한 번만 나오는 파트넘버는
    # 예전 그대로다(큐리처럼 모델명이 겹치는 파일이 여기 기댄다).
```

## 주석 (name 근처)

```
        # 모델명 칸이 비어 있으면 비어 있는 대로 둔다.
        #
        # 예전에는 품번을 넣어 채웠다. 그러면 표에 똑같은 글자가 두 칸
        # 나란히 찍힌다 — 아리스타 PCB 처럼 품번만 있고 따로 부르는
        # 이름이 없는 것이 그렇다. 화면에서는 빈 칸으로 두고, 이름이
        # 꼭 필요한 자리(앱 목록)에서만 품번을 대신 보여준다.
```

## 주석 (items 근처)

```
        # 앱·홈에 안 띄우기로 한 프로젝트라도, admin 에서 자료를 올려야 하는
        # 자리는 여기엔 나와야 한다. 블룸이 그랬다 — 품목 파일이 전부
        # bloom_main 으로 저장되는데 visible:false 라 화면에 올릴 곳이
        # 아예 없었고, 사람들은 품목 일곱 개 중 하나를 골라 올리고 있었다.
```

## 주석 (admin_uploads_page 근처)

```
#
# 보기 전용이다. 여기서는 운영 데이터를 바꾸지 않는다. admin_v2.html 은
# '수정 금지' 상태라 일부러 건드리지 않고 별도 페이지로 둔다.
#
# 주소
#   /admin/uploads               화면
#   /admin/uploads/summary       몇 건 · 몇 바이트 · 어느 달이 있나
#   /admin/uploads/list?month=   그 달의 기록
#   /admin/uploads/file/{id}     한 건 내려받기
#   /admin/uploads/zip?month=    한 달치 통째로
```

## 주석 (sd 근처)

```
                                # [SALES v2] 우선순위:
                                #   1) 섹션에 첨부된 xlsx + sales_prices → 자동 파싱/계산
                                #   2) sales_data (구조화 JSON)
                                #   3) sales_input (구식 텍스트)
```

## 주석 (ADMIN_WRITE_OFF 근처)

```
#
# 화면 쪽(admin_v2.html)만 잠그면 반쪽이다. 브라우저 콘솔 한 줄, 열어 둔
# 옛 탭, 북마크해 둔 주소로 여전히 같은 요청이 나간다. 그렇게 들어온
# 저장은 엑셀이 들고 온 값을 조용히 덮어쓴다 — 아무도 못 본다.
# 들어오는 자리에서 막는다.
#
# 되돌리려면 이 한 줄을 False 로 둔다. 화면 쪽 MODELS_READONLY 와 짝이다.
```

## 주석 (_ADMIN_LOCKED 근처)

```
# ====  admin 은 보기 전용 — 손으로 바꾸는 길을 전부 닫는다 (2026-11-04)
#
# Min: "이건 전체적으로 다 적용 되어야 하는건데 admin v2에 수정, 삭제,
#       변경을 전혀 못 하게끔 해야함" → 범위: "admin 자료 전체 잠금"
#
# 위의 ADMIN_WRITE_OFF 는 세 곳(모델 · 현황 메모 · 주차 미달 사유)만 함수
# 첫 줄에서 막고 있었다. 나머지 손 입력 길(공정 직접 입력, 목표 직접 입력,
# 노트 · 보고 카드 편집 · 삭제, 전체 초기화 …)은 열려 있었다. 함수마다 한
# 줄씩 넣으면 빠뜨린다 — 실제로 97개 중 3개만 막혀 있었다.
#
# 그래서 **목록 하나**로, 들어오는 자리(미들웨어)에서 막는다. admin 의 쓰기
# 주소는 전부 아래 두 목록 중 하나에 있어야 한다. 새 주소를 만들고 어느
# 쪽인지 안 정하면 tests/test_admin_write_lock.py 가 실패한다.
#
#   _ADMIN_LOCKED  손으로 넣고 · 고치고 · 지우는 길 → 막는다
#   _ADMIN_OPEN    파일로 들어오는 길 · 로그인 · 앱 배포 · 백업/복구 → 연다
#
# 파일로 들어오는 길도 '사업부 양식이 대신하는 것' 은 _form_only 가 따로
# 닫고 있다 (DIVISION_FORM_ONLY). 여기서는 건드리지 않는다.
# 파워박스 · 메이저모듈 전용 업로드(판가 · 공정 엑셀)는 파일 업로드라 연다.
#
# 되돌리려면 ADMIN_WRITE_OFF 를 False 로 — 위의 세 곳과 같은 스위치다.
```

## 주석 (_price_mode 근처)

```
    # 판가·재료비를 언제부터 적용할지. 화면에서 저장할 때 물어본다.
    #   from_now  이번 주부터 (지난 주차 매출은 그대로)
    #   retro     지금 적용 중인 구간을 덮는다 (입력 오류 정정)
    #   preview   저장하지 않고 '무엇이 바뀌는지' 만 돌려준다
```

## 주석 (group 근처)

```
        # 이름이 비어 있어도 버리지 않는다.
        #
        # 품번만 있고 따로 부르는 이름이 없는 것들(아리스타 PCB)은 빈 칸이
        # 맞다. 예전에는 여기서 버려서, 화면이 그 줄을 돌려보내는 순간
        # 조용히 사라졌다 — 81종 중 13종이 그랬고, '지웁니다' 경고(409)로만
        # 겨우 드러났다. 열쇠는 id 다. id 가 없는 줄만 버린다.
```

## 주석 (entry 근처)

```
        # 서버에 있던 것을 바탕으로 깔고, 이 화면에서 고치는 칸만 덮는다.
        #
        # 예전에는 빈 도시락에 아는 칸만 담았다. 그래서 이 화면이 모르는 칸
        # (엑셀이 넣어 둔 소재 · 월 실적 같은 것)은 저장할 때마다 조용히
        # 사라졌다 — "고치기만 했는데 엑셀에서 끌어온 게 다 날아간다".
```

## 주석 (_b 근처)

```
        # 화면을 연 뒤 다른 곳(엑셀 업로드·주차 입력)에서 들어간 값을 지킨다.
        #
        # 저장은 화면이 들고 있던 목록을 통째로 보낸다. 그 사본은 화면을 열
        # 때 받은 것이라, 그 사이에 엑셀로 들어온 PO·판가를 모른다. 사람이
        # 안 건드린 칸까지 보낸 값으로 쓰면 그게 옛 값으로 되돌아간다.
        #
        # 판가는 여기서 되돌려야 한다 — 아래 _apply_price_change 가
        # entry 와 old 를 비교하므로, 되돌려 두면 '안 바뀐 것' 이 되어
        # 쓸데없는 판가 구간이 안 생긴다.
```

## 주석 (_ph 근처)

```
        # 이 화면에서 편집하지 않는 묶음은 서버에 있는 것을 그대로 둔다.
        #
        # 예전에는 보낸 값을 먼저 봤다. 목록 화면은 열 때 받아 둔 사본을
        # 저장할 때 그대로 돌려보내므로, 그 사이에 다른 곳(주차 계획 입력,
        # 엑셀 업로드, Process 입력)에서 들어간 내용이 옛날 값으로 덮여
        # 되돌아갔다. 파워박스 9월 주차 계획이 그렇게 사라졌다.
        #
        #   weekly_plan/progress/summary : 주차별 계획·실적 (별도 화면·엑셀)
        #   current_expected/stage       : 프로세스에서 계산해 넣는 값
        #   auto                         : 자동차사업부 원가·계약 묶음
```

## 주석 (_proc 근처)

```
        # 프로세스는 이 화면에서 편집하지 않는다. 그런데 목록을 열 때 받아 둔
        # 사본을 저장할 때 같이 돌려보내서, 그 사이에 'Process 입력' 에서
        # 고친 내용이 옛날 값으로 덮여 되돌아갔다.
        # 보낸 값을 무시하고 서버에 있는 것을 그대로 둔다 — 프로세스를 바꾸는
        # 문은 PUT .../models/{id}/process 하나뿐이어야 한다.
```

## 주석 (_gone 근처)

```
    # 이 저장으로 사라지는 모델. '전체 교체' 라 화면이 목록을 덜 들고
    # 저장하면 나머지가 통째로 지워진다 — 실제로 챔버 19종·SpaceX 16종이
    # 그렇게 날아갔다. 사람이 정말 지운 것이면 화면이 allow_delete 를 같이
    # 보낸다. 안 보내고 많이 지우려 하면 저장을 거부한다.
```

## 주석 (_h 근처)

```
    # admin 에서 직접 고른 값이 문구보다 우선한다. 다만 빈 문자열은
    # '진행을 골랐다' 가 아니라 '그 칸이 화면에 없었다' 는 뜻이다. 그걸
    # 수동 해제로 읽으면, 현황 메모만 고쳐도 보류가 영구히 풀리고
    # hold_source='manual' 때문에 문구에서 다시 살아나지도 못한다.
```

## 주석 (_PLAN_MODEL_COLS 근처)

```
# 파워박스팀은 매주 'PBX 9월 출하계획' 파일을 쓴다. 새 양식을 따로 만들어
# 채우게 하는 대신, 쓰던 파일을 그대로 올려서 주차 계획/실적만 가져온다.
#
# PO·판가·재료비는 건드리지 않는다. 그 값들은 누적이라 여기서 잘못 덮으면
# 되살릴 방법이 없다 (예전에 PO 3,427 이 240 으로 깎인 적이 있다).
# 그리고 저장하기 전에 무엇이 무엇으로 바뀌는지 먼저 보여준다.
```

## 주석 (out 근처)

```
    # 2026-10-22 — 그 줄이 누구인가는 **파트넘버가 먼저**다.
    #
    # 양식이 바뀌었다. 품번은 늘 파트넘버 칸에 들어가고, 모델명 칸은 품번과
    # 다른 이름이 따로 있을 때만 찬다 (챔버·CUP·하바플레이트는 품번이 곧
    # 이름이라 모델명 칸이 비어 있다). 전처럼 모델명 칸만 보면 그런 줄은
    # 이름이 없다고 통째로 건너뛰어, 판가·재료비·PO·실적이 하나도 안 들어간다.
```

## 주석 (_auto_projects 근처)

```
# 한 파일에 여러 고객사가 섞여 있다. 고객사가 곧 프로젝트이므로 행마다
# 어느 프로젝트로 갈지 갈라서 넣는다. 저장 전에 무엇이 어디로 가는지 먼저 보여준다.
#
# 제품명이 열쇠다. 같은 이름이 다른 고객사에 있어도(케피코 DCDC / 발레오 DCDC)
# 프로젝트가 다르니 섞이지 않는다.
```

## 주석 (DIVISION_FORM_ONLY 근처)

```
#
# 엑셀을 올리는 자리가 스무 곳 넘게 흩어져 있었다. 사업부마다 다른 양식을
# 쓰던 때에 하나씩 붙은 것인데, 양식을 한 벌로 모은 지금은 길이 여러 개인
# 것 자체가 문제다.
#
#   · 담당자는 어디에 올려야 하는지 모른다
#   · 길마다 읽는 규칙이 달라서, 같은 숫자가 길에 따라 다르게 들어간다
#   · 후임에게 넘길 때 설명할 것이 스무 가지가 된다
#
# 그래서 **사업부 양식이 대신하는 길은 닫는다**. 닫힌 주소를 부르면 어디로
# 가야 하는지 알려 준다. 지우지 않고 막아 두는 이유는, 양식에 아직 안 담긴
# 것이 나오면 한 줄로 되돌리기 위해서다.
#
# 아래 목록에 **없는** 업로드는 그대로 열려 있다. 사업부 양식이 그 내용을
# 담고 있지 않기 때문이다.
#   매출 관리 · 매입 · 초과근무 · 공정 · 블룸 일일 · 단가 · 보고서 · 앱 배포
#
# 되돌리려면 이 한 줄을 False 로.
```

## 주석 (_df_norm 근처)

```
#
# 사업부마다 쓰는 한 벌짜리 양식을 올리면, 그 안의 두 장을 읽어
# 프로젝트(고객사)별 모델과 이슈로 반영한다.
#
#   [품목정보] → 모델 · 구분 · 판가 · 재료비 · PO/실적 · 주차별 계획
#   [이슈사항] → 품번별 이슈 (품번이 없으면 프로젝트 단위 이슈)
#
# 엑셀을 읽는 일은 division_form_import.py 가 한다. 여기서는 '읽은 것을
# 어느 프로젝트에 넣을지' 만 정한다. 둘을 한 파일에 섞으면 양식이 바뀔
# 때마다 반영 규칙까지 같이 흔들린다.
#
# 주소
#   POST /admin/divisions/{division_id}/form/preview   무엇이 바뀌는지만 보여준다
#   POST /admin/divisions/{division_id}/form/apply     실제로 저장한다
```

## 주석 (data 근처)

```
    # Min: "TC 같은 경우 일 보고에는 TC라고 작성되어 있고 모델 목록에는
    #      TC (Tele...) 이렇게 적혀있는데도 연결이 안되는건가"
    #
    # 모델 목록에 'TC (Telemaetry Cabinet)' 이라고 적혀 있으면, 시스템은
    # 이미 TC 가 무엇인지 알고 있는 셈이다. 그걸 안 쓰고 프로젝트 이름만
    # 보니까 일 보고의 'TC' 가 어디에도 안 붙었다.
    #
    # **한 사업부 안에서 그 이름이 한 프로젝트에만 있을 때만** 쓴다.
    # 두 프로젝트에 같은 이름의 모델이 있으면(하바플레이트처럼 소재가
    # 이름인 곳은 'PC (Dynex)' 가 수십 줄이다) 아무 데나 붙여 버린다 —
    # 그때는 아예 안 붙이고 '못 찾음' 으로 남기는 쪽이 낫다. 못 붙은 줄은
    # 화면이 목록으로 보여 주지만, 잘못 붙은 줄은 아무도 못 알아챈다.
```

## 주석 (_DISPLAY_NAMES 근처)

```
# 엑셀마다 같은 곳을 다르게 적는다 — 양식은 'FLUENCE', 일 보고는 '플루언스'.
# 둘 중 하나로 고르면 다른 파일이 안 붙으므로, **원문은 그대로 두고**
# 화면 이름만 바꾼다. 원문은 별칭으로 남겨서 다음 달에 영문으로 와도
# 같은 프로젝트를 찾는다.
#
# 표는 config/display_names.json 이 들고 있다. 거기 없는 이름은 적힌
# 그대로 둔다 — 모르는 회사를 음차하면 오히려 못 알아본다.
```

## 주석 (_df_project_sync 근처)

```
        # 블룸은 일 보고 엑셀 한 장이 품목을 다 싣고 와서 bloom_main 에
        # 담긴다. 각 프로젝트는 bloom_item 으로 제 몫만 잘라 본다.
        # 이걸 안 적어 두면 양식으로 새로 생긴 프로젝트(SM 등)는 자를
        # 열쇠가 없어서 일 보고 보드가 통째로 비거나 남의 것까지 뜬다.
        #
        # 단, **프로젝트형 양식에만** 붙인다. 블룸 양식의 첫 열은
        # 프로젝트(=품목, 'YFP')라 일 보고의 품목 이름과 같지만, ESS 양식의
        # 첫 열은 **고객사**('SDI')다. 일 보고에 'SDI' 라는 품목은 없으므로
        # 그대로 붙이면 정확히 일치하는 품목을 못 찾아 보드가 통째로 빈다.
        # 고객사형은 품목 이름 안의 고객사로 고른다(_daily_slice_by_project).
```

## 주석 (_df_apply_price 근처)

```
    # 주차가 빈 칸이면 _week_ord 가 '0주차'(202600)를 돌려준다. 그걸 그대로
    # 쓰면 '2026-W00' 이라는 없는 주차부터 판가가 바뀐다 — 사실상 전 기간
    # 소급이다. 주차를 못 읽으면 빈 글자로 돌려보내고, 부르는 쪽이 오늘
    # 주차로 떨어뜨린다.
```

## 주석 (_DF_TYPO_MIN_LEN 근처)

```
# ====  고객사 이름의 오타를 가장 가까운 한 곳에 붙인다 (2026-11-03)
#
# 자동차 양식에 'Schaefller' 라고 적혀 와서, 이미 있던 'Schaeffler' 를
# 못 찾고 프로젝트가 하나 더 생겼다. 같은 품번·같은 수량이 두 프로젝트에
# 나뉘어 들어갔고, 개발 일정 양식을 붙일 때 품번이 두 곳에서 걸려
# 매칭도 흐려졌다.
#
# Min: "schaefller로 적힌건 결국에는 오타거든? 근데 누가봐도 제일
#       근접하고 가까운게 schaeffler이잖아, 그런것 처럼 만약에 오타가
#       나도 최대한 비슷한 느낌의 고객사품목이 있는지 확인을 해서
#       매핑을 해줘"
#
# **고객사 이름에만 한다. 품목 이름에는 절대 하지 않는다.**
# 지금 등록된 품목 1,331종으로 재 봤더니, 글자 하나 차이인데 서로 다른
# 부품인 쌍이 78개 나왔다 —
#     ..._LAM_LH ↔ ..._LAM_RH      (좌/우)
#     ..._IB_LAM ↔ ..._OB_LAM      (안쪽/바깥쪽)
#     STOP A LAM ↔ STOP B LAM      (등급)
#     CEFEM FE(VN) ↔ CEFEM BE(VN) · Mach I VTM ↔ Mach IV VTM
# 품목에 오타 보정을 걸면 남의 수량이 조용히 섞인다. 사업부 안 고객사
# 이름 1,468쌍으로 같은 규칙을 돌렸을 때는 잘못 붙을 쌍이 0 이었다.
#
# 규칙 — 네 가지가 다 맞을 때만 붙인다
#   1) **숫자가 완전히 같다.** GSP2000 ↔ GSP5000 을 막는 조건이다.
#   2) 글자 차이 1 이내. 자리바꿈도 하나로 센다
#      (스마스트택 ↔ 스마트스택 — 일 보고에 실제로 이렇게 적혀 온다).
#   3) 양쪽 다 여섯 글자 이상. 짧은 이름은 한 글자가 너무 크다.
#   4) 후보가 **딱 하나**다. 둘 이상이면 안 붙이고 '못 찾음' 으로 남긴다 —
#      못 붙은 줄은 화면이 목록으로 보여 주지만, 잘못 붙은 줄은 아무도
#      못 알아챈다.
#
# 붙였으면 **반드시 알린다**(notes). 조용히 고치면 다음 달에 또 오타가
# 와도 아무도 모르고, 진짜 새 고객사가 오타로 오해받아 묻힌다.
```

## 주석 (month 근처)

```
    # 주차 칸이 없는 양식도 받는다 (2026-10-26).
    #
    # 전에는 여기서 400 으로 끊었다. 그런데 ESS 2026-10 양식처럼 주차
    # 블록이 아예 없는 장이 있다 — 품목 13건을 다 읽고도 "어느 달인지
    # 알 수 없습니다" 한 줄로 반영이 통째로 막혔다. 올린 사람은 왜 안
    # 되는지 알 길이 없다.
    #
    # 달이 필요한 것은 **주차별 계획을 어느 달 칸에 넣을까** 뿐이다.
    # 판가 · PO수량 · 출하수량 · 구분 · 이슈는 달과 상관없다. 그래서
    # 달이 없으면 주차 계획만 건너뛴다.
```

## 주석 (? 근처)

```
        # Min: "개발 같은 경우에는 RPM으로 rapid production이라서 한 번
        #      들어갔다가 다음주차에 없어질수도 있어 … 이건 잘 데이터
        #      저장이 되어야해"
        #
        # 개발품은 끝나면 다음 양식에서 그냥 빠진다. 문제가 생겨서 빠진
        # 게 아니다. 그래서 **지우지 않는다** — 지우면 그 품목이 몇 주에
        # 걸쳐 뭘 했는지가 통째로 사라진다.
        #
        # 대신 '마지막으로 양식에 보인 때' 를 적어 둔다. 다음 양식에서
        # 빠지면 아래에서 missing_since 가 붙고, 화면이 '양식에서 빠짐'
        # 으로 갈라 보여 준다. 다시 나타나면 그 표시를 뗀다.
```

## 주석 (_before 근처)

```
        # Min: "개발 같은 경우에는 RPM으로 rapid production이라서 한 번
        #      들어갔다가 다음주차에 없어질수도 있어서 이건 잘 데이터
        #      저장이 되어야해"
        #
        # 양식에서 빠진 모델은 지우지 않는다 (remove_missing 기본 꺼짐).
        # 그래서 자료는 남는데, 남아 있는 것이 '아직 진행 중' 인지
        # '지난주까지만 있던 것' 인지 화면에서 가릴 수가 없었다.
        # 마지막으로 양식에 실려 온 주차를 적어 두면 그 둘이 갈린다.
```

## 주석 (_before 근처)

```
        # Min: "가끔 불량 생기면 PO 취소 될 경우가 생기기도 해"
        #
        # 전에는 `if it.get("po_qty"):` 였다. 0 이 거짓이라 **PO 전량 취소가
        # 통째로 건너뛰어졌다** — 558 이 그대로 남았다. 이제 파서가 빈 칸을
        # None 으로 돌려주니(_int_or_none) 둘을 가릴 수 있다.
        #   적힌 0  → 덮어쓴다 (취소)
        #   빈 칸   → 그냥 둔다 (한 칸만 고쳐 올린 엑셀이 나머지를 안 날린다)
```

## 주석 (_pc 근처)

```
                # Min: "주차별 계획이 있는 애들은 거기에 제일 최근에
                #      작성된 실적이 있을 거 아니야. 있다고 하면 PO수량
                #      변동이 있는지 확인해주면 되지"
                #
                # 양식이 스스로 말해 준다 — 실적이 적힌 마지막 주차가
                # 그 양식의 기준 주차다 (parse_items 의 as_of_week).
                # 올린 날로 찍으면 W43 양식을 월요일에 올렸을 때 W44 에
                # 숫자가 선다 — 그 주엔 아무 일도 없었는데.
                #
                # 주차 칸이 아예 없거나 실적이 한 칸도 없는 양식
                # (CUP · 챔버)은 빈 글자다. 그때만 올린 날로 떨어뜨린다.
                # ── 날짜를 같이 적는다 (2026-10-27)
                #
                # 전에는 month(양식의 달)만 적었다. 그런데 PO증감은
                # **전주 대비**로 읽는 숫자다 — 같은 10월 안에서도 W42 에
                # 늘었는지 W43 에 늘었는지가 중요하다. 달만 적어 두면 그
                # 구분이 영영 없어진다. 양식을 올린 날을 적어 두면 주차로
                # 묶을 수 있고, 달로 접는 것도 날짜에서 바로 된다.
```

## 주석 (_pc 근처)

```
                # 12번이었다. 양식이 **주에 한 번** 올라오니 12번은 석 달도
                # 못 채운다. 그런데 보드의 PO증감 칸은 지난 6개월 + 이번 달
                # 주차를 보여준다 — 옛 기록이 먼저 밀려나가 반쯤 빈 칸이
                # 된다. 주 1회로 60번이면 1년 두 달이라 6개월 치는 확실히
                # 남는다. 한 줄이 100바이트 남짓이라 무게도 문제없다.
```

## 주석 (_pc 근처)

```
        # Min: "W43주차에 변경된 금액으로 올렸어 그러면 W42까지는 기존에
        #      있던 금액 그대로 지표가 되어야 하고 43주차 부터 변경된
        #      금액으로 지표가 되기를 원하는거야"
        #
        # 그냥 덮어쓰면 지난달 매출까지 새 판가로 다시 계산된다.
        # _df_apply_price 가 구간(phases)으로 쌓고 값도 같이 넣는다.
```

## 주석 (wp 근처)

```
        # 주차마다 '그 주차가 속한 달' 칸에 넣는다. 양식 전체를 한 달로
        # 몰아넣지 않는다 (2026-10-26).
        #
        # 반도체 양식은 주차 칸이 W40~W44 다섯이다. 달력 규칙상 W40 은
        # 9월 것이고 W41~W44 는 10월 것이다. 전에는 양식의 달 하나로
        # 몰아넣어서, 10월 양식이면 W40 자리가 10월에 생기고, 9월로
        # 읽히면 W41~W44 가 9월에 생겼다 — 9월 보드는 W36~W40 만,
        # 10월 보드는 W41~W44 만 보기 때문에 어느 쪽이든 숫자가
        # 조용히 사라졌다. HRVA 한 장에서 65칸 중 57칸이 그랬다.
        #
        # 주차가 어느 달 것인지 아는 곳은 week_calendar 하나다. 양식에
        # 적힌 달은 '못 알아본 주차' 의 대비용으로만 쓴다.
```

## 주석 (_mark 근처)

```
    # 지우지는 않는다. 개발품(RPM)은 끝나면 양식에서 그냥 빠지는데,
    # 지워 버리면 그 품목의 주차별 계획·실적이 통째로 없어진다.
    # 표시만 해 두면 자료는 남고, 화면에서는 끝난 것과 도는 것을 가른다.
    #
    # 처음 빠진 때만 적는다 — 매번 덮으면 '언제부터' 가 늘 오늘이 된다.
```

## 주석 (admin_plan_file_preview 근처)

```
        # 양식 안의 일일 실적은 아직 반영하지 않는다 (2026-10-27).
        # 읽히기는 하는데, 지금 양식 어느 장에도 '예시)' 아닌 줄이 없다 —
        # 검증할 자료가 없는 채로 저장 경로부터 만들면 틀려도 모른다.
        # 블룸·ESS 는 일 보고를 따로 파일로 받고 있고 그쪽은 그대로다.
```

## 주석 (_pstat 근처)

```
    # 프로젝트 현황 — 양식 아래 '프로젝트 현황' 두 줄 (2026-10-22)
    #
    # 모델 줄의 비고와 **다른 층**이다. 비고는 그 모델 하나만 멈춘 것이고
    # 여기는 프로젝트 전체가 멈춘 것이다. 섞으면 모델 하나 드롭이 프로젝트
    # 전체 드롭으로 읽혀서, 그 프로젝트 모델 전부가 지연 집계에서 빠진다.
```

## 주석 (ws 근처)

```
            # 그룹 PO / 실적 / 잔량
            #
            # 예전에는 weekly_summary 를 그대로 부었다. 그건 옛 주간보고 엑셀에서 들어온
            # 값이라 모델 목록을 고쳐도 따라오지 않는다. 엔클로저는 PO 4,873 을 들고
            # 있었는데 모델 합계는 4,863 이었다 (엑셀의 '009 직납 154' vs 등록된 144).
            # 화면(주차 현황 보드)은 모델 합계를 보여주므로, LLM 도 같은 걸 봐야 한다.
            #
            # 주차별 계획/실적은 여기서 다루지 않는다. 바로 아래 '주차별 매출' 블록이
            # 이번 달 주차를 정확히 넣어 준다. 예전에는 여기서 W32~W35 를 코드에
            # 박아 둬서, 9월을 물어도 8월 숫자가 같이 들어갔다.
```

## 주석 (_wr 근처)

```
                # 주차별 수량·매출은 보드·매출 카드와 같은 엔진(get_weekly_revenue)에서 받는다.
                #
                # 예전에는 여기서 따로 계산했다. 그러다 보니 같은 주차를 두 번 물으면
                # 답이 갈렸다. 특히 실적이 0일 때 계획 매출을 $3,350 고정 단가로 냈는데,
                # 판가가 $9,100~$11,803 인 엔클로저에서 계획 106대가 $355,100 으로 나왔다
                # (실제 $1,001,256). 엔진을 하나로 두면 갈릴 수가 없다.
```

## 주석 (_m_plan 근처)

```
                # 수량·매출 모두 같은 엔진에서 받는다. 앱이 보여주는 값과 같아야 한다.
                #
                # 예전에는 여기서 세 번째 계산을 했다. weekly_summary 의 양산 실적을
                # 모델별 계획 비율로 나눠 각 판가를 곱하고, 계획 매출은 $3,350,
                # 계획이 없으면 $3,245 같은 고정 단가를 썼다. 그래서 같은 주차라도
                # 챗봇과 화면의 숫자가 갈릴 수 있었다.
                #
                # 하바플레이트 개발은 모델별 입력이 비어 있어 get_weekly_revenue 가
                # 알아서 그룹 총계 x $3,400 으로 잡아 준다. 여기서 따로 볼 필요가 없다.
```

## 주석 (cur 근처)

```
            # 실적일이 찍힌 자리는 '진행중' 이라고 적혀 있어도 끝난 것이다.
            #
            # 파워박스 Striker Oxide 는 BV2 에 실적일(9/19)을 넣고도 상태가
            # '진행중' 으로 남아 있었다. 그 자리를 현재 위치로 잡는 바람에
            # 뒤에 있는 Source Inspection 을 무엇으로 바꾸든 화면은 늘 '대기'
            # 였다 — 고쳐지지 않는 것처럼 보인다.
            # _process_current 는 이미 같은 조건으로 거른다. 둘을 맞춘다.
```

## 주석 (changed 근처)

```
    # 사람이 골라 둔 건 사람만 되돌린다. 여기서 문구를 다시 읽어 덮으면
    # '진행' 으로 바꿔놔도 서버가 뜰 때마다 보류가 되살아난다.
    #
    # 2026-10-22 — 'excel' 도 같이 막는다. 이 함수는 서버가 뜰 때마다
    # 한 번씩 도는데(_stamp_hold_on_boot), 엑셀에서 상태를 '진행' 으로
    # 바꿔 올려도 현황 글에 '홀딩' 이라는 말이 남아 있으면 다음 배포에서
    # 조용히 보류로 되돌아갔다.
```

## 주석 (SOON_DAYS 근처)

```
# 완료예정일이 며칠 안 남았을 때 '임박' 으로 볼 것인가.
#
# 7일이면 34건이 뜬다. 그 정도면 목록이 아니라 배경이 되어서 아무도 안 본다.
# 3일로 좁히면 24건 — 크게 안 줄어드는데, 16건이 같은 날 하나에 몰려 있어서다.
```

## 주석 (g 근처)

```
    # 사람이 '지연' 이라고 적었으면 그것도 판정이다.
    # 양산품은 이것 말고 늦었는지 볼 근거가 없다.
    #
    # 2026-10-22 — 이슈 칸만 보던 것을 비고까지 넓혔다. 모델 정보를 엑셀로만
    # 고치게 바꾸면서 화면의 이슈 칸이 잠겼는데, 엑셀이 싣고 오는 글자 칸은
    # 비고 하나다. 비고에 적은 '지연' 을 안 읽으면 양산품은 늦었는지 볼
    # 근거가 아예 없어진다. _model_hold 는 이미 두 칸을 같이 읽고 있었다.
```

## 주석 (proc 근처)

```
    # Min: "양산 개발을 나뉘는데 개발에 들어가더라도 양산처럼 틀
    #      똑같이 맞춰달라는거였어"
    #
    # 구분(display_group)과 틀(frame)은 다른 이야기다.
    #   구분 — 목록이 양산 · 개발 두 묶음으로 나뉘는 기준. 그대로 둔다.
    #   틀   — 그 묶음에 들어갔을 때 어떤 카드 · 어떤 상세 화면으로 보나.
    #
    # 아리스타 개발은 '개발' 묶음에 그대로 있되, 안에서는 양산처럼
    # 주차별 계획 · 실적으로 본다. 공정 13단계는 반도체 것이라 PCB 에는
    # 맞는 단계가 하나도 없다 — 들어가면 빈 단계표만 떴다.
```

## 주석 (_iss 근처)

```
            # 이슈 — 적어 둔 문제. 지연과 겹치지 않는다: 지연은 개발품 공정이
            # 밀린 것이고, 이슈는 주로 양산품에 사람이 적어 넣은 것이다.
            # 경영진에게는 '일정이 늦었나' 와 '문제가 있나' 둘 다 문제다.
            # 한 모델은 한 줄이다. 위에서 지연으로 센 것을 여기서 또
            # 이슈로 세면 같은 모델이 두 번 올라온다.
```

## 주석 (label 근처)

```
            # 정상 — 문제 없이 가고 있는 것.
            #
            # 화면에 지연·이슈·임박만 늘어놓으면 제대로 가는 게 훨씬
            # 많다는 사실이 어디에도 안 나온다. 260종 중 문제는 열 몇 건이다.
```

## 주석 (_last 근처)

```
        # 방금 끝난 주만 본다. 3주 전에 못 채운 것은 이미 지나간 이야기고,
        # 마감 주차가 쌓일수록 목록이 주차 미달로만 가득 찬다.
        # (고르는 일은 _weekly_shortfall_cached 안에서 한다 — 보드를
        #  여기까지 들고 오면 캐시가 보드를 쥐고 있어야 한다.)
```

## 주석 (_div_label 근처)

```
    # Min: "이거 지금 사진에 보이는거 사업부별로 나눠줘"
    #
    # 프로젝트로 줄을 세우면 121곳이다. '모두 보기 (121곳)' 를 눌러야
    # 전체가 보이는데, 그걸 눌러도 Smac · 파워박스 · SM … 이 끝없이
    # 늘어설 뿐이라 어디가 문제인지 한눈에 안 들어온다. 사업부는 여섯이다.
    #
    # by_kind 는 그대로 둔다 — 목록 화면이 프로젝트 단위로 쓰고 있다.
    # 여기서 같은 내역을 한 겹 위로 접어서 따로 내려보낸다.
```

## 주석 (_cal_date 근처)

```
# ====  캘린더에 띄울 일정 — 운영 자료에서 바로 모은다 (2026-11-04)
#
# 캘린더는 옛 주간보고 카드(/dashboard)의 글자 속에서 '(11-07)' 같은 날짜를
# 찾아 일정을 만들고 있었다. 그 카드가 86장인데 날짜가 잡히는 카드는
# 0장이라 캘린더가 통째로 비어 있었다. 정작 자료에는 개발 예정일 367개 ·
# 실적일 301개 · 11월 이후 주차 계획 214칸이 쌓여 있었다.
#
# Min: "캘린더랑 일정들이랑 연결 되어 있어?" → "연결 부탁할게"
#
# 세 가지를 모은다.
#   1) 개발 단계  — 실적일이 있으면 그 날 '완료', 없으면 예정일에 '예정'
#   2) 주차 계획  — 프로젝트 · 주차마다 한 줄. 그 주 월요일에 '출하 계획 N대'
#   3) 일정 지연  — 따로 세지 않는다. 홈과 **같은 판정**(_enrich_model 의
#                   alert)을 쓴다. 캘린더에서 따로 '예정일이 지났다' 로 세면
#                   홈은 '일정 지연 18' 인데 캘린더는 40 이 되는 식으로 갈린다.
#                   그래서 지금 걸려 있는 단계(current_stage)에만 지연·임박을 단다.
#
#   날짜 없는 지연 — 홈이 지연으로 세는데 달력에 놓을 날짜가 없는 품목이 있다.
#                   양산품 비고에 '지연' 이라고 적힌 것이다 (PBX CEFEM VDP
#                   '시트메탈 지연' · VXT AHM HCE '파워서플라이 OEM 지연').
#                   날짜를 지어내 오늘에 꽂으면 거짓말이 되고, 빼면 홈은 18 인데
#                   캘린더는 16 이 된다. 그래서 undated 로 따로 낸다.
#
# 보류(드롭예정 포함)된 품목·프로젝트는 뺀다 — 멈춘 것을 달력에 올리면
# 할 일처럼 보인다. 홈도 보류는 따로 센다.
#
# 메모리 — 이 서버는 큰 자료를 요청마다 새로 만들다가 죽은 적이 있다
# (OOM, 2026-11-03). 운영 파일이 안 바뀌었으면 만든 결과를 다시 쓴다.
```

## 주석 (changed 근처)

```
        # Min: "이거 없어야 되는데 잇는 이유가 뭐야"
        #
        # _ensure_process 가 사업부를 안 보고 기본 13단계를 깔던 때
        # 자료에 박힌 것들이다. 비어 있을 때만 걷는다 — 날짜가 한 칸이라도
        # 적혀 있으면 사람이 쓰고 있는 단계라 건드리지 않는다.
```

## 주석 (_ 근처)

```
    # Min: "이것도 안 뜨고" (Schaeffler 프로젝트 — SocketException)
    #
    # 여기는 GET 이다. 그런데 'changed' 가 서면 models.json 을 통째로 다시
    # 쓰고, _save_models 는 쓰기 전에 백업 사본까지 한 장 뜬다. 즉 앱이
    # 프로젝트를 한 번 열 때마다 큰 파일을 두 번 쓴 셈이다.
    #
    # 재어 보니 —
    #     automotive_schaeffler (모델 4종)  140초 넘게 → 타임아웃
    #     powerbox              (모델 82종)  70초
    # 모델 수와 상관이 없다. 파일 쓰기가 값이었던 것이다.
    #
    # changed 가 서는 조건이 '개발 품목의 단계 수가 12~15가 아니면' 이라,
    # 단계가 3개·6개인 자동차 · 블룸 프로젝트는 **열 때마다 매번** 섰다.
    #
    # 저장할 이유도 없다. 여기서 바뀌는 건 기본 단계를 깔아 주는 것과
    # 빈 반도체 단계를 걷어내는 것뿐인데, 둘 다 다음에 읽을 때 또 하면
    # 되는 계산이다. 엑셀이 올라올 때(apply)는 그쪽에서 저장한다.
    #
    # changed 는 남겨 둔다 — 무엇이 손질됐는지 세는 값이라 나중에 쓴다.
```

## 주석 (get_model_weekly_plan_q 근처)

```
        # 사람이 적던 현황 글 대신 모델 수를 센 한 줄 (2026-10-28).
        # 앱은 이 칸을 그대로 '현황' 카드에 그린다 — 여기만 바꾸면
        # 앱을 다시 올리지 않아도 바로 바뀐다.
        # 적어 둔 글은 지우지 않는다. 보류·드롭 판정이 그 글을 읽는다
        # (_hold_from_note) — 지우면 보류가 통째로 풀린다.
```

## 주석 (_norm_group 근처)

```
# 그룹(양산/개발) 단위 주차 합계 · PO 관리
#
# 하바플레이트 개발은 종수가 많고 모델별 주차 계획을 따로 잡지 않는다.
# 그래서 '개발' 은 모델이 아니라 그룹 총계로 주차 계획/실적을 입력한다.
# PO 수량과 '기초 누적 실적'(주차 입력 이전까지의 누적)도 여기서 관리해서,
# 엑셀 원본 없이도 PO/실적/잔량/PO증감 표를 계산해 낼 수 있게 한다.
#   weekly_summary[그룹] = {
#     po_qty, base_actual, next_month_plan,
#     ongoing_types, done_types,          # 개발 'N종 진행중 / M종 완료'
#     weeks: { "W32": {plan, actual}, ... },
#     po_history: [{date, from, to, note}]
#   }
```

## 주석 (_weeks_in_file 근처)

```
    # 같은 파일 맨 아래의 주차표(파트번호 x 주차 계획·실적)도 같이 넣는다.
    #
    # 하바는 통일 양식으로 옮겨 가는 중이지만, 옮기는 동안 주차 숫자가
    # 어디에도 안 들어가는 구간을 만들면 안 된다. 이 표는 이미 파일에
    # 있고 모양도 우리가 읽는 그대로다 — 안 읽고 있었을 뿐이다.
```

## 주석 (models 근처)

```
            # 행마다 직접 입력이 있으면 그 값이 정본, 없으면 모델 합계.
            # 단일 모델 행은 모델 목록에서 넣는 게 낫고(진행률도 같이 잡힌다),
            # '4종'·'Dep 15종' 같은 묶음 행은 보드에서 바로 넣는 게 편하다.
            # ── 이 줄의 숫자를 어디서 가져올 것인가
            #    'manual' 줄은 보드에서 직접 적는 줄이라 모델을 안 본다.
            #    ('Dep 15종' 같은 묶음 줄 — 모델 목록으로는 못 묶는다)
```

## 주석 (_BLOOM_DIFF_CAP 근처)

```
# 반도체와 코드를 공유하지 않는다. 반도체는 '주차 x 모델' 한 겹인데
# 블룸은 '날짜 x 품목 x 공정(NCT/조립/출하)' 세 겹이고 매일 실적이 들어온다.
# 하나로 묶으면 양쪽 다 망가진다.
#
# 저장 위치: projects.<key>.daily_board
#   {title, report_date, prior_label, sheet, dates:[...], notes:[...],
#    items:[{item, code, wait_ship, wait_part,
#            steps:[{step, group, wip, month_plan, month_actual,
#                    prior_plan, prior_actual, note,
#                    days:{'YYYY-MM-DD': {plan, actual}}}]}]}
#
# 같은 달 파일을 매일 올린다. 그래서 통째로 덮지 않고 날짜 단위로 합친다.
# 새 파일에 없는 날짜·품목·공정은 지우지 않고 그대로 둔다 — 파일이 한 번
# 잘못 와도 그 전에 쌓인 게 날아가면 안 된다.
```

## 주석 (old_steps 근처)

```
        # owner(고객사)도 같이 담는다 (2026-11-03).
        #
        # Min: "엑셀 올렸는데 왜 반영을 못 하는거야"
        #
        # ESS 일 보고에는 품목 왼쪽에 고객사 열이 따로 있다
        # (SDI · 플루언스 · EPC POWER). 프로젝트 화면은 그 고객사로
        # 제 몫을 골라 낸다 (_daily_slice_by_project).
        #
        # 그런데 파서는 owner 를 읽어 놓고 여기서 버렸다. 담기는 건
        # code · wait_ship · wait_part 뿐이었다. 그래서 품목 이름
        # ('SBB 1.5 UL (한국 함안)') 으로만 고르게 됐고, 거기엔 'SDI' 가
        # 없으니 한 줄도 못 골라 "이 프로젝트는 일 보고 자료에 없습니다"
        # 가 떴다. 블룸은 고객사 열이 없어서 안 드러났다.
```

## 주석 (_BLOOM_STORE 근처)

```
# 블룸은 품목 하나가 프로젝트 하나다 (YFP · Corva KPE · SL7 …).
# 엑셀은 한 장으로 오므로 원본은 bloom_main 한 곳에 두고, 품목 프로젝트는
# 거기서 자기 몫만 잘라 본다. 갈라 저장하면 다음 업로드 때 합치는 일이
# 또 생기고, 한 번 어긋나면 되돌리기 어렵다.
```

## 주석 (cols 근처)

```
    # 한 달치를 날짜 그대로 그리면 열이 서른 개가 넘어 아무도 못 읽는다.
    # 지난주는 '그 주에 얼마나 했나' 면 되고, 손이 가는 건 이번 주뿐이다.
    # 접는 규칙은 daily_view.py 하나가 갖고 있다 — 화면마다 따로 접으면
    # 앱과 admin 의 숫자가 갈린다.
    #
    # dates · days 는 그대로 둔다 (앱이 아직 그걸 읽는다).
```

## 주석 (_DAILY_STORE 근처)

```
#
# 두 사업부는 보고 자료가 **날마다** 들어온다. 한 장에 사업부 전체(품목 ×
# 공정 × 날짜)가 들어 있어서, 프로젝트 하나에 붙이는 게 아니라 사업부
# 단위로 받는다.
#
# 블룸은 예전부터 받고 있었고 자리가 'bloom_main' 이라는 가짜 프로젝트였다.
# ESS 도 같은 모양이라 길을 하나로 모은다 — 사업부만 바꿔 부르면 된다.
#
#   POST /admin/divisions/{사업부}/daily/preview   무엇이 바뀌는지 본다
#   POST /admin/divisions/{사업부}/daily/apply     저장한다
#   GET  /divisions/{사업부}/daily-view            접은 표를 내보낸다
#
# 옛 주소(/admin/projects/{키}/bloom-daily)는 그대로 둔다. 화면이 이미
# 그걸 부르고 있어서, 지우면 블룸 업로드가 바로 멈춘다.
```

## 주석 (_now 근처)

```
        # ── 기본은 '이번 달' 이다 (2026-10-26)
        #
        # 전에는 가장 최근 달을 띄웠다. 블룸 보고 자료에는 12월 계획까지
        # 들어 있어서, 10월에 열면 제목이 '2026-12' 로 떴다. 지금 돌아가는
        # 달이 기본이어야 한다. 이번 달 자료가 없으면 그때 가장 최근 달.
```

## 주석 (_WEEK_REASON_KINDS 근처)

```
# 주차 미달과 그 사유
#
# "계획 대비 실적이 안 나오면 이슈가 있는 거 아닐까?"
#
# 맞다. 다만 끝난 주차에만 해당한다 — 아직 오지 않은 주의 실적 0 은
# 미달이 아니라 아직 안 온 것이다. 그리고 미달이 늘 문제인 것도 아니다:
# 엔클로저는 매출을 맞추려고 일부러 덜 출하하기도 한다. 그래서 사유에
# '문제' / '참고' 를 달고, 참고로 표시된 주는 문제로 세지 않는다.
# 사유가 아예 없으면 '사유 미입력' — 그건 문제 쪽이다.
```

## 주석 (_DAILY_BOARD_ROWS 근처)

```
#
# 두 사업부는 자료가 날마다 들어오고, 프로젝트 안에 모델(품번)이 없거나
# 있어도 주차 계획을 따로 안 적는다. 그래서 반도체처럼 '양산 / 개발' 두
# 줄로 그리면 두 줄 다 0 이 뜬다 — 그런 구분이 자료에 없기 때문이다.
#
# 대신 일 보고에 **공정**이 적혀 온다. 그걸 '구분' 열로 세운다.
#
#   블룸 — NCT · 조립 · 출하
#   ESS  — 제관/용접 · 조립 · 출하
#
# 품목마다 적혀 오는 공정이 들쭉날쭉하다 (BOP Assy 는 NCT 가 없고,
# SS8 · TC 는 세 줄이 다 비어 있다). 자료에 있는 것만 세우면 품목마다
# 표의 줄 수가 달라져서 옆 품목과 눈으로 못 맞춘다. 그래서 **그 달 일 보고
# 전체에 적힌 공정을 모든 품목에 똑같이 세운다** (_daily_report_rows).
# 자료가 없는 줄은 0 이 아니라 빈 칸으로 둔다 — 0 은 '계획이 0개' 로
# 읽히고, 빈 칸은 '안 적혀 있다' 다. 아래 목록은 일 보고가 아예 없을 때만
# 쓰는 기본 줄이다.
#
# ⚠ 합계 줄은 '공정을 다 더한 값' 이다. 같은 물건이 공정을 차례로 지나므로
#   합계는 몇 대 나갔는지가 아니다. 나간 수량은 '출하' 줄이다. 화면에도
#   그렇게 한 줄 적어 보낸다 (note).
#
# 품목과 프로젝트가 붙는 방법이 사업부마다 다르다.
#   블룸 — 프로젝트 하나가 품목 하나다 (projects.json 의 bloom_item)
#   ESS  — 품목이 여럿이고, 일 보고의 '고객사' 칸이 프로젝트 이름이다
#          (SDI 3종 · 플루언스 8종 · EPC POWER 1종). 그 프로젝트가 맡은
#          품목을 전부 모아 공정별로 더한다.
```

## 주석 (picked 근처)

```
    # ESS 일 보고에는 품목 왼쪽에 **고객사** 열이 따로 있다
    # (SDI · 플루언스 · EPC POWER). 품목 이름은 'SBB 1.5 (한국 함안)'
    # 처럼 고객사가 안 들어가 있어서, 이름만 뒤지면 한 줄도 못 고른다.
    # 블룸은 고객사 열이 없으니 그때는 품목 이름으로 간다.
```

## 주석 (vals 근처)

```
        # '이전 데이터' 칸 — ESS 보고자료에는 '10월05일 이전 데이터' 처럼
        # 날짜별로 안 적고 한 칸에 몰아 둔 기간이 있다. 날짜가 없어서 어느
        # 주차에도 못 넣는데, 빼 버리면 주차 칸을 다 더해도 월 합계가 안
        # 맞는다 (2026-10 SDI 가 60대 차이 났다). 맨 앞에 한 칸으로 둔다.
```

## 주석 (weeks 근처)

```
    # 보통은 그 달이 가진 주차다 (_get_month_weeks → 10월이면 W41~W44).
    # 그런데 일 보고는 **날짜**로 들어온다. 10/01~10/04 는 10월인데 주차로는
    # W40 이고, W40 은 주차 배정 규칙상 9월 것이다. 그래서 그 달 주차만
    # 세우면 10/01~10/04 에 나간 물량이 표 어디에도 안 뜬다 — 2026년 10월
    # 블룸 YFP 가 그 경우로, 32대가 조용히 사라졌다.
    #
    # 그래서 **자료에 실제로 있는 그 달 날짜의 주차**를 보태 준다. 다른 달
    # 날짜는 안 본다 (9월 시트가 섞여 들어오면 9월 주차까지 설 수 있다).
```

## 주석 (use_sections 근처)

```
    # 품목을 묶어서 보여 줄 것인가
    #
    #   블룸 — 프로젝트 하나가 품목 하나다. 품목 이름이 이미 화면 제목에
    #          있으니 한 번 더 쓰면 같은 글자가 두 번 뜬다. 평평한 표.
    #   ESS  — 프로젝트 하나가 품목을 여럿 맡는다 (SDI → SBB 1.5 · SBB 1.7
    #          · SBB 2.0). 다 더해 세 줄로 접으면 어느 품목이 밀렸는지가
    #          안 보인다. 품목마다 묶음(section)을 만들어 그 안에 공정을
    #          세운다.
```

## 주석 (hide 근처)

```
    #    PO수량 · 잔량 · 다음달 계획 · PO증감 은 일 보고 자료에 없는 숫자다.
    #    '지난달' 은 지난달 보고 자료가 올라와 있을 때만 숫자가 있다.
    #    한 달 치만 올라온 상태에서 '지난달 0' 을 띄우면 '지난달에 하나도
    #    못 냈다' 로 읽힌다 — 사실은 '그 달 자료가 아직 없다' 이다.
```

## 주석 (_weekly_filtered 근처)

```
        # 품목 묶음 표로 그린다 (앱의 _sectionTable).
        #   layout   묶음 표를 쓰라는 뜻
        #   columns  'week' — 달이 아니라 주차로 열을 세운다
        #   현황 · 비고 열은 일 보고에 없는 칸이라 끈다
```

## 주석 (out 근처)

```
    # 한 프로젝트에 맞는 줄이 없다고 거르기를 포기하면 안 된다 — 아리스타
    # 27개 중 렉이 있는 건 일곱뿐이라, 나머지 스물은 샷시 숫자를 그대로
    # 띄우게 된다. 그건 '렉만 본다' 가 아니다.
    #
    # 포기하는 건 **사업부 전체에 한 줄도 안 맞을 때**뿐이다. 그때는
    # 조건이 바뀌었거나 아직 안 적은 것이고, 빈 표를 띄우면 "자료가
    # 사라졌다" 가 된다.
```

## 주석 (_bl 근처)

```
    # 한 번 _weekly_filtered 를 여기에 걸었다가, 아리스타 프로젝트
    # (Baja-Peninsula-90W 등)의 보드가 통째로 0 이 됐다. 그 프로젝트
    # 모델은 샷시라 렉 조건에 안 맞아 다 걸러졌기 때문이다. 밑의
    # '모델별 주차 계획' 에는 숫자가 있는데 위 보드만 0 이었다.
    #
    # 렉만 보는 건 **사업부 화면의 보드** 하나다 (프로젝트를 한 줄씩
    # 세우는 그 표). 프로젝트에 들어오면 그 프로젝트의 양산 · 개발을
    # 전부 본다 — 반도체와 같다.
```

## 주석 (_hist 근처)

```
    #    PO 수량이 중간에 바뀐 기록이다. 양산/개발을 나누지 않고 한 벌만
    #    보여준다 — 엑셀 표기와 같게 맞춘 것이다.
    #
    #    출처가 둘이다 (2026-10-27).
    #      po_history  그룹 단위. 옛 임포터와 화면에서 직접 고친 것.
    #      po_log      모델 단위. **사업부 양식을 올릴 때** 서버가 적는다.
    #
    #    전에는 po_history 만 봤다. 그래서 양식을 다시 올려 PO 가 바뀌어도
    #    모델 목록 옆에는 ▲12 가 뜨는데 주차 현황 보드의 PO증감 칸은
    #    비어 있었다 — 같은 화면 두 곳이 서로 다른 말을 했다.
    #    이제 둘을 합친다. 날짜가 없는 옛 po_log 기록은 주차로 묶을 수
    #    없어서 건너뛴다(그 달 한 줄로도 못 접는다 — 달만 있고 날이 없다).
```

## 주석 (PROCESS_LEAD_DEFAULT 근처)

```
# ─── 단계별 표준 소요 (주) ───────────────────────────────
#
# '자재 입고부터 최종 승인까지 평균 석 달' 을 단계로 쪼개 보여준다.
# 실적일로 내고 싶었지만 파워박스는 실적일이 단계당 2~5건뿐이고,
# 계획일은 대부분 +7 / +14 로 찍혀 있어 실제 리드타임이 아니다
# (계획일 기준 자재입고→최종승인 중앙값이 5주 — 석 달의 절반도 안 된다).
# 그래서 기본값을 넣어 두고 admin 에서 고친다.
```

## 주석 (_AUTO_LEAD_MONTHS 근처)

```
# ─── 사업부 단위 표준 소요 (2026-11-02) ──────────────────────────────
#
# 위 PROCESS_LEAD_DEFAULT 는 프로젝트 하나(powerbox)에 걸려 있다. 블룸은
# 프로젝트가 열다섯인데 공정은 다 같은 세 단계라, 프로젝트마다 똑같은
# 값을 열다섯 번 적을 수는 없다. 사업부로 한 번 적는다.
#
# 찾는 차례는 프로젝트 저장값 → 프로젝트 기본값 → 사업부 기본값이다.
# 한 프로젝트만 다르게 가야 하면 admin 에서 그 프로젝트에만 저장하면
# 되고, 그게 사업부 값을 이긴다.
#
# 블룸 값은 Min 이 준 것이다 (2026-11-02):
#   "소요되는 주는 PO접수는 2주, PRP 3주 그 뒤로 바로 최종승인이야"
# '그 뒤로 바로' 라서 최종 승인은 0 이다. 0 은 '안 정함'(None) 과 다르다 —
# 안 정한 것은 칩에 아무것도 안 붙지만, 0 은 '걸리는 시간이 없다' 를
# 적어 둔 것이다.
#
# 단계 이름은 양식에 적힌 'PO 발주' 다. Min 은 'PO접수' 라고 부르는데,
# 같은 단계를 가리키는 말이라 둘 다 받아 둔다 — 양식 글자가 바뀌어도
# 소요가 조용히 사라지지 않게.
# ─── 자동차 — 고객사마다 단계도 소요도 다르다 (2026-11-03) ──────────
#
# Min 이 불러 준 값이다. 단위가 **개월**이고, 단계 이름이 아니라
# **자리(01~06)** 로 불러 줬다 —
#     "삼성SDI는 01 6개월 02 12개월 03 4개월 04 8개월 05 10개월 06 12개월"
#
# 이름으로 못 맞춘다. 같은 01 이라도 고객사마다 'T-car' · 'X0' · 'G1'
# 로 달라서다 (Min: "자동차 개발은 고객사별로 개발 일정 양식이
# 맞춰저야돼"). 그래서 자리로 맞춘다 — 양식의 프로세스 줄 차례 그대로.
#
# 칸이 단계보다 적으면 남는 단계는 비워 둔다. 많으면 남는 값은 버린다.
# 둘 다 양식이 바뀌었다는 뜻이라, 억지로 늘리거나 밀면 엉뚱한 단계에
# 엉뚱한 기간이 붙는다.
#
# 아직 못 받은 곳: KET KOREA · JAHWA VINA.
```

## 주석 (PROCESS_LEAD_MONTHS_BY_PROJECT 근처)

```
# 프로젝트 키 → 자리별 소요(개월). 위 두 표에서 펼쳐 둔다.
#
# 풀어 쓰면:  for group, months in _AUTO_LEAD_MONTHS.items():
#                 for pk in _AUTO_LEAD_PROJECTS[group]:
#                     PROCESS_LEAD_MONTHS_BY_PROJECT[pk] = months
# 한 줄(대입 하나)로 두는 까닭 — 테스트(test_process_lead_division)가 이 대입만
# 떼어 내서 값을 확인한다. 반복문으로 바꾸면 그 테스트가 값을 못 본다.
```

## 주석 (_CDR_PRR_PROJECTS 근처)

```
# ─── 파워박스 공정 13·14번 자리를 한 틀로 ─────────────────────────
#
# 모델이 두 틀로 갈라져 있었다.
#   CDR 틀 26종  … 12 FAIR 승인 · 13 CDR · 14 최종 승인
#   PRR 틀 22종  … 12 FAIR 승인 · 13 PRR 작성 · 14 PRR 승인 · 15 최종 승인
# 같은 자리(FAIR 승인 다음, 최종 승인 앞)다. 작성/승인을 따로 보려고
# 두 칸으로 맞춘다 (Min 2026-09-21, 안 B).
#   … 12 FAIR 승인 · 13 CDR/PRR 작성 · 14 CDR/PRR 승인 · 15 최종 승인
# CDR 틀은 CDR 날짜를 '승인' 칸으로 옮기고 '작성' 칸은 비워 둔다
# (승인이 끝나면 _process_rolled 가 앞 칸을 완료로 그린다).
#
# 번호가 붙은 파워박스 틀('01 FA PO')만 본다. 기본 13단계 틀로 들어간
# 모델(CONGA SPDB · VDP Aux)은 가공 · LAP TEST 가 있는 다른 틀이라 안 건드린다.
```

## 주석 (_rolled 근처)

```
            # 여기도 GET 이다. 기본 단계를 깔아 주려고 models.json 을
            # 통째로 다시 쓰고 있었다 — 앱이 품목 하나를 열 때마다 큰
            # 파일을 쓴 셈이다 (2026-11-03). 깔아 주는 건 다음에 읽을 때
            # 또 하면 되는 계산이라 저장할 이유가 없다.
```

## 주석 (_STEP_NA 근처)

```
# 일정표 칸에 들어오는 값은 세 가지다.
#   날짜        → 그 날짜에 끝났다
#   '완료' 글자 → 끝나긴 했는데 날짜를 안 적었다
#   'NA' 따위   → 이 모델에는 없는 단계다 (파워박스는 LAIR 이 대개 없다)
# 예전에는 셋을 구분하지 않고 '칸이 비지 않았으면 완료' 로 봐서,
# NA 도 완료로 세고 '완료' 글자를 날짜 칸에 밀어 넣었다.
```

## 주석 (admin_import_weekly_summary 근처)

```
            # 비고는 사람이 적는 칸이다. 엑셀 칸에 'Not yet' · 'In stock' 같은
            # 글자가 있다고 해서 그걸 모아 비고에 적지 않는다 — 40종이 전부
            # 단계 상태 나열로 덮여 정작 적어 둔 메모가 묻힌다.
            # 그 글자들은 단계 상태(대기·진행중)로 이미 반영돼 있다.
```

## 주석 (_new_ids 근처)

```
    # 엑셀에 없는 기존 모델 처리:
    #   RPM 개발품  → 정리 (주 단위로 바뀌는 항목이라 남길 이유가 없다)
    #   그 외(양산·HVM) → 그대로 유지. 예전에는 전부 잘려 나가면서
    #                     주차별 계획과 개발 공정 이력까지 같이 사라졌다.
```

## 주석 (_week_ord 근처)

```
# 모델의 '구분·판가 이력' (phases)
#
# 개발품으로 나가다가 도중에 양산으로 넘어가는 모델이 있다. 예) Mahabali MPD
# 는 W35 까지 개발품($138,470)으로 출하되다가 W36 부터 양산품으로 바뀐다.
# 모델에 group/price 를 하나씩만 두면 구분을 바꾸는 순간 과거 주차까지
# 새 판가로 소급 계산돼 8월 매출이 통째로 흔들린다.
#
# 그래서 시점별 구간을 배열로 둔다.
#   "phases": [
#     {"from": "2026-W01", "group": "개발", "price": 138470},
#     {"from": "2026-W36", "group": "양산", "price":  96000}
#   ]
# 주차마다 from <= 그 주차 인 마지막 구간의 구분/판가를 쓴다.
# phases 가 없으면 모델의 현재 group/price 를 그대로 쓴다(기존 동작 유지).
```

## 주석 (dev_g 근처)

```
    # 1) 개발 모델에 주차 값이 들어와 있으면 그걸 정본으로 쓴다 (파워박스 등).
    #    단가는 모델 판가가 있으면 그걸, 없으면 $3,400 고정단가.
    # 2) 모델 쪽이 비어 있고 weekly_summary['개발'] 그룹 총계만 있으면 그걸 쓴다
    #    (하바플레이트 — 개발을 모델이 아니라 그룹 단위로 관리한다).
    #    판단은 _dev_weeks_from_models 에 있다.
```

## 주석 (_PLAN_KEEP 근처)

```
# 예전 임포터가 비고에 적어 두던 단계 나열을 지운다.
#   '10 FAIR Approval: Not yet · 11 LAP Test: Not yet'
# 비고는 사람이 적는 칸이고, 저 내용은 이미 단계 상태로 들어가 있다.
#
# 사람이 적은 메모는 건드리지 않는다 — _looks_auto_note 가 모양으로 가른다.
# 한 번 지우고 나면 다음 기동에는 걸리는 게 없어 아무 일도 하지 않는다.
# _save_models 가 덮어쓰기 전에 백업을 남기므로 되돌릴 수단도 있다.
# 반도체사업부의 '주차별 계획 원본'(엑셀을 올려 이미지로 붙여 둔 것)을 뗀다.
# 주차 현황 보드가 그 자리를 대신하므로 원본은 더 볼 일이 없다.
# 챔버만 남긴다.
#
# 주의: 여기서 지우는 건 프로젝트에 붙은 weekly_plan(photo_ref) 하나다.
# 모델마다 들고 있는 weekly_plan(월·주차별 계획·실적)은 다른 값이고 건드리지 않는다.
```

## 주석 (_CURIE_KEY 근처)

```
# 내가 잘못 만든 마이그레이션이 버스바 품번 11개(560D~570D)를 한 모델로
# 합치면서 지워버렸다. 담당자는 모델 목록에는 품번별로 다 두고 보드에서만
# 한 줄로 묶어 본다. _save_models 가 덮어쓰기 직전에 남긴 자동 백업에서
# 큐리 모델 목록만 되돌린다.
#
# 한 번만 돈다. 이미 품번이 있으면 아무것도 하지 않는다.
```

## 주석 (_GROUP_SEED_FILE 근처)

```
# Min: "애초에 이러면 내가 지금 코딩으로 바꿔서 하는거잖아 이후에 다른
#      고객사 생기면 어떻게 분류하려고"
#
# 묶음은 이제 양식의 묶음 칸이 정한다 (division_columns.customer_group).
# 지금 있는 고객사는 그 칸이 아직 비어 있으니, 그때까지 쓰던 이름 규칙
# (seed_group)으로 고른 값을 한 번만 자료에 적어 둔다. 그 뒤로 새로 생기는
# 고객사는 코드가 짐작하지 않는다 — 칸이 비면 '미분류' 로 들어가고, 양식을
# 올릴 때 '묶음이 빈 고객사' 로 알려 준다.
#
# 한 번만 도는 표시는 DATA_DIR 의 작은 파일이다. 다시 돌리면 그 사이 생긴
# 새 고객사까지 이름 규칙으로 묶어 버려서, 위 약속이 깨진다.
```

## 주석 (REVENUE_FILE 근처)

```
# 매출 — 사업부 전체. 실적과 예상은 출처가 다르다.
#
# 실적은 주간보고 '1. 계획 대비 실적 (수정본) Actual FCST' 시트가 원본이다.
# 줄마다 실적, 열마다 W1~W52, 맨 아래 [합 계] 블록에 보고서 묶음까지 그대로.
#
# 예상은 사람이 넣는다. 한동안 주간보고의 '실행계획' 열을 그 달 계획으로
# 썼는데, 그 열은 작년에 짜 둔 숫자다. 9월만 봐도 주간보고 $1,964만 대
# 실제 예상 $2,422만이었다. 금액 하나만 넣어도 되고 Estimate 파일을
# 올려도 된다.
```

## 주석 (DIV_TARGET_FILE 근처)

```
# 사람이 넣는 건 타겟뿐이다. 실적은 사업부마다 이미 들어오는 자료가 달라서
# (반도체는 주간보고, 블룸은 매일 올리는 보고자료, 나머지는 모델의 판가 ×
# 출하 실적) 여기서 출처까지 같이 들고 나간다. 어디서 온 숫자인지 모르면
# 틀렸을 때 어디를 고쳐야 하는지도 모른다.
```

## 주석 (_file_usd 근처)

```
        # Min: "그냥 최대한 매출 파일 업로드가 되면 그걸 우선시 하고 만약에
        #      없으면 판가 대비 계획 or 실적 계산해서 올리라고"
        #
        # 판가 × 실적은 어림값이다. 회계가 쓰는 숫자에는 스페어 부품 ·
        # 반제품 단가 차이 · 선매출 · 환율 적용 시점이 다 들어 있어서,
        # ESS 10월만 놓고도 $516만이 달랐다. 보고 자리에서 어느 쪽이
        # 맞느냐는 질문이 나오면 답할 수가 없다.
```

## 주석 (_mon_actual 근처)

```
            # 그 달 주차 실적이 있으면 달로 가른다 (2026-10-27).
            # 없으면 지금까지처럼 누계 — 숫자가 사라지는 것보다 낫고,
            # 어느 쪽인지는 출처 글자가 말해 준다.
            # ── 누계를 '그 달 실적' 칸에 쓰지 않는다 (2026-11-03)
            #
            # Min: "11월 이제 시작인데 실적이 어디서 나온건지"
            #      "왜 누계로 되는거야...누구 마음대로"
            #
            # 그 달 자료가 없을 때 '숫자가 사라지는 것보다 낫다' 며 누계
            # (판가 × 전체 출하수량) 를 넣어 뒀었다. 그런데 누계는 달과
            # 상관없는 값이라, 11월 3일에 11월 실적이 $1187만으로 떴다.
            # 자동차는 10월도 11월도 똑같이 $253만 5,913 — 같은 누계가
            # 두 달에 겹쳐 선 것이다.
            #
            # 출처 글자로 구분된다고 적어 뒀지만 앱에는 그 글자가 안 뜬다.
            # 보는 사람에게는 그냥 '그 달 실적' 이다.
            #
            # 이제 그 달 자료가 없으면 0 이다. 누계는 '연간 누적' 자리에만
            # 선다 (_div_ytd_money). 파일 → 그 달 판가×실적 순서는 그대로.
```

## 주석 (admin_home_summary 근처)

```
        # 일 보고 사업부(블룸·ESS)는 계획이 일 보고 보드에 있다 (_daily_div_money).
        # 목표를 보드에서 잡았으면 실적도 **같은 보드**에서 잡는다 — 한 줄 안에서
        # 목표는 파일, 실적은 보드처럼 출처가 섞이면 달성률이 의미가 없다.
        # 그래서 파일 목표가 있는 달(블룸 10월 $1,340만)은 건드리지 않는다.
```

## 주석 (_gs 근처)

```
            # 내부거래도 한 줄로 세운다. 빼 놓으면 쪼갠 줄을 다 더해도
            # 사업부 줄과 안 맞는다 — 10월만 해도 $421만이 비었다
            # (묶음 합 $1652만 vs 사업부 줄 $2073만). 더해서 안 맞는
            # 숫자가 보이면 "어느 쪽이 틀렸지" 를 찾게 된다.
```

## 주석 (as_of 근처)

```
            # 그 사업부 안의 쪼갬 (2026-11-03)
            #
            # Min: "반도체 같은 경우 데이터 센터 뭐시기뭐시기 나눠져
            #      있잖아 ... 사업부 밑에 만약에 상세로 내용이 있으면
            #      눌렀을 때 뜨게끔 해줘"
            #
            # 반도체는 '반도체 · 데이터 센터 · 우주항공', 네트워크 ·
            # 자동차는 매출 파일의 구분이다. 없는 사업부는 빈 칸이고,
            # 화면은 빈 칸이면 안 펴지게 그린다.
```

## 주석 (PURCHASE_FILE 근처)

```
# PCB 사업부의 '월별 매입 현황 분석' 엑셀을 담는 자리다. 매출과 달리
# 매입은 사업부마다 형식이 제각각이라, 자동 집계 대신 admin 에서 직접
# 넣는다. 잔액은 계산하지 않고 적힌 값을 쓴다 — 표의 잔액이 매입-지급과
# 맞지 않는 달이 있어서다(선급금 상계로 보인다). 비워두면 그때만 계산한다.
```

## 주석 (admin_division_purchase_import 근처)

```
# preview 로 한 번 보여 주고, commit 이어야 저장한다. 엑셀에 없는 달은
# 건드리지 않는다 — 4~8월짜리 파일을 올렸다고 9월이 지워지면 안 된다.
#
# '합계 · 해외 · 국내' 세 열은 누적(summary)으로 따로 들어간다. 엑셀에
# 그 열이 없으면 summary 를 보내지 않는다 — 안 보내면 있던 누적을 지킨다.
```

## 주석 (money 근처)

```
        # 위 합계와 같은 잣대로 센다. 프로젝트 줄은 누계고 합계는 월별이면
        # 더해도 안 맞아서 "어느 쪽이 틀렸지" 를 찾게 된다.
        # 2026-11-03 — 그래서 여기도 누계로 안 내려간다. 합계가 0 인 달에
        # 프로젝트 줄만 누계로 서면 그 "안 맞는" 꼴이 된다.
```

## 주석 (_ds_plan 근처)

```
        # Min: "반도체사업부도 보면 내가 있는 품목이 아니더라도 매출 관리
        #      파일 기준으로 구분이 나눠져 있잖아 다른 사업부들도 다
        #      동일하게 해줘"
        #
        # 매출 파일이 적어 둔 구분 그대로 준다. 없으면 화면이 아래
        # 프로젝트별 표로 떨어진다 — 그때는 판가 × 실적이다.
```

## 주석 (_own 근처)

```
            # 양식 머리에 적힌 규칙 그대로 —
            #   "*완료되었으나 날짜 확인이 어려운 경우 '완료'로 작성"
            # 실적 칸에 '완료' 라고 적혔으면 끝난 것으로 센다. 날짜가
            # 없다고 안 끝난 것으로 두면 진행률이 영영 안 오른다.
            # 계획 칸에 '완료' 라고 적힌 것도 같다 (2026-11-05).
```

## 주석 (_ds_key 근처)

```
        # 끝난 단계인데 실적에 날짜가 없으면 실적 자리에 '완료' 라고 쓴다
        # (2026-11-05). 계획 칸에만 '완료' 가 적힌 단계, 최종 승인이 끝나
        # 앞이 전부 완료가 된 품목이 그렇다. 전에는 체크는 초록인데 글자는
        # '실제 미완료' 였다.
```

## 주석 (RESTORE_DIR 근처)

```
# 모델 저장이 '전체 교체' 라, 화면이 목록을 덜 들고 저장하면 나머지가
# 통째로 지워진다. 챔버 19종·SpaceX 16종·자동차 9종이 그렇게 날아갔고,
# 서버 자동 백업은 10개만 남아 그때까지 거슬러 올라가지 못했다.
#
# 그래서 오래된 백업에서 뽑아 둔 파일을 backend/restore/ 에 넣어 두고,
# '지금 없는 모델만' 더한다. 지금 있는 것은 절대 건드리지 않는다 —
# 되살리려다 그 뒤 13일치 작업을 덮으면 그게 더 큰 사고다.
```

## 주석 (OVERTIME_FILE 근처)

```
# 주 단위다. 한 주에 사업부 16곳, 각 곳이 요일 7줄. 지표는 잔업률(월~토)과
# 특근률(일) 둘이고 각각 전체/직접/간접으로 갈린다.
#
# 앱은 지표 하나 · 범위 하나씩만 받아 간다. 한 화면에 96칸을 내려보내면
# 폰에서 읽을 방법이 없다.
```

## 주석 (_daily_backup_mw 근처)

```
# 요청이 들어올 때 '오늘 것이 있나' 를 보고 없으면 만든다. fly 머신이
# auto_stop 이라 자정에 깨어 있지 않아서, 시계에 기대는 스케줄러를 쓸 수
# 없다. 아침에 누가 앱을 처음 열면 그때 그날 백업이 생긴다.
#
# 백업은 /data/backups/ 안에서만 지운다. 운영 데이터는 건드리지 않는다.
```

## 주석 (admin_weekly_template 근처)

```
# 주차는 반드시 week_calendar 에서 받는다. 손으로 적으면 어긋난다 —
# 2026-10 의 주차는 W41~W44 이고 W40 은 9월 소유다. 양식과 보드가 서로
# 다른 주차를 말하면 올려도 칸이 안 맞는다.
#
# 모델 칸을 채워 보내는 이유는 따로 있다. 매주 품번 수십 개를 손으로
# 적게 하면 언젠가 하나를 다르게 적고, 다르게 적힌 줄은 어느 모델에도
# 안 붙어 조용히 사라진다.
```

## 주석 (data 근처)

```
    # 숫자를 채워서 내려준다. 빈 양식을 따로 두지 않는 이유 —
    #   · 숫자가 없는 프로젝트는 채워도 비어 있다
    #   · 숫자가 있는 프로젝트에서 빈 양식은 '지난 주 실적이 뭐였나' 를
    #     보드에서 따로 찾게 만든다
    #   · 받은 파일에 이번 주만 적어 그대로 올리면 되니 손이 덜 간다
```

## 주석 (admin_bloom_template 근처)

```
# 기준은 사람이 쓰던 '블룸_보고자료_..._ver4_1.xlsx' 의 '10월 보고자료'
# 시트다. 새 모양을 짜내지 않고 그 모양을 그대로 만든다 — 받는 분들이
# 지금 쓰던 대로 채우면 되고, 파서도 그 머리글을 보고 열을 찾는다.
#
# 품목 칸은 미리 채워 보낸다. 매달 품목 여덟 개를 손으로 적게 하면
# 언젠가 하나를 다르게 적고, 다르게 적힌 줄은 어느 품목에도 안 붙어
# 조용히 사라진다. config 의 bloom_item 순서대로 깔고, 이미 올라와 있는
# 보드에만 있는 품목(SS8 처럼 프로젝트가 없는 것)을 뒤에 붙인다.
```

