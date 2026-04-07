"""
monitor.py v6 파이프라인 테스트 (실제 API/이메일 호출 없음)
테스트 항목: ① 중복제거 ② 날짜필터 ③ 지역필터 ④ 키워드필터 ⑤ 지원유형 분류
"""
import sys, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# monitor.py 함수 직접 import
sys.path.insert(0, str(Path(__file__).parent))

# 환경변수 mock (실제 키 불필요)
import os
os.environ.setdefault("BIZINFO_API_KEY",    "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY",  "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS",      "test@test.com")

from monitor import (
    dedup_items, date_filter, filter_for_group,
    classify_support_type, normalize_title,
    KST, ALL_SUPPORT_TYPES,
)

# ── 테스트용 mock 공고 ────────────────────────────────────────────
yesterday = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")
today     = datetime.now(KST).strftime("%Y-%m-%d")

MOCK_ITEMS = [
    # [A] 기업마당(통합) + K-Startup(주관) 동일 공고 → K-Startup 유지
    {
        "id": "bizinfo_001", "title": "2026년 뷰티산업 육성 지원 사업 뷰티 디자인 개발 과제 참여기업 모집",
        "link": "https://bizinfo.go.kr/001", "author": "중소벤처기업부",
        "description": "뷰티 디자인 개발 사업화 지원금 바우처",
        "deadline": "2026-04-17", "source": "기업마당",
        "posted_date": yesterday, "is_aggregator": True,
    },
    {
        "id": "kstartup_176993", "title": "2026년 뷰티산업 육성 지원 사업 「뷰티 디자인 개발 과제」참여기업 모집",
        "link": "https://k-startup.go.kr/176993", "author": "중소벤처기업부",
        "description": "뷰티 디자인 개발 사업화 지원",
        "deadline": "2026-04-17", "source": "K-Startup",
        "posted_date": yesterday, "is_aggregator": False,
    },
    # [B] 인천 화장품 수출바우처 → 인천 그룹 매칭
    {
        "id": "nipa_001", "title": "2026년 인천 화장품 수출바우처 지원사업",
        "link": "https://nipa.kr/001", "author": "인천테크노파크",
        "description": "인천 소재 화장품 제조업체 수출바우처 지원",
        "deadline": "2026-05-30", "source": "NIPA",
        "posted_date": yesterday, "is_aggregator": False,
    },
    # [C] 경남 로봇 전시회 → 인천 그룹 제외 (타지역)
    {
        "id": "bizinfo_002", "title": "2026 경남 로봇 해외전시회 참가지원",
        "link": "https://bizinfo.go.kr/002", "author": "경남테크노파크",
        "description": "경남 소재 로봇기업 해외전시회 참가비 지원",
        "deadline": "2026-04-20", "source": "기업마당",
        "posted_date": yesterday, "is_aggregator": True,
    },
    # [D] 날짜 없음 (날짜불명) → 포함 처리
    {
        "id": "myfair_001", "title": "K-뷰티 해외박람회 참가 지원",
        "link": "https://myfair.co/001", "author": "KOTRA",
        "description": "K-뷰티 기업 해외박람회 참가비 바우처",
        "deadline": "2026-06-30", "source": "마이페어",
        "posted_date": "",  # 날짜불명
        "is_aggregator": True,
    },
    # [E] 오늘 올라온 공고 → D-1 필터로 제외
    {
        "id": "bizinfo_003", "title": "오늘 올라온 수출 컨설팅 지원사업",
        "link": "https://bizinfo.go.kr/003", "author": "중진공",
        "description": "수출 기업 컨설팅 멘토링 지원",
        "deadline": "2026-05-01", "source": "기업마당",
        "posted_date": today,  # 오늘 → D-1 필터로 제외
        "is_aggregator": True,
    },
    # [F] 전국 화장품 교육 → 인천 그룹 포함 (전국)
    {
        "id": "kotra_001", "title": "화장품 수출역량강화 교육",
        "link": "https://kotra.or.kr/001", "author": "KOTRA",
        "description": "화장품 제조기업 수출 역량강화 교육 세미나",
        "deadline": "2026-05-15", "source": "KOTRA",
        "posted_date": yesterday, "is_aggregator": False,
    },
]

TEST_GROUP = {
    "id": "grp_test",
    "name": "인천 화장품 수출팀",
    "active": True,
    "regions": ["인천"],
    "keywords": {"logic": "OR", "keywords": ["화장품", "뷰티", "K-뷰티", "해외전시회", "수출"]},
    "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
    "recipients": ["ekth3691@gmail.com"],
}

SEP = "=" * 55

def run_test():
    print(f"\n{SEP}")
    print("  수출지원 모니터링 v6 파이프라인 테스트")
    print(SEP)

    # ── STEP 1: 중복제거 ───────────────────────────────────────────
    print("\n[1] 중복제거 (주관기관 우선)")
    deduped = dedup_items(MOCK_ITEMS)
    removed = len(MOCK_ITEMS) - len(deduped)
    print(f"    수집: {len(MOCK_ITEMS)}건 → 중복제거 후: {len(deduped)}건 (제거 {removed}건)")

    # K-Startup 버전이 남아야 함
    kst_survived = any(it["id"] == "kstartup_176993" for it in deduped)
    biz_removed  = all(it["id"] != "bizinfo_001" for it in deduped)
    print(f"    ✅ K-Startup 버전 유지: {'OK' if kst_survived else 'FAIL'}")
    print(f"    ✅ 기업마당 중복 제거:  {'OK' if biz_removed else 'FAIL'}")

    # ── STEP 2: 날짜필터 (D-1) ────────────────────────────────────
    print(f"\n[2] 날짜필터 (어제={datetime.now(KST).date() - __import__('datetime').timedelta(days=1)})")
    matched, unknown = date_filter(deduped, days_back=1)
    today_excluded = all(it["id"] != "bizinfo_003" for it in matched + unknown)
    print(f"    날짜 매칭: {len(matched)}건 / 날짜불명: {len(unknown)}건")
    print(f"    ✅ 오늘 공고 제외: {'OK' if today_excluded else 'FAIL'}")
    print(f"    ✅ 날짜불명 포함:  {'OK' if any(it['id']=='myfair_001' for it in unknown) else 'FAIL'}")

    # 처리 대상: 날짜 매칭 + 날짜불명
    target_items = matched + unknown
    print(f"    처리 대상: {len(target_items)}건")

    # ── STEP 3: 그룹 필터 ─────────────────────────────────────────
    print(f"\n[3] 그룹 필터 — '{TEST_GROUP['name']}'")
    g_items = filter_for_group(target_items, TEST_GROUP)
    경남_excluded = all(it["id"] != "bizinfo_002" for it in g_items)
    인천_included = any(it["id"] == "nipa_001" for it in g_items)
    전국_included = any(it["id"] == "kotra_001" for it in g_items)
    print(f"    그룹 매칭: {len(g_items)}건")
    print(f"    ✅ 경남 공고 제외:       {'OK' if 경남_excluded else 'FAIL'}")
    print(f"    ✅ 인천 화장품 공고 포함: {'OK' if 인천_included else 'FAIL'}")
    print(f"    ✅ 전국 화장품 공고 포함: {'OK' if 전국_included else 'FAIL'}")

    # ── STEP 4: 지원유형 분류 ─────────────────────────────────────
    print("\n[4] 지원유형 자동 분류")
    type_tests = [
        ("수출바우처 지원", ["지원금/바우처"]),
        ("컨설팅 멘토링 세미나", ["컨설팅·교육·상담"]),
        ("VC 투자 엔젤투자", ["투자"]),
        ("해외진출 협력 네트워크", ["그외"]),
    ]
    all_ok = True
    for title, expected in type_tests:
        result = classify_support_type({"title": title, "description": ""})
        ok = any(e in result for e in expected)
        print(f"    {'✅' if ok else '❌'} '{title}' → {result} (기대: {expected})")
        if not ok: all_ok = False

    # ── 최종 결과 요약 ─────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  최종 파이프라인 요약")
    print(SEP)
    print(f"  수집:       {len(MOCK_ITEMS)}건")
    print(f"  중복제거:   → {len(deduped)}건 ({removed}건 제거)")
    print(f"  날짜필터:   → {len(target_items)}건 (오늘 공고 제외)")
    print(f"  그룹필터:   → {len(g_items)}건 (인천 화장품팀 기준)")
    print()
    print("  [그룹 매칭 공고 목록]")
    for it in g_items:
        types = ", ".join(it.get("_types", ["미분류"]))
        print(f"  📌 {it['title'][:45]}")
        print(f"     유형:{types} | 출처:{it['source']} | 등록:{it.get('posted_date') or '불명'}")
    print(SEP)

    pass_cnt = sum([
        kst_survived, biz_removed, today_excluded, 경남_excluded, 인천_included, 전국_included, all_ok
    ])
    print(f"\n  테스트 결과: {pass_cnt}/7 통과\n")

if __name__ == "__main__":
    run_test()
