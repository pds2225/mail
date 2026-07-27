"""company_match(기업단위) ↔ monitor(그룹단위) 지역 verdict 대칭 가드.

계획서 '대칭 원칙': 같은 공고에 대해 두 경로가 같은 적격/차단 결론을 내야 한다.
명확한 타지역 한정·권역·own·전국 공고로 두 경로의 PASS/BLOCK 일치를 박는다.
('전국+개최지' 같은 모호 surface 케이스는 양쪽 기준이 달라 제외.) self-contained.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mail_core.matching import company_match as cm  # noqa: E402
import monitor as mon  # noqa: E402

OWN_CITIES = ["서울", "인천", "부산", "대구", "광주"]

# (이름, 공고) — 명확한 지역 신호만(모호 surface 제외)
CASES = [
    ("대구 소재 한정", {"title": "대구 제조", "description": "대구광역시 소재 제조기업만 신청."}),
    ("부산 소재 한정", {"title": "부산 물류", "description": "부산광역시 소재 기업만 신청."}),
    ("서울 소재 한정", {"title": "서울 사업화", "description": "서울특별시 소재 기업만 신청."}),
    ("경상권 한정", {"title": "경상권 제조", "description": "경상권 소재 제조기업만 신청."}),
    ("호남권 한정", {"title": "호남권 지원", "description": "호남권 소재 기업만 신청."}),
    ("수도권 공동", {"title": "수도권 제조", "description": "수도권 소재 제조기업 대상."}),
    ("진짜 전국", {"title": "전국 수출바우처", "description": "전국 중소제조기업 대상."}),
]


def _cm_verdict(item, city, dist=""):
    c = {"id": "t", "email": cm.TEST_RECIPIENT, "active": True,
         "region": {"city": city, "district": dist},
         "industry_keywords": ["제조", "제조업"], "interest_keywords": ["수출", "제조", "사업화"],
         "exclude_keywords": [], "match_threshold": 50}
    rs = cm.compute_match_score(item, c)["breakdown"]["region_status"]
    # other_only 만 명확 차단. nationwide_other_region(전국+개최지)은 약감점 surface=PASS 취급.
    return "BLOCK" if rs == "other_only" else "PASS"


def _mon_verdict(item, city, dist=""):
    g = {"applicant_region_city": city, "applicant_region_label": city,
         "applicant_districts": [dist] if dist else []}
    rs = mon.classify_region_for_group(item, g)["region_status"]
    return "BLOCK" if rs == "not_eligible" else "PASS"


def test_company_match_monitor_region_parity():
    """두 경로가 같은 공고·같은 기업지역에 같은 PASS/BLOCK 을 내야 한다."""
    mismatches = []
    for city in OWN_CITIES:
        dist = "남동구" if city == "인천" else ""
        for name, item in CASES:
            cmv = _cm_verdict(item, city, dist)
            monv = _mon_verdict(item, city, dist)
            if cmv != monv:
                mismatches.append(f"[{name}] own={city}: company_match={cmv} != monitor={monv}")
    assert not mismatches, "지역 verdict 비대칭:\n  " + "\n  ".join(mismatches)
