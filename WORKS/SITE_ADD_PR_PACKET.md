# SITE_ADD_PR_PACKET (템플릿)

이 파일은 **사이트 추가 PR 패킷의 고정 템플릿**입니다.  
실제 패킷은 Vercel UI `/sites/add` → 「PR 패킷 생성」 또는 API `POST /api/sites/packet` 실행 시 **덮어씁니다**.

## 수정 대상 파일

- `sites.json`

## 추가될 사이트 JSON (예시)

```json
{
  "id": "example_tp",
  "name": "예시 TP 공고",
  "type": "html_table",
  "url": "https://example.go.kr/notice/list",
  "enabled": true,
  "is_aggregator": false,
  "note": "지자체/TP — UI에서 생성",
  "selectors": {
    "row": "table tbody tr"
  }
}
```

## diff 예시

```diff
--- a/sites.json
+++ b/sites.json
@@ sites.json에 1건 추가 @@
+  { "id": "example_tp", ... }
```

## PR 제목 (초안)

`feat(sites): add {id} — {name}`

## PR 본문 (초안)

- 사이트 수집 소스 추가
- URL / type / enabled 명시
- [ ] `python3 scripts/monitor_dry_run.py --skip-coverage-fetch`
- [ ] 실제 메일 발송 없음

## 사용자 승인 필요 지점

1. JSON 내용·URL·collector type 검토
2. PR merge (자동 merge 금지)
3. 운영 cron·Actions는 별도 승인

---

**최신 패킷:** UI에서 생성하거나 로컬 API 호출 후 이 파일 내용을 확인하세요.
