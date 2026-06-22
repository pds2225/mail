"""
monitor.py v6 파이프라인 테스트 (실제 API/이메일 호출 없음)
테스트 항목: ① 중복제거 ② 날짜필터 ③ 지역필터 ④ 키워드필터 ⑤ 지원유형 분류
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 환경변수 mock (실제 키 불필요) — monitor 임포트 전에 설정
os.environ.setdefault("BIZINFO_API_KEY",    "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY",  "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS",      "test@test.com")

from monitor import (
    dedup_items, date_filter, filter_for_group,
    classify_support_type, normalize_title,
    fetch_html_generic, fetch_semas_loan_ols, fetch_mssmiv, extract_date_from_text,
    extract_application_period, resolve_item_deadline, classify_region,
    previous_business_day, mail_topic, KST, ALL_SUPPORT_TYPES,
    evaluate_notice, filter_for_group_with_diagnostics, render_excluded_summary,
    classify_deadline_status,
)

# ── 테스트용 mock 공고 ────────────────────────────────────────────
previous_workday = previous_business_day().strftime("%Y-%m-%d")
today     = datetime.now(KST).strftime("%Y-%m-%d")

MOCK_ITEMS = [
    # [A] 기업마당(통합) + K-Startup(주관) 동일 공고 → K-Startup 유지
    {
        "id": "bizinfo_001",
        "title": "2026년 뷰티산업 육성 지원 사업 뷰티 디자인 개발 과제 참여기업 모집",
        "link": "https://bizinfo.go.kr/001", "author": "중소벤처기업부",
        "description": "뷰티 디자인 개발 사업화 지원금 바우처",
        "deadline": "2026-04-17", "source": "기업마당",
        "posted_date": previous_workday, "is_aggregator": True,
    },
    {
        "id": "kstartup_176993",
        "title": "2026년 뷰티산업 육성 지원 사업 「뷰티 디자인 개발 과제」참여기업 모집",
        "link": "https://k-startup.go.kr/176993", "author": "중소벤처기업부",
        "description": "뷰티 디자인 개발 사업화 지원",
        "deadline": "2026-04-17", "source": "K-Startup",
        "posted_date": previous_workday, "is_aggregator": False,
    },
    # [B] 인천 화장품 수출바우처 → 인천 그룹 매칭
    {
        "id": "nipa_001",
        "title": "2026년 인천 화장품 수출바우처 지원사업",
        "link": "https://nipa.kr/001", "author": "인천테크노파크",
        "description": "인천 소재 화장품 제조업체 수출바우처 지원",
        "deadline": "2099-05-30", "source": "NIPA",
        "posted_date": previous_workday, "is_aggregator": False,
    },
    # [C] 경남 로봇 전시회 → 인천 그룹 제외 (타지역)
    {
        "id": "bizinfo_002",
        "title": "2026 경남 로봇 해외전시회 참가지원",
        "link": "https://bizinfo.go.kr/002", "author": "경남테크노파크",
        "description": "경남 소재 로봇기업 해외전시회 참가비 지원",
        "deadline": "2026-04-20", "source": "기업마당",
        "posted_date": previous_workday, "is_aggregator": True,
    },
    # [D] 날짜 없음 (날짜불명) → 포함 처리
    {
        "id": "myfair_001",
        "title": "K-뷰티 해외박람회 참가 지원",
        "link": "https://myfair.co/001", "author": "KOTRA",
        "description": "K-뷰티 기업 해외박람회 참가비 바우처",
        "deadline": "2099-06-30", "source": "마이페어",
        "posted_date": "",  # 날짜불명
        "is_aggregator": True,
    },
    # [E] 오늘 올라온 공고 → D-1 필터로 제외
    {
        "id": "bizinfo_003",
        "title": "오늘 올라온 수출 컨설팅 지원사업",
        "link": "https://bizinfo.go.kr/003", "author": "중진공",
        "description": "수출 기업 컨설팅 멘토링 지원",
        "deadline": "2026-05-01", "source": "기업마당",
        "posted_date": today,  # 오늘 → D-1 필터로 제외
        "is_aggregator": True,
    },
    # [F] 전국 화장품 수출지원 → 인천 그룹 포함 (전국)
    {
        "id": "kotra_001",
        "title": "전국 화장품 수출지원 참여기업 모집",
        "link": "https://kotra.or.kr/001", "author": "KOTRA",
        "description": "전국 화장품 제조기업 수출 마케팅 지원",
        "deadline": "2099-05-15", "source": "KOTRA",
        "posted_date": previous_workday, "is_aggregator": False,
    },
]

TEST_GROUP = {
    "id": "grp_test",
    "name": "인천 화장품 수출팀",
    "active": True,
    "regions": ["인천"],
    "keywords": {"logic": "OR", "keywords": ["화장품", "뷰티", "K-뷰티", "해외전시회", "수출"]},
    "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
    "recipients": ["test@example.com"],
}


# ── pytest 테스트 함수 ────────────────────────────────────────────

def test_dedup_keeps_primary_source():
    """중복제거: 주관기관(K-Startup) 버전 유지, 기업마당 중복 제거"""
    deduped = dedup_items(MOCK_ITEMS)
    assert any(it["id"] == "kstartup_176993" for it in deduped), \
        "주관기관(K-Startup) 버전이 유지되어야 함"
    assert all(it["id"] != "bizinfo_001" for it in deduped), \
        "기업마당 집계처 중복이 제거되어야 함"


def test_dedup_reduces_count():
    """중복제거: 전체 건수가 줄어야 함"""
    deduped = dedup_items(MOCK_ITEMS)
    assert len(deduped) < len(MOCK_ITEMS), \
        f"중복제거 후 건수({len(deduped)})가 원본({len(MOCK_ITEMS)})보다 적어야 함"


def test_date_filter_excludes_today():
    """날짜필터(D-1): 오늘 등록 공고는 matched/unknown 어디에도 없어야 함"""
    deduped = dedup_items(MOCK_ITEMS)
    matched, unknown = date_filter(deduped, days_back=1)
    all_results = matched + unknown
    assert all(it["id"] != "bizinfo_003" for it in all_results), \
        "오늘 등록 공고(bizinfo_003)는 날짜필터로 제외되어야 함"


def test_date_filter_includes_unknown():
    """날짜필터: 날짜불명(posted_date='') 공고는 unknown에 포함되어야 함"""
    deduped = dedup_items(MOCK_ITEMS)
    matched, unknown = date_filter(deduped, days_back=1)
    assert any(it["id"] == "myfair_001" for it in unknown), \
        "날짜불명 공고(myfair_001)는 unknown 목록에 포함되어야 함"


def test_group_filter_excludes_other_region():
    """그룹 지역 필터: 타지역(경남) 공고는 제외"""
    deduped = dedup_items(MOCK_ITEMS)
    matched, unknown = date_filter(deduped, days_back=1)
    g_items = filter_for_group(matched + unknown, TEST_GROUP)
    assert all(it["id"] != "bizinfo_002" for it in g_items), \
        "경남 공고(bizinfo_002)는 인천 그룹에서 제외되어야 함"


def test_group_filter_includes_target_region():
    """그룹 지역 필터: 지정 지역(인천) 공고는 포함"""
    deduped = dedup_items(MOCK_ITEMS)
    matched, unknown = date_filter(deduped, days_back=1)
    g_items = filter_for_group(matched + unknown, TEST_GROUP)
    assert any(it["id"] == "nipa_001" for it in g_items), \
        "인천 화장품 공고(nipa_001)가 그룹 필터에 포함되어야 함"


def test_group_filter_includes_nationwide():
    """그룹 지역 필터: 특정 지역이 없는 전국 공고는 포함"""
    deduped = dedup_items(MOCK_ITEMS)
    matched, unknown = date_filter(deduped, days_back=1)
    g_items = filter_for_group(matched + unknown, TEST_GROUP)
    assert any(it["id"] == "kotra_001" for it in g_items), \
        "전국 대상 공고(kotra_001)가 그룹 필터에 포함되어야 함"


def test_classify_support_type_voucher():
    """지원유형 분류: 바우처/지원금 키워드"""
    result = classify_support_type({"title": "수출바우처 지원", "description": ""})
    assert "지원금/바우처" in result, f"'지원금/바우처' 분류 실패: {result}"


def test_classify_support_type_consulting():
    """지원유형 분류: 컨설팅·교육·상담 키워드"""
    result = classify_support_type({"title": "컨설팅 멘토링 세미나", "description": ""})
    assert "컨설팅·교육·상담" in result, f"'컨설팅·교육·상담' 분류 실패: {result}"


def test_classify_support_type_investment():
    """지원유형 분류: 투자 키워드"""
    result = classify_support_type({"title": "VC 투자 엔젤투자", "description": ""})
    assert "투자" in result, f"'투자' 분류 실패: {result}"


def test_classify_support_type_other():
    """지원유형 분류: 미해당 → 그외"""
    result = classify_support_type({"title": "해외진출 협력 네트워크", "description": ""})
    assert "그외" in result, f"'그외' 분류 실패: {result}"


def test_extract_date_from_text_supports_korean_date():
    """날짜 추출: 2026년 5월 9일 같은 한국어 날짜도 YYYY-MM-DD로 정규화"""
    assert extract_date_from_text("등록일 2026년 5월 9일") == "2026-05-09"


def test_previous_business_day_skips_weekend():
    """직전영업일 계산: 월요일 실행 시 금요일 공고를 기준으로 삼음."""
    monday = datetime(2026, 5, 25, 9, 0, tzinfo=KST)
    assert previous_business_day(monday).isoformat() == "2026-05-22"


def test_fetch_html_generic_uses_configured_date_selectors(monkeypatch):
    """공통 HTML 파서: sites.json의 날짜 selector가 있으면 그 값을 우선 사용"""
    from bs4 import BeautifulSoup
    import monitor

    html = """
    <table>
      <tbody>
        <tr>
          <td class="title"><a href="/notice/1">K-뷰티 해외진출 지원</a></td>
          <td class="posted">2026.05.15</td>
          <td class="deadline">2026년 6월 1일</td>
          <td class="author">한국보건산업진흥원</td>
        </tr>
      </tbody>
    </table>
    """
    monkeypatch.setattr(monitor, "_soup", lambda url: BeautifulSoup(html, "html.parser"))

    site = {
        "id": "khidi_test",
        "name": "KHIDI 테스트",
        "url": "https://example.com/list",
        "is_aggregator": False,
        "selectors": {
            "row": "table tbody tr",
            "title": ".title a",
            "link": ".title a",
            "date": ".posted",
            "deadline": ".deadline",
            "author": ".author",
        },
    }

    items = fetch_html_generic(site)

    assert len(items) == 1
    assert items[0]["title"] == "K-뷰티 해외진출 지원"
    assert items[0]["link"] == "https://example.com/notice/1"
    assert items[0]["posted_date"] == "2026-05-15"
    assert items[0]["deadline"] == "2026-06-01"
    assert items[0]["author"] == "한국보건산업진흥원"


def test_fetch_html_generic_accepts_top_level_date_selector(monkeypatch):
    """공통 HTML 파서: 설계 문서의 date_selector 필드명도 그대로 지원"""
    from bs4 import BeautifulSoup
    import monitor

    html = """
    <ul>
      <li>
        <a href="view.aspx?id=1">예술분야 기초창업 지원사업</a>
        <span class="posted">2026/05/15</span>
      </li>
    </ul>
    """
    monkeypatch.setattr(monitor, "_soup", lambda url: BeautifulSoup(html, "html.parser"))

    site = {
        "id": "kams_test",
        "name": "KAMS 테스트",
        "url": "https://example.com/notice_list.aspx",
        "date_selector": ".posted",
        "selectors": {"row": "ul li"},
    }

    items = fetch_html_generic(site)

    assert len(items) == 1
    assert items[0]["posted_date"] == "2026-05-15"


def test_fetch_html_generic_builds_detail_link_from_onclick(monkeypatch):
    """공통 HTML 파서: javascript 링크도 onclick 인자와 template으로 상세 URL을 합성"""
    from bs4 import BeautifulSoup
    import monitor

    html = """
    <table>
      <tbody>
        <tr>
          <td class="title">
            <a href="javascript:void(0)" onclick="showNotice('2026062201')">해외전시회 개별참가 지원사업</a>
          </td>
          <td class="posted">2026-06-22</td>
        </tr>
      </tbody>
    </table>
    """
    monkeypatch.setattr(monitor, "_soup", lambda url: BeautifulSoup(html, "html.parser"))

    site = {
        "id": "onclick_test",
        "name": "onclick 테스트",
        "url": "https://example.com/board/list",
        "selectors": {
            "row": "table tbody tr",
            "title": ".title a",
            "link": ".title a",
            "date": ".posted",
            "link_template": "/board/view?id={0}",
            "link_arg_re": r"showNotice\('(\d+)'\)",
        },
    }

    items = fetch_html_generic(site)

    assert len(items) == 1
    assert items[0]["title"] == "해외전시회 개별참가 지원사업"
    assert items[0]["link"] == "https://example.com/board/view?id=2026062201"
    assert items[0]["posted_date"] == "2026-06-22"


def test_fetch_html_generic_builds_detail_link_from_data_id(monkeypatch):
    """공통 HTML 파서: href 없는 목록 링크도 data-id와 template으로 상세 URL을 합성"""
    from bs4 import BeautifulSoup
    import monitor

    html = """
    <ul>
      <li>
        <a data-notice-id="abc-123">화장품 수출바우처 참여기업 모집</a>
        <span class="posted">2026.06.20</span>
      </li>
    </ul>
    """
    monkeypatch.setattr(monitor, "_soup", lambda url: BeautifulSoup(html, "html.parser"))

    site = {
        "id": "data_id_test",
        "name": "data-id 테스트",
        "url": "https://example.org/support/list",
        "selectors": {
            "row": "ul li",
            "link": "a",
            "date": ".posted",
            "link_template": "detail/{0}",
            "link_id_attr": "data-notice-id",
        },
    }

    items = fetch_html_generic(site)

    assert len(items) == 1
    assert items[0]["title"] == "화장품 수출바우처 참여기업 모집"
    assert items[0]["link"] == "https://example.org/support/detail/abc-123"
    assert items[0]["posted_date"] == "2026-06-20"


def test_fetch_mssmiv_extracts_deadline_when_list_has_two_dates(monkeypatch):
    """중소기업혁신바우처: 목록 td에 등록일+마감일 2개면 마지막을 접수마감으로."""
    from bs4 import BeautifulSoup
    import monitor

    html = """
    <table>
      <tbody>
        <tr>
          <td><a onclick="goDetail(985)">2026년 중소기업 혁신바우처 운영기관 모집 공고</a></td>
          <td>2026-06-08</td>
          <td>2026-06-30</td>
        </tr>
      </tbody>
    </table>
    """
    monkeypatch.setattr(monitor, "_soup", lambda url: BeautifulSoup(html, "html.parser"))

    site = {"name": "중소기업 혁신바우처(MSSMIV)",
            "url": "https://www.mssmiv.com/portal/board/BoardList?bbsId=1"}
    items = fetch_mssmiv(site)

    assert len(items) == 1
    assert items[0]["posted_date"] == "2026-06-08"
    assert items[0]["deadline"] == "2026-06-30"


def test_fetch_mssmiv_leaves_deadline_empty_when_only_one_date(monkeypatch):
    """중소기업혁신바우처: 목록에 날짜가 등록일 1개뿐이면 마감일은 빈 문자열."""
    from bs4 import BeautifulSoup
    import monitor

    html = """
    <table>
      <tbody>
        <tr>
          <td><a onclick="goDetail(964)">중소기업 혁신바우처 운영기관 안내</a></td>
          <td>2026-02-13</td>
        </tr>
      </tbody>
    </table>
    """
    monkeypatch.setattr(monitor, "_soup", lambda url: BeautifulSoup(html, "html.parser"))

    site = {"name": "중소기업 혁신바우처(MSSMIV)",
            "url": "https://www.mssmiv.com/portal/board/BoardList?bbsId=1"}
    items = fetch_mssmiv(site)

    assert len(items) == 1
    assert items[0]["posted_date"] == "2026-02-13"
    assert items[0]["deadline"] == ""


def test_semas_loan_ols_site_registered_as_active_dedicated_fetcher():
    """소진공 정책자금 온라인신청은 전용 수집기로 기존 메일링에 합류."""
    sites = json.loads(Path("sites.json").read_text(encoding="utf-8"))
    by_id = {site["id"]: site for site in sites}

    assert "semas" in by_id, "기존 semas 항목은 유지되어야 함"
    assert "semas_loan_ols" in by_id, "신규 소진공 정책자금 사이트가 등록되어야 함"

    site = by_id["semas_loan_ols"]
    assert site["url"] == "https://ols.semas.or.kr/ols/man/SMAN051M/page.do"
    assert site["type"] == "semas_loan_ols"
    assert site["selectors"]["row"] == "table tbody tr"
    assert site["enabled"] is True
    assert "AJAX POST" in site["note"]


def test_fetch_semas_loan_ols_maps_ajax_results(monkeypatch):
    """소진공 정책자금 AJAX 응답을 기존 공고 item 스키마로 변환."""
    import monitor

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": [
                    {
                        "bltwtrTitNm": "2026년 5월 재도전특별자금 신청안내",
                        "bltwtrSeq": 371,
                        "bbsTypeCd": "01",
                        "loanSeCdNm": "직접대출",
                        "bltwtrClcd": "대출정보",
                        "frstRegDt": "2026-05-08",
                    },
                    {
                        "bltwtrTitNm": "『AI+ OpenData 챌린지』 참여기업 모집공고",
                        "bltwtrSeq": 372,
                        "bbsTypeCd": "01",
                        "loanSeCdNm": "직접대출",
                        "bltwtrClcd": "기타",
                        "frstRegDt": "2026-05-11",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers", {})

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, data):
            calls.append((url, data, self.headers))
            return FakeResponse()

    monkeypatch.setattr(monitor.httpx, "Client", FakeClient)
    site = {
        "id": "semas_loan_ols",
        "name": "소진공 정책자금 온라인신청",
        "url": "https://ols.semas.or.kr/ols/man/SMAN051M/page.do",
        "is_aggregator": False,
        "max_pages": 1,
    }

    items = fetch_semas_loan_ols(site)

    assert len(items) == 1
    assert items[0]["id"] == "semas_loan_ols_371_01"
    assert items[0]["title"] == "2026년 5월 재도전특별자금 신청안내"
    assert items[0]["link"] == site["url"]
    assert items[0]["author"] == "소상공인시장진흥공단"
    assert items[0]["posted_date"] == "2026-05-08"
    assert "대출구분: 직접대출" in items[0]["description"]
    assert calls[0][0] == "https://ols.semas.or.kr/ols/man/SMAN051M/search.do"
    assert calls[0][1]["pageNo"] == "1"
    assert calls[0][2]["X-Requested-With"] == "XMLHttpRequest"


def test_mail_topic_uses_semas_policy_fund_title_for_semas_only():
    """소진공 정책자금 단독 메일은 전용 제목을 사용."""
    assert mail_topic([{"source": "소진공 정책자금 온라인신청"}]) == "소상공인 정책자금 공고"


FILTER_TODAY = datetime(2026, 5, 27, tzinfo=KST).date()
FUTURE_DEADLINE = "2099.6.1 ~ 2099.6.30"
PAST_DEADLINE = "2020.1.1 ~ 2020.1.31"

POLICY_GROUP = {
    "id": "policy",
    "name": "인천 남동구 제조 수출팀",
    "active": True,
    "required_conditions": {"regions": ["인천"]},
    "or_keywords": [
        "모집", "지원", "수출", "해외", "글로벌", "박람회", "전시회",
        "베트남", "동남아", "소상공인", "지원금", "혁신바우처", "수출바우처",
        "공장", "스마트", "제조", "공정개선", "공정자동화", "설비개선", "신청접수",
    ],
    "and_keyword_groups": [],
    "exclude_keywords": [],
    "support_types": ALL_SUPPORT_TYPES,
}


def notice(title, description="전국 중소기업 대상 신청접수", deadline=FUTURE_DEADLINE):
    return {
        "id": normalize_title(title)[:20],
        "title": title,
        "link": "https://example.com/notice",
        "author": "테스트기관",
        "description": description,
        "deadline": deadline,
        "source": "테스트",
        "posted_date": previous_workday,
        "is_aggregator": False,
    }


def evaluated(title, description="전국 중소기업 대상 신청접수", deadline=FUTURE_DEADLINE):
    return evaluate_notice(notice(title, description, deadline), POLICY_GROUP, FILTER_TODAY)


def test_extract_date_from_text_supports_short_year_and_month_day_deadline():
    assert extract_date_from_text("'26.5.13(수) 18시") == "2026-05-13"
    assert extract_date_from_text("~ 5.13(수) 18시까지") == "2026-05-13"


def test_extract_application_period_prefers_application_over_agreement():
    sample = (
        "ㅇ 협약기간 : '26년 1월 1일 ~ '26년 11월 30일\n"
        "ㅇ 신청기간 : 26년 1월 27일(화) ~ 2월 09일(월) 18시까지"
    )
    period = extract_application_period(sample)
    assert period["start"] == "2026-01-27"
    assert period["end"] == "2026-02-09"
    assert period["display"] == "2026-01-27 ~ 2026-02-09"


def test_resolve_item_deadline_ignores_agreement_period_in_body():
    item = {
        "title": "2026 경기 수출 기회 바우처 지원사업 모집공고",
        "description": "ㅇ 협약기간 : 2026-01-01 ~ 2026-11-30",
        "deadline": "2026-01-01 ~ 2026-11-30",
    }
    item["description"] += (
        "\nㅇ 신청기간 : 26년 1월 27일(화) ~ 2월 09일(월) 18시까지"
    )
    assert resolve_item_deadline(item) == "2026-01-27 ~ 2026-02-09"


def test_classify_region_excludes_gyeonggi_and_busan_targets():
    gyeonggi = classify_region({
        "title": "2026 경기 수출 기회 바우처 지원사업 모집공고",
        "description": "지원대상 : 본사 또는 공장 소재지가 경기도인 중소 제조 기업",
    })
    assert gyeonggi["region_status"] == "not_eligible"

    busan = classify_region({
        "title": "뿌리산업 BIZ 플랫폼 지원 기업 모집",
        "region_field": "부산광역시",
        "description": "공고일 기준 부산 소재 기업",
    })
    assert busan["region_status"] == "not_eligible"


def test_evaluate_excludes_gyeonggi_voucher_for_incheon_group():
    item = {
        "id": "exportvoucher_test",
        "title": "2026 경기 수출 기회 바우처 지원사업 모집공고",
        "description": (
            "지원대상 : 경기도 소재 중소 제조 기업 신청접수\n"
            "ㅇ 신청기간 : 26년 1월 27일(화) ~ 2월 09일(월) 18시까지"
        ),
        "deadline": "2026-01-27 ~ 2026-02-09",
        "link": "https://www.exportvoucher.com/portal/board/boardView?ntt_id=1",
        "author": "KOTRA 경기지원본부",
        "source": "수출바우처",
        "posted_date": "2026-01-28",
        "is_aggregator": False,
    }
    result = evaluate_notice(item, POLICY_GROUP, FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "REGION_NOT_ELIGIBLE" in result["exclude_reason_codes"]


def test_evaluate_excludes_busan_kstartup_for_incheon_group():
    item = {
        "id": "kstartup_177831",
        "title": "뿌리산업 BIZ 플랫폼 지원 기업 모집",
        "description": "공고일 기준 부산 소재 기업 신청접수",
        "region_field": "부산광역시",
        "deadline": "2026-04-30",
        "link": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=177831",
        "author": "한국로봇융합연구원",
        "source": "K-Startup",
        "posted_date": "2026-01-28",
        "is_aggregator": False,
    }
    result = evaluate_notice(item, POLICY_GROUP, FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "REGION_NOT_ELIGIBLE" in result["exclude_reason_codes"]


def test_filter_excludes_admin_guideline_education_supplier_selected_and_info_cases():
    cases = [
        ("국고보조금 부정수급 관련 정부 지침 강화 안내", "GUIDELINE_OR_MANUAL"),
        ("2026년 중소기업 혁신 바우처사업 컨설팅분야 수행 관련 안내&유의사항", "GUIDELINE_OR_MANUAL"),
        ("'26년 혁신바우처사업 관리지침 및 운영지침", "GUIDELINE_OR_MANUAL"),
        ("공동인증서 용도별 종류 및 사용 안내", "GUIDELINE_OR_MANUAL"),
        ("2026년 중소기업 혁신바우처 사업 분야별 교육 일정", "EDUCATION_ONLY"),
        ("산재예방요율제 안내", "NOT_GRANT_NOTICE"),
        ("혁신바우처사업 수요기반 공급기업 추가모집안내", "SUPPLIER_ONLY"),
        ("선금신청 매뉴얼 및 제출 서류 안내", "GUIDELINE_OR_MANUAL"),
        ("재기컨설팅 사업 관리지침 개정안내", "GUIDELINE_OR_MANUAL"),
        ("접수기간이 과거인 지원계획 공고", "CLOSED_DEADLINE", PAST_DEADLINE),
        ("수도권 소재 기업 신청 불가 지원사업 공고", "REGION_NOT_ELIGIBLE"),
        ("수출지원 설명회 단독 안내", "INFO_SESSION"),
        ("멘토링 단독 공고", "LOW_PRIORITY_SERVICE_KEYWORD"),
        ("컨설팅지원 단독 공고", "LOW_PRIORITY_SERVICE_KEYWORD"),
    ]
    for case in cases:
        title, expected_code, *deadline = case
        result = evaluated(title, deadline=deadline[0] if deadline else FUTURE_DEADLINE)
        assert result["is_relevant"] is False, title
        assert expected_code in result["exclude_reason_codes"], result


def test_filter_allows_application_notices_with_general_keywords_and_scores_them():
    cases = [
        "인천 소재 중소기업 신청 가능 지원사업 공고",
        "전국 중소기업 대상 수출지원 공고",
        "화장품/뷰티 해외전시회 참가기업 모집",
        "베트남 수출상담회 참가기업 모집",
        "동남아 박람회 참가기업 모집",
        "글로벌 전시회 참가 지원사업",
        "소상공인 지원금 신청 공고",
        "접수 예정 공고",
    ]
    for title in cases:
        result = evaluated(title)
        assert result["is_relevant"] is True, result
        assert result["relevance_score"] > 0
        assert result["exclude_reason_codes"] == []


def test_priority_keywords_promote_only_real_open_application_notices():
    priority_cases = [
        "접수 중인 수출바우처 참여기업 모집",
        "접수 중인 혁신바우처 수요기업 모집",
    ]
    for title in priority_cases:
        result = evaluated(title)
        assert result["is_relevant"] is True, result
        assert result["priority_keyword"] is True
        assert result["priority_keywords"]


def test_priority_keyword_regressions_do_not_override_hard_exclusions():
    cases = [
        ("혁신바우처 관리지침 안내", "GUIDELINE_OR_MANUAL"),
        ("혁신바우처 교육일정 안내", "EDUCATION_ONLY"),
        ("혁신바우처 공급기업 추가모집 안내", "SUPPLIER_ONLY"),
        ("수출바우처 설명회 개최 안내", "INFO_SESSION"),
    ]
    for title, expected_code in cases:
        result = evaluated(title)
        assert result["priority_keyword"] is True
        assert result["is_relevant"] is False
        assert expected_code in result["exclude_reason_codes"], result


def test_priority_keyword_regressions_allow_demand_company_applications():
    innovation = evaluated("혁신바우처 수요기업 모집", "인천 남동구 소재 중소기업 신청접수")
    export = evaluated("수출바우처 참여기업 모집", "전국 중소기업 대상 신청접수")

    assert innovation["is_relevant"] is True
    assert innovation["priority_keyword"] is True
    assert innovation["district_status"] == "eligible"
    assert export["is_relevant"] is True
    assert export["priority_keyword"] is True
    assert export["region_status"] == "eligible"


def test_district_filter_excludes_specific_incheon_districts_not_including_namdong():
    cases = [
        ("인천 서구 소재 중소기업 스마트공장 지원사업", "DISTRICT_NOT_ELIGIBLE"),
        ("인천 부평구 소상공인 지원금 신청 공고", "DISTRICT_NOT_ELIGIBLE"),
        ("남동구 제외 인천 제조기업 공정개선 지원사업", "DISTRICT_NOT_ELIGIBLE"),
    ]
    for title, expected_code in cases:
        result = evaluated(title)
        assert result["is_relevant"] is False
        assert result["district_status"] == "not_eligible"
        assert expected_code in result["exclude_reason_codes"], result


def test_factory_and_smart_keywords_are_scored_but_do_not_override_info_exclusions():
    info_session = evaluated("스마트공장 설명회 개최 안내")
    education = evaluated("스마트공장 교육 일정 안내")
    complex_only = evaluated("특정 산업단지 입주기업 전용 제조혁신 지원사업")

    assert info_session["is_relevant"] is False
    assert "INFO_SESSION" in info_session["exclude_reason_codes"]
    assert "SMART_FACTORY_INFO_ONLY" in info_session["exclude_reason_codes"]
    assert education["is_relevant"] is False
    assert "EDUCATION_ONLY" in education["exclude_reason_codes"]
    assert "SMART_FACTORY_INFO_ONLY" in education["exclude_reason_codes"]
    assert complex_only["is_relevant"] is False
    assert "ONLY_SPECIFIC_INDUSTRIAL_COMPLEX" in complex_only["exclude_reason_codes"]


def test_factory_and_smart_application_cases_pass_or_become_priority():
    cases = [
        ("인천광역시 소재 제조기업 스마트공장 구축 지원사업", "인천광역시 소재 제조기업 신청접수"),
        ("인천 남동구 제조기업 공정자동화 지원사업", "인천 남동구 제조기업 신청접수"),
        ("전국 제조기업 스마트팩토리 구축 지원사업", "전국 제조기업 신청접수"),
        ("공장등록증 보유 제조기업 대상 수출바우처 참여기업 모집", "전국 제조기업 신청접수"),
        ("공장 보유 소상공인 대상 설비개선 지원금 신청 공고", "인천광역시 소재 소상공인 신청접수"),
    ]
    for title, description in cases:
        result = evaluated(title, description)
        assert result["is_relevant"] is True, result
        assert result["factory_condition"] is True
        assert result["relevance_score"] > 0
    voucher = evaluated("공장등록증 보유 제조기업 대상 수출바우처 참여기업 모집")
    assert voucher["priority_keyword"] is True
    assert voucher["factory_required"] is True
    assert "공장보유 또는 제조시설 조건" in voucher["required_conditions"]


def test_filter_for_group_diagnostics_returns_excluded_summary_for_dry_run():
    items = [
        notice("수출바우처 참여기업 모집", "전국 중소기업 대상 신청접수"),
        notice("혁신바우처 관리지침 안내", "전국 중소기업 대상"),
        notice("인천 서구 소재 중소기업 스마트공장 지원사업", "인천 서구 소재 기업만 신청접수"),
    ]
    diagnostics = filter_for_group_with_diagnostics(items, POLICY_GROUP, FILTER_TODAY)
    summary = render_excluded_summary(diagnostics["excluded"])

    assert [it["title"] for it in diagnostics["included"]] == ["수출바우처 참여기업 모집"]
    assert "GUIDELINE_OR_MANUAL" in summary
    assert "DISTRICT_NOT_ELIGIBLE" in summary


# ── DebouncedCallback 동시 실행 격리 테스트 ────────────────────────────────────
def test_debounced_callback_serialises_concurrent_fires():
    """
    두 타이머 스레드가 동시에 _fire()를 호출해도 callback이 겹치지 않아야 한다.

    수정 전: _exec_lock 없음 → 두 callback 동시 실행 가능 → 중복 Sheets 행 기록
    수정 후: _exec_lock 으로 직렬화 → 두 번째 fire는 첫 번째 완료 후 실행
    """
    import threading
    from customer_intake.inbox_watch import DebouncedCallback

    overlap_detected = threading.Event()
    inside = threading.Event()
    call_count = [0]
    lock = threading.Lock()

    def slow_callback():
        # Mark entry and check for overlap
        with lock:
            call_count[0] += 1
            if inside.is_set():
                overlap_detected.set()
            inside.set()
        try:
            threading.Event().wait(timeout=0.1)  # simulate slow work
        finally:
            inside.clear()

    # Use a zero-delay debounce to make two fires easy to trigger
    debounced = DebouncedCallback(delay_sec=0, callback=slow_callback)

    # Trigger two fires in rapid succession
    t1 = threading.Thread(target=debounced._fire)
    t2 = threading.Thread(target=debounced._fire)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not overlap_detected.is_set(), (
        "두 _fire() 호출이 동시에 callback을 실행했습니다 — 중복 처리 버그"
    )
    assert call_count[0] == 2, "두 fire 모두 실행되어야 합니다 (직렬화, 누락 아님)"


# ── 작업 A·C: 키워드 보강 회귀 테스트 ──────────────────────────────────────────

def test_open_deadline_terms_new_items_positive():
    """OPEN_DEADLINE_TERMS 신규: 상시모집·연중수시가 title/description에 있으면 'open'"""
    assert classify_deadline_status(
        {"title": "OO사업 상시모집 안내", "description": "", "deadline": ""},
        FILTER_TODAY,
    ) == "open"
    assert classify_deadline_status(
        {"title": "OO 연중수시 모집", "description": "", "deadline": ""},
        FILTER_TODAY,
    ) == "open"
    assert classify_deadline_status(
        {"title": "OO 모집", "description": "연중수시 접수", "deadline": ""},
        FILTER_TODAY,
    ) == "open"
    # 단독 '상시'는 추가하지 않음 — '상시 근로자 5인 이상 기업'은 여전히 open이 아님
    assert classify_deadline_status(
        {"title": "상시 근로자 5인 이상 기업", "description": "", "deadline": ""},
        FILTER_TODAY,
    ) != "open"


def test_application_keywords_positive_chamgasinjung():
    """'참가신청' APPLICATION_KEYWORDS 추가 → region-eligible 본문에서 is_relevant=True"""
    result = evaluate_notice(
        notice("OO 참가신청 공고", description="인천 소재 중소 제조 기업 수출"),
        POLICY_GROUP,
        FILTER_TODAY,
    )
    assert result["is_relevant"] is True
    assert result["exclude_reason_codes"] == []


def test_application_keywords_positive_gongmo():
    """'공모' APPLICATION_KEYWORDS 추가 → region-eligible 본문에서 is_relevant=True"""
    result = evaluate_notice(
        notice("OO 공모 공고", description="인천 소재 중소 제조 기업 수출"),
        POLICY_GROUP,
        FILTER_TODAY,
    )
    assert result["is_relevant"] is True
    assert result["exclude_reason_codes"] == []


def test_negative_gate_guard_ungyongjiwongonggo_excluded():
    """'지원공고' 미추가 잠금: '운영지원공고'는 여전히 NOT_GRANT_NOTICE로 제외.
    region/group은 통과(인천 소재, '지원' in or_keywords), application 게이트만 막힘.
    '지원공고'를 APPLICATION_KEYWORDS에 추가하면 is_relevant=True로 뒤집혀 이 테스트가 red."""
    item = notice(title="운영지원공고", description="인천 소재 중소기업")
    result = evaluate_notice(item, POLICY_GROUP, FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "NOT_GRANT_NOTICE" in result["exclude_reason_codes"]
    # '지원' in or_keywords → group_keyword_pass=True(통과) — application 게이트만 차단
    assert "지원" in POLICY_GROUP["or_keywords"]


def test_membership_assertions():
    """키워드 리스트 멤버십: 단독 일반어·미승인어는 없고, 승인 신규어는 있음"""
    import monitor
    assert "모집" not in monitor.APPLICATION_KEYWORDS
    assert "접수" not in monitor.APPLICATION_KEYWORDS
    assert "지원공고" not in monitor.APPLICATION_KEYWORDS
    assert "상시" not in monitor.OPEN_DEADLINE_TERMS
    assert "공모" in monitor.APPLICATION_KEYWORDS
    assert "참가신청" in monitor.APPLICATION_KEYWORDS
    assert "상시모집" in monitor.OPEN_DEADLINE_TERMS
    assert "연중수시" in monitor.OPEN_DEADLINE_TERMS


def test_gongmo_known_overtriggering_cost():
    # 의도된 과탐 비용 — 비지원 '청년 사진 공모전'이 region/group eligible이면
    # '공모' substring이 NOT_GRANT_NOTICE 게이트를 열음(2345-2346).
    # '공모' 채택의 알려진·수용된 부작용.
    # 후속 경계매칭 PR에서 이 단언을 is False로 뒤집어 제거할 것.
    item = notice(title="청년 사진 공모전", description="인천 소재 중소 제조 기업 수출")
    result = evaluate_notice(item, POLICY_GROUP, FILTER_TODAY)
    assert result["is_relevant"] is True
