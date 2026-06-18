# -*- coding: utf-8 -*-
"""[임시 재현] grp_goyang 에 강원/길음 공고가 왜 통과(is_relevant)했는지 실데이터로 재현.
실제 파이프라인: fetch_kstartup 가 만드는 item 형태 → enrich_item_from_detail(상세 지역 보강)
→ evaluate_notice(item, group). 메일 발송/seen 저장 없음(읽기 전용)."""
import json, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
for k, v in [("BIZINFO_API_KEY", "x"), ("ANTHROPIC_API_KEY", "x"),
             ("GMAIL_ADDRESS", "x@x.com"), ("GMAIL_APP_PASSWORD", "x"),
             ("MONITOR_NO_PERSIST_SEEN", "1")]:
    os.environ.setdefault(k, v)
import monitor as m

groups = {g["id"]: g for g in json.load(open("groups.json", encoding="utf-8"))}
grp = groups["grp_goyang"]

cases = [
    {
        "id": "kstartup_178177",
        "title": "2026 강원권 LIPS 민간운영사 연합 INVESTOR DAY 6월 참여기업 모집",
        "link": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancClssCd=PBC010&schM=view&pbancSn=178177",
        "author": "2026 강원권 LIPS 민간운영사 연합 INVESTOR DAY 6월",
        "description": "",
        "deadline": "2026-06-25",
        "source": "K-Startup",
        "posted_date": "",
    },
    {
        "id": "kstartup_178167",
        "title": "[길음청년희망스토어]청년창업실험공간 공업사 2026년 하반기 공간지원사업 공고",
        "link": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancClssCd=PBC010&schM=view&pbancSn=178167",
        "author": "[길음청년희망스토어]청년창업실험공간 공업사 2026년 하반기 공간지원사업 공고",
        "description": "",
        "deadline": "2026-06-26",
        "source": "K-Startup",
        "posted_date": "",
    },
]

print("DETAIL_ENRICH_HOSTS =", getattr(m, "DETAIL_ENRICH_HOSTS", "N/A"))
for c in cases:
    print("\n" + "=" * 70)
    print("TITLE:", c["title"])
    enriched = m.enrich_item_from_detail(dict(c))
    print("  region_field   :", repr(enriched.get("region_field")))
    print("  desc(head 200) :", repr((enriched.get("description") or "")[:200]))
    nt = m._notice_text(enriched)
    print("  notice_text head:", repr(nt[:160]))
    # 지역 판정 (그룹용)
    rinfo = m.classify_region_for_group(enriched, m._normalize_group(grp))
    print("  classify_region_for_group:", rinfo)
    print("  _detect_target_regions(raw):", m._detect_target_regions(
        f"{enriched.get('title','')} {enriched.get('description','')} {enriched.get('author','')} {enriched.get('region_field','')}"))
    ev = m.evaluate_notice(enriched, grp)
    print("  --- evaluate_notice ---")
    for k in ["is_relevant", "region_status", "district_status",
              "deadline_status", "business_years_status", "support_amount_status",
              "review_needed", "exclude_reason_codes", "eligible_regions",
              "excluded_regions", "_types", "notes"]:
        print(f"    {k} = {ev.get(k)}")
