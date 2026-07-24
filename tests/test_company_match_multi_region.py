"""company_match 지역별 기업 공통 매칭 회귀 — compute_match_score (모든 기업 공통 로직).

compute_match_score(item, company) 는 company.region.city 로 판정하는 '모든 기업 공통' 로직이다.
서울·인천·경기·부산·대구·충북 각 own 기업 × 5케이스 매트릭스로, monitor.test_region_multi_group 과
대칭되게 검증한다. 네트워크/SMTP 없음 (self-contained).

회귀:
- ★'수도권 소재' 공고가 비수도권 기업(부산·대구·충북)에 적격으로 새던 빈틈 (2026-06-29 수정)
- '[대구] 전국(대구 소재 한정)' 이 '전국' 한 단어로 차단 우회하던 빈틈 (PR #111)
"""
from __future__ import annotations

from mail_core.matching import company_match as cm


def _comp(city, dist=""):
    return cm._normalize_company({
        "id": "t", "email": cm.TEST_RECIPIENT, "active": True,
        "region": {"city": city, "district": dist},
        "industry_keywords": ["제조", "제조업", "식품"],
        "interest_keywords": ["수출", "박람회", "제조", "판로"],
        "exclude_keywords": [], "match_threshold": 50,
    })


OWNS = {
    "서울": _comp("서울"),
    "인천": _comp("인천", "남동구"),
    "경기": _comp("경기"),
    "부산": _comp("부산"),
    "대구": _comp("대구"),
    "충북": _comp("충북"),
}
METRO = {"서울", "인천", "경기"}


def _verdict(item, c):
    rs = cm.compute_match_score(item, c)["breakdown"]["region_status"]
    return "BLOCK" if rs in ("other_only", "nationwide_other_region") else "PASS"


def _assert_matrix(item, exp_fn, label):
    for own, c in OWNS.items():
        got = _verdict(item, c)
        exp = exp_fn(own)
        assert got == exp, f"[{label}] own={own}: 기대 {exp} != 실제 {got}"


def test_daegu_nationwide_restricted_blocked_except_daegu():
    item = {"title": "[대구] 전국 식품박람회",
            "description": "전국 식품제조업체 대상. 대구광역시 소재 기업만 신청 가능."}
    _assert_matrix(item, lambda o: "PASS" if o == "대구" else "BLOCK", "대구전국한정")


def test_true_nationwide_all_pass():
    item = {"title": "전국 중소제조 수출바우처", "description": "전국 중소기업 대상 수출 지원."}
    _assert_matrix(item, lambda o: "PASS", "진짜전국")


def test_busan_only_passes_busan():
    item = {"title": "부산 전용 물류비", "description": "부산광역시 소재 기업만 신청."}
    _assert_matrix(item, lambda o: "PASS" if o == "부산" else "BLOCK", "부산전용")


def test_seoul_only_passes_seoul():
    item = {"title": "서울 창업지원", "description": "서울특별시 소재 기업만 신청."}
    _assert_matrix(item, lambda o: "PASS" if o == "서울" else "BLOCK", "서울한정")


def test_sudogwon_only_metro_family():
    """★빈틈 회귀: '수도권 소재' 공고는 수도권 family(서울·인천·경기)만 통과, 비수도권 차단."""
    item = {"title": "수도권 제조 지원", "description": "수도권 소재 제조기업 대상."}
    _assert_matrix(item, lambda o: "PASS" if o in METRO else "BLOCK", "수도권공동")


def test_region_cluster_members_only():
    """★권역 일반화 회귀(2026-06-29): 수도권만이 아니라 경상/호남/충청/강원권 한정 공고도
    그 권역 멤버 기업만 통과하고 비멤버는 차단한다."""
    cluster = {
        "수도권": {"서울", "인천", "경기"},
        "경상권": {"부산", "대구"},
        "호남권": {"광주"},
        "충청권": {"충북"},
        "강원권": {"강원"},
    }
    owns = dict(OWNS)
    owns["광주"] = _comp("광주")
    owns["강원"] = _comp("강원")
    for kwon, members in cluster.items():
        item = {"title": f"{kwon} 제조 지원", "description": f"{kwon} 소재 제조기업 대상."}
        for own, c in owns.items():
            exp = "PASS" if own in members else "BLOCK"
            got = _verdict(item, c)
            assert got == exp, f"[{kwon}] own={own}: 기대 {exp} != 실제 {got}"
