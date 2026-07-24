"""2026-07-24 '예비창업 AI (전국·서울강조)' 발송사고 회귀 테스트.

실측된 오발송 5유형을 고정한다:
  ① 완전연도 날짜("2025. 7. 22.")의 M.D 부분을 축약패턴이 현재연도로 재파싱해
     만료 공고 신청기간이 미래(2026-08-05)로 부풀어 closed→open 오판 (EMA 방산 건)
  ② 워치리스트 키워드가 본문 우연일치로 만료·행정 공고를 날짜필터 우회 강제포함
     (EMA '지식재산', 이노비즈 사기예방 건)
  ③ 위원(사람) 위촉 모집공고가 기업 지원공고로 발송 (경남TP 기획위원 건)
  ④ 보도자료가 추천공고로 발송 + 목록행 요약·제공일자가 제목에 통째로 유입
     (인천시청 펜타포트 건)
  ⑤ 사무·보육 공간 입주기업 모집에 '공장보유 필요' 오표기 (서울 AI 허브 건)
"""
import datetime as dt
import os

os.environ.setdefault("BIZINFO_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GMAIL_ADDRESS", "test@example.invalid")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test")

import monitor

TODAY = dt.date(2026, 7, 24)

GROUP = {
    "id": "grp_prestartup_ai",
    "name": "예비창업 AI (전국·서울강조)",
    "required_conditions": {},
    "applicant_region_city": "서울특별시",
    "applicant_region_label": "서울",
    "or_keywords": ["AI", "인공지능", "생성형AI", "빅데이터", "데이터"],
    "and_keyword_groups": [],
    "exclude_keywords": [],
    "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
    "extra_eligible_regions": ["인천", "경기", "수도권"],
}


# ── ① 날짜 파서 이중매칭(가짜 연도) ─────────────────────────────────────────

def test_full_year_date_not_reparsed_as_current_year():
    """"2025. 7. 22.(화)" 내부의 "7. 22." 를 현재연도 날짜로 다시 만들지 않는다."""
    dates = [d for _, d in monitor._parse_date_candidates(
        "모집기간 : 2025. 7. 22.(화) ~ 2025. 8. 5.(화)", base_year=2026)]
    assert dt.date(2025, 7, 22) in dates
    assert dt.date(2025, 8, 5) in dates
    assert dt.date(2026, 7, 22) not in dates
    assert dt.date(2026, 8, 5) not in dates


def test_application_period_expired_year_not_inflated():
    period = monitor.extract_application_period("모집기간 : 2025. 7. 22.(화) ~ 2025. 8. 5.(화)")
    assert period["start"] == "2025-07-22"
    assert period["end"] == "2025-08-05"


def test_expired_notice_classified_closed():
    """EMA 방산 건: 2025년 신청기간이 지난 공고는 closed(발송 제외)여야 한다."""
    item = {
        "title": "2026년도 인천시 방산 중소기업 생산성향상 지원사업 수혜 후보기업 모집 공고",
        "description": "신청 기간 : 2025.07.22(화) 00:00 ~ 2025.08.05(화) 18:00 "
                       "모집기간 : 2025. 7. 22.(화) ~ 2025. 8. 5.(화)",
        "posted_date": "2025-07-22",
    }
    assert monitor.classify_deadline_status(item, today=TODAY) == "closed"
    result = monitor.evaluate_notice(item, GROUP, today=TODAY)
    assert result["is_relevant"] is False
    assert "CLOSED_DEADLINE" in result["exclude_reason_codes"]


def test_shortform_period_uses_segment_year():
    """혼합 표기 "2025.07.22 ~ 8.5" 의 축약일도 구간의 완전연도(2025)를 따른다."""
    dates = monitor._parse_period_dates("2025.07.22 ~ 8.5")
    assert dates[0] == dt.date(2025, 7, 22)
    assert dates[-1] == dt.date(2025, 8, 5)


def test_standalone_shortform_dates_still_parsed():
    """회귀 방지: 축약 단독 표기(연도 단서 없음)는 기존처럼 base_year 로 파싱된다."""
    dates = [d for _, d in monitor._parse_date_candidates("접수 7.22 마감", base_year=2026)]
    assert dates == [dt.date(2026, 7, 22)]


# ── ② 워치리스트 본문 우연일치 강제포함 ─────────────────────────────────────

WL = {"keywords": ["지식재산"], "urls": [], "recipients": []}


def test_watchlist_keyword_matches_title():
    assert monitor.is_watchlisted({"title": "2026 지식재산 활용 지원사업 공고"}, WL) is True


def test_watchlist_keyword_ignores_body_only_mention():
    """상세보강된 긴 본문의 우연일치('신청제외: 지식재산권 분쟁기업')로 강제포함하지 않는다."""
    item = {
        "title": "방산 중소기업 생산성향상 지원사업 모집 공고",
        "description": "신청제외 대상: 지식재산권 분쟁 중인 기업",
        "author": "",
    }
    assert monitor.is_watchlisted(item, WL) is False


def test_watchlist_keyword_matches_author():
    assert monitor.is_watchlisted(
        {"title": "지원사업 공고", "author": "지식재산처"}, WL) is True


# ── ③ 위원 위촉 모집 ────────────────────────────────────────────────────────

def test_committee_recruitment_excluded():
    item = {
        "title": "AI기반 종단간 미래자동차 E2E 고속자율주행 고성능 특화플랫폼 검증 기반구축 "
                 "기획위원(후보자) 모집공고",
        "description": "기획위원 모집. 신청기간: 2026-07-23 ~ 2026-08-10",
        "posted_date": "2026-07-23",
    }
    result = monitor.evaluate_notice(item, GROUP, today=TODAY)
    assert result["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in result["exclude_reason_codes"]
    assert "위원 모집" in result["excluded_keywords"]


def test_committee_variants_excluded():
    for title in ("2026년 평가위원 위촉 공고", "심사위원 공개모집", "자문위원 후보자 모집"):
        assert monitor.non_grant_title_reason({"title": title}) == "위원 모집", title


def test_committee_word_in_company_notice_not_excluded():
    """'위원회'·참여기업 모집은 위원 위촉이 아니다 — 진짜 지원공고를 막지 않는다."""
    for title in (
        "운영위원회 심의를 거친 2026 AI 참여기업 모집",
        "AI 스타트업 지원사업 참여기업 모집 공고",
    ):
        assert monitor.non_grant_title_reason({"title": title}) == "", title


# ── ④ 보도자료 ──────────────────────────────────────────────────────────────

def test_press_release_title_excluded():
    item = {
        "title": "[보도자료] 인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화(GEO) 도입",
        "description": "생성형 인공지능 검색 환경 홍보 혁신. 해외 관광객 접근성 강화.",
        "posted_date": "2026-07-23",
    }
    result = monitor.evaluate_notice(item, GROUP, today=TODAY)
    assert result["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in result["exclude_reason_codes"]


def test_press_release_row_marker_excluded():
    """목록행 요약이 제목에 섞여 '제공일자 … 제공부서'가 남은 경우도 잡는다."""
    title = ("인천 펜타포트, 세계 음악축제 최초 생성형 인공지능 최적화(GEO) 도입 "
             "문화체육관광부가 선정 제공일자 2026-07-23 제공부서 예술정책과")
    assert monitor.non_grant_title_reason({"title": title}) == "보도자료"


def test_press_release_announcing_recruitment_not_excluded():
    """모집을 알리는 보도자료는 guard 로 살린다(recall)."""
    assert monitor.non_grant_title_reason(
        {"title": "[보도자료] 인천시, AI 스타트업 입주기업 모집 시작"}) == ""


# ── ⑤ 사기·피싱 예방 행정 안내 ──────────────────────────────────────────────

def test_fraud_prevention_notice_excluded():
    item = {
        "title": "수요기관 임직원 사칭 허위구매 사기피해 예방 안내",
        "description": "해외 무역업체로 위장한 사기 사례 및 대응방법 안내. 데이터 참고.",
        "posted_date": "2026-06-25",
    }
    assert monitor.non_grant_title_reason(item) == "피해예방 안내"
    result = monitor.evaluate_notice(item, GROUP, today=TODAY)
    assert result["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in result["exclude_reason_codes"]


def test_fraud_education_recruitment_not_excluded():
    assert monitor.non_grant_title_reason(
        {"title": "사기피해 예방 교육 수강생 모집"}) == ""


# ── ⑥ 입주기업 공장요건 오표기 ──────────────────────────────────────────────

def test_office_tenant_recruitment_not_factory_required():
    item = {
        "title": "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내",
        "description": "시설ㆍ공간ㆍ보육",
        "deadline": "2026-07-22 ~ 2026-08-11",
        "posted_date": "2026-07-23",
    }
    result = monitor.evaluate_notice(item, GROUP, today=TODAY)
    assert result["is_relevant"] is True
    assert result["factory_required"] is False
    assert "공장 보유 여부 확인 필요" not in result["notes"]


def test_industrial_complex_tenant_still_factory_required():
    item = {
        "title": "산업단지 입주기업 대상 스마트공장 구축 지원사업 모집",
        "description": "남동구 산업단지 입주기업의 공정개선 지원. 신청기간: 2026-07-20 ~ 2026-08-20",
        "posted_date": "2026-07-23",
    }
    result = monitor.evaluate_notice(item, GROUP, today=TODAY)
    assert result["factory_required"] is True
