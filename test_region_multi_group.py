"""지역별 그룹 공통 지역 로직 회귀 테스트 — monitor.classify_region_for_group.

classify_region_for_group 은 group 인자를 받는 '모든 그룹 공통' 로직이다. 따라서 특정
지역(인천)만이 아니라 서울·인천·경기·부산·대구·충북 각각을 own 으로 놓고, 자기지역 통과 /
타지역 차단 / 전국 통과 / 수도권 family 를 지키는지 매트릭스로 검증한다.

회귀: '[대구] 전국 박람회(대구 소재 한정)' 같은 공고가 '전국' 한 단어로 제목[지역]태그·
신청한정 차단을 우회하던 빈틈(2026-06-29 수정, PR #112)이 모든 지역에서 막혔는지 확인.
네트워크/SMTP 없음 (self-contained).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402


def _grp(label, city, dists=None):
    return {"applicant_region_city": city, "applicant_region_label": label,
            "applicant_districts": dists or [], "extra_eligible_regions": []}


OWNS = {
    "서울": _grp("서울", "서울특별시"),
    "인천": _grp("인천", "인천광역시", ["남동구"]),
    "경기": _grp("경기", "경기도"),
    "부산": _grp("부산", "부산광역시"),
    "대구": _grp("대구", "대구광역시"),
    "충북": _grp("충북", "충청북도"),
}
METRO = {"서울", "인천", "경기"}


def _verdict(item, g):
    return "BLOCK" if m.classify_region_for_group(item, g)["region_status"] == "not_eligible" else "PASS"


def _assert_matrix(item, expected_fn, label):
    for own, g in OWNS.items():
        got = _verdict(item, g)
        exp = expected_fn(own)
        assert got == exp, f"[{label}] own={own}: 기대 {exp} != 실제 {got}"


def test_daegu_nationwide_restricted_blocked_except_daegu():
    """★빈틈: '[대구] 전국 박람회 + 대구 소재 한정' → 대구 그룹만 통과, 나머지 전 지역 차단."""
    item = {"title": "[대구] 전국 식품박람회",
            "description": "전국 식품제조업체 대상. 대구광역시 소재 기업만 신청 가능."}
    _assert_matrix(item, lambda o: "PASS" if o == "대구" else "BLOCK", "대구전국한정")


def test_true_nationwide_all_groups_pass():
    """진짜 전국공고(신청 지역 제한 없음)는 모든 지역 그룹에 통과(recall 보존)."""
    item = {"title": "전국 중소제조 수출바우처", "description": "전국 중소기업 대상 수출 지원."}
    _assert_matrix(item, lambda o: "PASS", "진짜전국")


def test_busan_only_passes_busan():
    item = {"title": "부산 전용 물류비", "description": "부산광역시 소재 기업만 신청."}
    _assert_matrix(item, lambda o: "PASS" if o == "부산" else "BLOCK", "부산전용")


def test_seoul_only_passes_seoul():
    item = {"title": "서울 창업지원", "description": "서울특별시 소재 기업만 신청."}
    _assert_matrix(item, lambda o: "PASS" if o == "서울" else "BLOCK", "서울한정")


def test_sudogwon_family_only():
    """'수도권 소재' 공고는 수도권 family(서울·인천·경기)만 통과, 비수도권 광역은 차단."""
    item = {"title": "수도권 제조 지원", "description": "수도권 소재 제조기업 대상."}
    _assert_matrix(item, lambda o: "PASS" if o in METRO else "BLOCK", "수도권공동")
