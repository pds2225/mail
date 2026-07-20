"""feedback_suggest — O/X 골든 → 개선 제안(제안 전용) 회귀 테스트.

diagnose_notice 는 순수 함수(입력=accuracy_matrix notice 레코드 + 그룹 키워드)라
합성 레코드로 각 원인 진단이 올바른 제안을 내는지 검증한다. 자동 적용은 없다(제안만).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import feedback_suggest as fs  # noqa: E402


def _notice(fb, groups, title="2026년 인천 화장품 제조 스마트공장 지원 공고", nid="n1"):
    return {"id": nid, "title": title, "feedback": fb, "groups": groups}


GKW = {"g_ai": ["AI", "인공지능", "SaaS"], "g_incheon": ["화장품", "제조"]}


def test_region_hint_when_keyword_matched_but_region_unknown():
    """키워드 맞음 + 지역 미상 강등 → region_hint(전국/소스 힌트)."""
    n = _notice("O", {"g_incheon": {
        "is_relevant": False, "region_status": "unknown",
        "region_unknown_review": True, "reason_codes": ["REGION_UNKNOWN", "LOW_CONFIDENCE"],
    }})
    sugg = fs.diagnose_notice(n, GKW)
    kinds = [s["kind"] for s in sugg]
    assert "region_hint" in kinds
    assert sugg[0]["group"] == "g_incheon"


def test_no_suggestion_when_already_recommended():
    """O 이고 이미 추천됨 = 정상(놓침 아님) → 제안 없음."""
    n = _notice("O", {"g_incheon": {"is_relevant": True, "reason_codes": []}})
    assert fs.diagnose_notice(n, GKW) == []


def test_keyword_add_when_all_groups_missed_keyword():
    """어느 그룹도 키워드 매칭 안 됨 → keyword_add 후보 추출(범용어 제외)."""
    n = _notice(
        "O",
        {"g_ai": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]},
         "g_incheon": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
        title="2026년 그린바이오 융합 소재 실증 지원 공고",
    )
    sugg = fs.diagnose_notice(n, GKW)
    kw = [s for s in sugg if s["kind"] == "keyword_add"]
    assert kw, "키워드 후보 제안이 있어야 함"
    cands = kw[0]["candidates"]
    assert cands and all(c not in fs.GENERIC_TERMS for c in cands)
    assert "공고" not in cands and "지원" not in cands   # 범용어 제외


def test_date_window_when_keyword_matched_but_date_blocked():
    """키워드 맞음 + 날짜만 막힘 → date_window."""
    n = _notice("O", {"g_incheon": {
        "is_relevant": False, "region_status": "eligible",
        "reason_codes": ["MISSING_APPLICATION_PERIOD"],
    }})
    kinds = [s["kind"] for s in fs.diagnose_notice(n, GKW)]
    assert "date_window" in kinds


def test_exclude_relax_when_keyword_matched_but_excluded():
    """키워드 맞음 + 제외규칙만 막힘 → exclude_relax(규칙 명시)."""
    n = _notice("O", {"g_incheon": {
        "is_relevant": False, "region_status": "eligible",
        "reason_codes": ["SUPPLIER_ONLY"],
    }})
    sugg = [s for s in fs.diagnose_notice(n, GKW) if s["kind"] == "exclude_relax"]
    assert sugg and "SUPPLIER_ONLY" in sugg[0]["evidence"]


def test_hard_other_region_is_not_suggested():
    """확실한 타지역(REGION_NOT_ELIGIBLE)은 승격 대상 아님 → region_hint 제안 없음."""
    n = _notice("O", {"g_incheon": {
        "is_relevant": False, "region_status": "not_eligible",
        "reason_codes": ["REGION_NOT_ELIGIBLE"],
    }})
    assert [s for s in fs.diagnose_notice(n, GKW) if s["kind"] == "region_hint"] == []


def test_false_send_review_for_X_delivered():
    """X(무관)인데 발송됨 → false_send_review 플래그(정밀도)."""
    n = _notice("X", {"g_ai": {"is_relevant": True, "reason_codes": []}})
    sugg = fs.diagnose_notice(n, GKW)
    assert len(sugg) == 1 and sugg[0]["kind"] == "false_send_review"
    assert "g_ai" in sugg[0]["groups"]


def test_company_path_delivery_is_not_a_miss():
    """O 인데 기업 경로(company matched)로 발송됨 → 놓침 아님(제안 없음)."""
    n = {"id": "n1", "title": "인천 화장품 수출바우처 공고", "feedback": "O",
         "groups": {"g_incheon": {"is_relevant": False, "reason_codes": ["REGION_UNKNOWN"]}},
         "companies": {"cmp_bnco": {"decision": "matched", "score": 40}}}
    assert fs.diagnose_notice(n, GKW) == []


def test_company_path_false_send_flagged():
    """X 인데 기업 경로로 발송됨 → false_send_review(기업 경로 포함)."""
    n = {"id": "n2", "title": "무관 공고", "feedback": "X",
         "groups": {"g_incheon": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
         "companies": {"cmp_bnco": {"decision": "matched", "score": 33}}}
    sugg = fs.diagnose_notice(n, GKW)
    assert len(sugg) == 1 and sugg[0]["kind"] == "false_send_review"
    assert sugg[0]["companies"] == ["cmp_bnco"]


def test_full_reason_codes_keyword_miss_beyond_third():
    """reason_codes 가 잘리지 않고 전량 오면, 3번째 밖의 INDUSTRY_NOT_MATCHED 도 키워드미스로 인식.

    (accuracy_matrix 가 코드를 [:3] 로 자르던 버그의 소비측 회귀 가드 — 전량 코드 가정.)
    """
    n = _notice(
        "O",
        {"g_ai": {"is_relevant": False, "reason_codes": [
            "MISSING_APPLICATION_PERIOD", "LOW_CONFIDENCE", "NOT_GRANT_NOTICE", "INDUSTRY_NOT_MATCHED"]},
         "g_incheon": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
        title="그린바이오 실증 지원 공고",
    )
    # 모든 그룹이 키워드 미스 → region/date/exclude 제안이 아니라 keyword_add 만 나와야 한다.
    kinds = {s["kind"] for s in fs.diagnose_notice(n, GKW)}
    assert kinds == {"keyword_add"}


def test_unlabeled_notice_yields_nothing():
    """골든 라벨 없는 공고는 제안 대상 아님."""
    n = _notice("", {"g_ai": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]}})
    assert fs.diagnose_notice(n, GKW) == []


def test_no_keyword_add_when_all_groups_hard_region_blocked():
    """모든 그룹이 키워드 미스 + 확실한 타지역 → 키워드를 더해도 못 살림 → keyword_add 없음.

    (Bugbot: '키워드를 못 잡았지만 지역도 확실히 타지역'인 공고에 제목 토큰을 추천하던 오작동 가드.)
    """
    n = _notice(
        "O",
        {"g_ai": {"is_relevant": False, "region_status": "not_eligible",
                  "reason_codes": ["INDUSTRY_NOT_MATCHED", "REGION_NOT_ELIGIBLE"]},
         "g_incheon": {"is_relevant": False, "region_status": "not_eligible",
                       "reason_codes": ["INDUSTRY_NOT_MATCHED", "DISTRICT_NOT_ELIGIBLE"]}},
        title="부산 그린바이오 소재 실증 지원 공고",
    )
    assert fs.diagnose_notice(n, GKW) == []


def test_keyword_add_when_some_group_region_open():
    """일부 그룹은 지역이 열려 있으면(타지역 확정 아님) 키워드 추가로 살릴 여지 → keyword_add 유지."""
    n = _notice(
        "O",
        {"g_ai": {"is_relevant": False, "region_status": "not_eligible",
                  "reason_codes": ["INDUSTRY_NOT_MATCHED", "REGION_NOT_ELIGIBLE"]},
         "g_incheon": {"is_relevant": False, "region_status": "eligible",
                       "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
        title="그린바이오 소재 실증 지원 공고",
    )
    kinds = {s["kind"] for s in fs.diagnose_notice(n, GKW)}
    assert "keyword_add" in kinds


def test_support_type_mismatch_is_not_keyword_add():
    """키워드는 맞는데(keyword_pass=True) 지원유형 불일치로 INDUSTRY_NOT_MATCHED → support_relax.

    (Bugbot: INDUSTRY_NOT_MATCHED 를 무조건 키워드 미스로 봐 제목 토큰을 추천하던 오진단 가드.)
    """
    n = _notice("O", {"g_incheon": {
        "is_relevant": False, "region_status": "eligible", "keyword_pass": True,
        "reason_codes": ["INDUSTRY_NOT_MATCHED"],
    }})
    sugg = fs.diagnose_notice(n, GKW)
    kinds = {s["kind"] for s in sugg}
    assert kinds == {"support_relax"}
    assert "keyword_add" not in kinds


def test_keyword_pass_false_is_still_keyword_miss():
    """keyword_pass=False(진짜 키워드 게이트 실패)면 여전히 키워드 미스로 keyword_add."""
    n = _notice(
        "O",
        {"g_ai": {"is_relevant": False, "keyword_pass": False,
                  "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
        title="그린바이오 소재 실증 지원 공고",
    )
    kinds = {s["kind"] for s in fs.diagnose_notice(n, GKW)}
    assert "keyword_add" in kinds


def test_keyword_add_suppressed_when_keywords_unknown():
    """groups.json 로드 실패(keywords_known=False) → 기존 키워드 중복 방지 불가 → keyword_add 억제."""
    notices = [
        _notice("O", {"g_ai": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
                title="그린바이오 소재 실증 공고", nid="a"),
    ]
    rep = fs.build_suggestions(notices, [], keywords_known=False)
    assert rep["counts"].get("keyword_add", 0) == 0
    # 반대로 keywords_known=True(기본) 이면 후보가 나온다(회귀 대비).
    rep2 = fs.build_suggestions(notices, [{"id": "g_ai", "or_keywords": ["AI"]}])
    assert rep2["counts"].get("keyword_add", 0) >= 1


def test_build_suggestions_aggregates_and_ranks_keywords():
    """집계: 여러 놓침에서 반복되는 키워드 후보가 빈도순 상위에 온다."""
    notices = [
        _notice("O", {"g_ai": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
                title="그린바이오 소재 실증 공고", nid="a"),
        _notice("O", {"g_ai": {"is_relevant": False, "reason_codes": ["INDUSTRY_NOT_MATCHED"]}},
                title="그린바이오 스케일업 지원 공고", nid="b"),
    ]
    groups = [{"id": "g_ai", "or_keywords": ["AI"]}]
    rep = fs.build_suggestions(notices, groups)
    assert rep["counts"].get("keyword_add", 0) >= 1
    top = dict(rep["top_keyword_candidates"])
    assert top.get("그린바이오", 0) >= 2      # 두 놓침에 공통 → 빈도 2
    assert "제안 전용" in rep["note"]
