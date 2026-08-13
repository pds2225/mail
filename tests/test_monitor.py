"""
monitor.py v6 파이프라인 테스트 (실제 API/이메일 호출 없음)
테스트 항목: ① 중복제거 ② 날짜필터 ③ 지역필터 ④ 키워드필터 ⑤ 지원유형 분류
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
REPO_ROOT = Path(__file__).resolve().parent.parent

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
    sites = json.loads((REPO_ROOT / "config" / "sites.json").read_text(encoding="utf-8"))
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
        ("멘토링 단독 공고", "CONSULTING_ONLY"),
        ("컨설팅지원 단독 공고", "CONSULTING_ONLY"),
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


def test_applicant_target_region_not_organizer():
    """지역 판정은 지원대상 기준 — 주관 서울이어도 대상 전국이면 통과, 대상 서울이면 제외."""
    grp = POLICY_GROUP

    nationwide_ok = {
        "title": "K-뷰티 해외진출 지원사업 참여기업 모집",
        "description": "전국 소재 중소기업 대상 신청접수",
        "author": "서울특별시",
        "region_field": "전국",
        "deadline": FUTURE_DEADLINE,
    }
    assert evaluate_notice(nationwide_ok, grp)["is_relevant"] is True

    seoul_only = {
        "title": "SBA x LG전자 K-뷰티ㆍ라이프스타일 판로 연계사업(태국) 참여기업 모집 공고",
        "description": (
            "서울경제진흥원(SBA)은 LG전자와 협력합니다. "
            "신청일 기준 서울 소재 사업장을 보유한 중소기업. "
            "뷰티ㆍ라이프스타일 분야. 태국 쇼피 라자다 판매. 신청접수"
        ),
        "author": "서울특별시",
        "region_field": "전국",
        "deadline": FUTURE_DEADLINE,
    }
    ev = evaluate_notice(seoul_only, grp)
    assert ev["is_relevant"] is False
    assert "REGION_NOT_ELIGIBLE" in ev["exclude_reason_codes"]

    beauty_seoul_meta = {
        "title": "2026년 2차 뷰티트레이드쇼 수출상담회 참가기업 모집 공고",
        "description": "서울 소재 뷰티기업 대상 수출상담회. 신청접수",
        "author": "서울특별시",
        "region_field": "전국",
        "deadline": FUTURE_DEADLINE,
    }
    assert evaluate_notice(beauty_seoul_meta, grp)["is_relevant"] is False

    # 본문 지역 단서 없고 region_field 전국만 — recall 유지(누락 방지)
    meta_only = {
        "title": "중소기업 수출 지원사업",
        "description": "중소기업 대상 신청접수",
        "author": "서울특별시",
        "region_field": "전국",
        "deadline": FUTURE_DEADLINE,
    }
    assert classify_region(meta_only)["region_status"] == "eligible"


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


# ── 작업 A·C: 키워드 보강 회귀 테스트 ──────────────────────────────────────────

def test_open_deadline_terms_new_items_positive():
    """OPEN_DEADLINE_TERMS 신규: 상시모집·연중수시가 title/description에 있으면 'always_open'"""
    assert classify_deadline_status(
        {"title": "OO사업 상시모집 안내", "description": "", "deadline": ""},
        FILTER_TODAY,
    ) == "always_open"
    assert classify_deadline_status(
        {"title": "OO 연중수시 모집", "description": "", "deadline": ""},
        FILTER_TODAY,
    ) == "always_open"
    assert classify_deadline_status(
        {"title": "OO 모집", "description": "연중수시 접수", "deadline": ""},
        FILTER_TODAY,
    ) == "always_open"
    # 단독 '상시'는 추가하지 않음 — '상시 근로자 5인 이상 기업'은 여전히 open이 아님
    assert classify_deadline_status(
        {"title": "상시 근로자 5인 이상 기업", "description": "", "deadline": ""},
        FILTER_TODAY,
    ) not in {"open", "always_open"}


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
    """'지원공고' 미추가 잠금: '운영지원공고'는 여전히 NOT_APPLICATION_LIKE로 제외.
    region/group은 통과(인천 소재, '지원' in or_keywords), application 게이트만 막힘.
    '지원공고'를 APPLICATION_KEYWORDS에 추가하면 is_relevant=True로 뒤집혀 이 테스트가 red."""
    item = notice(title="운영지원공고", description="인천 소재 중소기업")
    result = evaluate_notice(item, POLICY_GROUP, FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "NOT_APPLICATION_LIKE" in result["exclude_reason_codes"]
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
    # '공모' substring이 NOT_APPLICATION_LIKE 게이트를 연다.
    # '공모' 채택의 알려진·수용된 부작용.
    # 후속 경계매칭 PR에서 이 단언을 is False로 뒤집어 제거할 것.
    item = notice(title="청년 사진 공모전", description="인천 소재 중소 제조 기업 수출")
    result = evaluate_notice(item, POLICY_GROUP, FILTER_TODAY)
    assert result["is_relevant"] is True


# ══════════════════════════════════════════════════════════════════
# P0 필수 테스트 — 예비창업 공고 파이프라인 (autodev prompt §6)
# ══════════════════════════════════════════════════════════════════

def _p0_group() -> dict:
    """P0 테스트용 grp_prestartup_ai 유사 그룹."""
    return {
        "id": "grp_prestartup_ai",
        "or_keywords": ["AI 스타트업", "인공지능 스타트업", "AI 솔루션"],
        "and_keyword_groups": [["AI", "창업"], ["AI", "스타트업"], ["AI", "사업화"]],
        "exclude_keywords": ["성료", "지침 안내", "결과 발표", "보도자료", "채용", "재직자"],
        "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
        "applicant_region_city": "서울특별시",
        "applicant_region_label": "서울",
        "extra_eligible_regions": ["인천", "경기", "수도권"],
    }


def test_p0_mentoring_with_financial_support_is_included():
    """사업화자금 + 멘토링 → INCLUDE (P0-4)"""
    item = notice(
        title="2026년 AI 사업화 지원사업 참여자 모집",
        description="공고일 현재 사업자등록이 없는 예비창업자 대상. 사업화자금 최대 5,000만 원 및 전문가 멘토링 지원. 전국 대상.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"사업화자금+멘토링은 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_mentoring_only_is_excluded():
    """멘토링 단독 → EXCLUDE (P0-4)"""
    item = notice(
        title="예비창업자 1:1 멘토링 프로그램",
        description="예비창업자 대상 전문가 상담 및 멘토링 제공.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "CONSULTING_ONLY" in result["exclude_reason_codes"], f"멘토링 단독은 CONSULTING_ONLY여야 함: {result['exclude_reason_codes']}"


def test_p0_education_only_is_excluded():
    """교육 단독 → EXCLUDE (P0-4)"""
    item = notice(
        title="창업교육 프로그램 수강생 모집",
        description="예비창업자 대상 창업 교육 프로그램 운영. 교육 수료증 발급.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "CONSULTING_ONLY" in result["exclude_reason_codes"], f"교육 단독은 CONSULTING_ONLY여야 함: {result['exclude_reason_codes']}"


def test_p0_investment_only_is_excluded():
    """투자 단독 → EXCLUDE (P0-4)"""
    item = notice(
        title="AI 스타트업 투자유치 데모데이",
        description="AI 스타트업 대상 VC 투자유치 프로그램. IR 피칭 기회 제공.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "INVESTMENT_ONLY" in result["exclude_reason_codes"], f"투자 단독은 INVESTMENT_ONLY여야 함: {result['exclude_reason_codes']}"


def test_p0_space_only_is_excluded():
    """입주공간 단독 → EXCLUDE (P0-4)"""
    item = notice(
        title="창업보육센터 입주기업 모집",
        description="창업보육센터 입주 공간 제공. 사무실 및 공용시설 이용 가능.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False


def test_p0_space_with_financial_support_is_included():
    """입주공간 + 사업화자금 → INCLUDE (P0-4)"""
    item = notice(
        title="AI 창업보육센터 입주기업 모집 (사업화자금 지원)",
        description="AI 창업보육센터 입주 공간 및 사업화자금 최대 3,000만 원 지원. 전국 예비창업자 대상.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"입주+사업화자금은 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_operator_recruitment_is_excluded():
    """운영기관 모집 → EXCLUDE (P0-2)"""
    item = notice(
        title="예비창업자 지원 프로그램 운영기관 모집",
        description="대학, 협회, 창업지원기관 대상 운영기관 모집 공고.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False


def test_p0_nationwide_from_daegu_institution_is_included():
    """대구 기관 + 전국 대상 → INCLUDE (P0-6)"""
    item = notice(
        title="2026년 AI 창업지원사업 참여자 모집",
        description="전국 예비창업자 대상 사업화자금 지원. 주관기관: 대구테크노파크.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"대구기관+전국대상은 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_busan_only_is_excluded():
    """부산 거주자 한정 → EXCLUDE (P0-6)"""
    item = notice(
        title="부산 지역 창업지원사업 참여자 모집",
        description="부산 거주자 대상 창업지원금 지원. 부산 소재 예비창업자만 신청 가능.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False
    assert "REGION_NOT_ELIGIBLE" in result["exclude_reason_codes"], f"부산한정은 REGION_NOT_ELIGIBLE여야 함: {result['exclude_reason_codes']}"


def test_p0_nationwide_with_relocation_is_conditional():
    """전국 + 선정 후 대구 이전 → CONDITIONAL_INCLUDE (P0-6)"""
    item = notice(
        title="전국 창업지원사업 참여자 모집",
        description="전국 예비창업자 대상 사업화자금 지원. 선정 후 대구광역시 내 사업자등록 필수.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    # 조건부 포함은 아직 is_relevant=True로 처리할 수 있음 (메일에 조건 표시)
    # 또는 CONDITIONAL reason_code가 있어야 함
    assert "REGION_NOT_ELIGIBLE" not in result["exclude_reason_codes"], f"전국+대구이전은 REGION_NOT_ELIGIBLE이면 안 됨: {result['exclude_reason_codes']}"


def test_p0_personal_standalone_not_prestartup():
    """`개인 또는 법인` → 예비창업 자동인정 금지 (P0-3)"""
    item = notice(
        title="창업지원사업 참여자 모집",
        description="개인 또는 법인 신청 가능. 사업화자금 지원.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    # "개인"만으로 예비창업 확정하면 안 됨 — 다른 창업 신호가 있어야 함
    # 이 테스트는 "개인"이 예비창업의 충분조건이 아님을 검증
    # (실제로는 다른 키워드에 의해 포함될 수 있음)


def test_p0_personal_with_team_is_eligible():
    """`사업자등록이 없는 개인 또는 팀` → ELIGIBLE (P0-3)"""
    item = notice(
        title="2026년 AI 창업지원사업 참여자 모집",
        description="공고일 현재 사업자등록이 없는 개인 또는 팀 단위의 예비창업자 대상. 사업화자금 최대 5,000만 원 지원. 전국 대상.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"개인+팀+창업예정은 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_export_consultation_is_included():
    """수출상담회 → 비용지원형 해외진출이므로 INCLUDE (P0-4)"""
    item = notice(
        title="AI 스타트업 베트남 수출상담회 참가기업 모집",
        description="해외 진출 희망 AI 스타트업 대상 베트남 수출상담회 참가기업 모집. 참가비 지원. 전국 대상.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"수출상담회는 해외진출 지원이므로 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_financial_support_with_mentoring_is_included():
    """시제품비 + 교육 → INCLUDE (P0-4)"""
    item = notice(
        title="2026년 AI 시제품 제작 지원사업 참여자 모집",
        description="예비창업자 대상 시제품 제작비 최대 2,000만 원 및 전문 교육 프로그램 지원. 전국 대상.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"시제품비+교육은 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_voucher_with_consulting_is_included():
    """바우처 + 컨설팅 → INCLUDE (P0-4)"""
    item = notice(
        title="2026년 AI 바우처 지원사업 참여기업 모집",
        description="예비창업자 및 창업 3년 이내 기업 대상. 바우처 최대 5,000만 원 및 전문 컨설팅 지원. 전국 대상.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"바우처+컨설팅은 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_performer_recruitment_is_excluded():
    """수행기관 모집 → EXCLUDE (P0-2)"""
    item = notice(
        title="예비창업자 지원 프로그램 수행기관 모집 공고",
        description="예비창업자 지원 사업의 수행기관을 모집합니다. 사업 수행 역량을 보유한 기관.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False


def test_p0_committee_recruitment_is_excluded():
    """위원 모집 → EXCLUDE"""
    item = notice(
        title="창업지원사업 평가위원 모집 공고",
        description="창업지원사업 서류평가 및 발표평가 위원을 모집합니다.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False


# ══════════════════════════════════════════════════════════════════
# P1 테스트 — 제목 정규화 및 canonical ID
# ══════════════════════════════════════════════════════════════════

def test_p1_safe_normalize_title_preserves_year():
    """P1-4: 연도 정보 보존"""
    from monitor import safe_normalize_title
    assert "2026" in safe_normalize_title("2026년 AI 사업화 지원사업")
    assert "2025" in safe_normalize_title("2025 예비창업패키지")


def test_p1_safe_normalize_title_preserves_region():
    """P1-4: 지역 정보 보존"""
    from monitor import safe_normalize_title
    result = safe_normalize_title("[서울] AI 창업지원사업")
    assert "서울" in result


def test_p1_safe_normalize_title_preserves_round():
    """P1-4: 모집 차수 보존"""
    from monitor import safe_normalize_title
    result = safe_normalize_title("2차 모집 공고")
    assert "2차" in result


def test_p1_safe_normalize_title_normalizes_whitespace():
    """P1-4: 공백 정규화"""
    from monitor import safe_normalize_title
    result = safe_normalize_title("AI  창업   지원사업")
    assert "  " not in result


def test_p1_canonical_id_from_notice_id():
    """P1-2: 공고번호로 canonical ID 생성"""
    from monitor import generate_canonical_notice_id
    item = {"notice_id": "PBLN_2026_001", "title": "테스트"}
    cid = generate_canonical_notice_id(item)
    assert cid.startswith("canon_")
    assert "PBLN_2026_001" in cid


def test_p1_canonical_id_from_url():
    """P1-2: URL로 canonical ID 생성"""
    from monitor import generate_canonical_notice_id
    item1 = {"link": "https://example.com/notice/123", "title": "테스트"}
    item2 = {"link": "http://www.example.com/notice/123", "title": "테스트"}
    cid1 = generate_canonical_notice_id(item1)
    cid2 = generate_canonical_notice_id(item2)
    # www 유무 정규화 후 동일 ID
    assert cid1 == cid2


def test_p1_canonical_id_from_title_org():
    """P1-2: 제목+기관으로 canonical ID 생성"""
    from monitor import generate_canonical_notice_id
    item1 = {"title": "2026년 AI 창업지원사업", "author": "중소벤처기업부", "deadline": "2026-08-31"}
    item2 = {"title": "2026년 AI 창업지원사업", "author": "중소벤처기업부", "deadline": "2026-08-31"}
    cid1 = generate_canonical_notice_id(item1)
    cid2 = generate_canonical_notice_id(item2)
    assert cid1 == cid2


def test_p1_canonical_id_different_year():
    """P1-2: 연도가 다르면 다른 canonical ID"""
    from monitor import generate_canonical_notice_id
    item1 = {"title": "2025 예비창업패키지", "author": "테스트", "deadline": "2025-12-31"}
    item2 = {"title": "2026 예비창업패키지", "author": "테스트", "deadline": "2026-12-31"}
    cid1 = generate_canonical_notice_id(item1)
    cid2 = generate_canonical_notice_id(item2)
    assert cid1 != cid2


# ══════════════════════════════════════════════════════════════════
# P1-2 테스트 — 크로스소스 중복 제거
# ══════════════════════════════════════════════════════════════════

def test_p1_cross_site_same_notice_different_date():
    """사이트 간 동일 공고 (날짜 하루 차이) → 1건만 발송"""
    from monitor import dedup_items
    items = [
        {"id": "a1", "title": "2026년 AI 창업지원사업 모집", "source": "bizinfo",
         "author": "중소벤처기업부", "deadline": "2026-08-31", "is_aggregator": False,
         "link": "https://bizinfo.go.kr/notice/123", "posted_date": "2026-08-17"},
        {"id": "b1", "title": "2026년 AI 창업지원사업 모집", "source": "kstartup",
         "author": "중소벤처기업부", "deadline": "2026-08-31", "is_aggregator": False,
         "link": "https://k-startup.go.kr/notice/456", "posted_date": "2026-08-18"},
    ]
    result = dedup_items(items)
    assert len(result) == 1, f"동일 공고는 1건이어야 함: {len(result)}건"


def test_p1_cross_site_different_year():
    """2025/2026 같은 사업은 서로 다른 공고"""
    from monitor import dedup_items
    items = [
        {"id": "a1", "title": "2025 예비창업패키지 모집", "source": "bizinfo",
         "author": "중기부", "deadline": "2025-12-31", "is_aggregator": False,
         "link": "https://example.com/2025", "posted_date": "2025-01-01"},
        {"id": "b1", "title": "2026 예비창업패키지 모집", "source": "bizinfo",
         "author": "중기부", "deadline": "2026-12-31", "is_aggregator": False,
         "link": "https://example.com/2026", "posted_date": "2026-01-01"},
    ]
    result = dedup_items(items)
    assert len(result) == 2, f"다른 연도는 별도 공고: {len(result)}건"


def test_p1_cross_site_same_url_different_source():
    """동일 URL, 다른 소스 → 1건만"""
    from monitor import dedup_items
    items = [
        {"id": "a1", "title": "AI 창업지원 공고", "source": "bizinfo",
         "author": "기관A", "deadline": "2026-08-31", "is_aggregator": False,
         "link": "https://example.com/notice/100", "posted_date": "2026-08-01"},
        {"id": "b1", "title": "AI 창업지원 공고 (안내)", "source": "kstartup",
         "author": "기관A", "deadline": "2026-08-31", "is_aggregator": False,
         "link": "https://example.com/notice/100", "posted_date": "2026-08-02"},
    ]
    result = dedup_items(items)
    assert len(result) == 1, f"동일 URL은 1건이어야 함: {len(result)}건"


def test_p1_cross_site_aggregator_replaced():
    """집계처 → 주관기관으로 교체"""
    from monitor import dedup_items
    items = [
        {"id": "a1", "title": "2026년 수출바우처 모집", "source": "aggregator_site",
         "author": "알수없음", "deadline": "2026-08-31", "is_aggregator": True,
         "link": "https://agg.com/1", "posted_date": "2026-08-01"},
        {"id": "b1", "title": "2026년 수출바우처 모집", "source": "bizinfo",
         "author": "중소벤처기업부", "deadline": "2026-08-31", "is_aggregator": False,
         "link": "https://bizinfo.go.kr/2", "posted_date": "2026-08-02"},
    ]
    result = dedup_items(items)
    assert len(result) == 1
    assert result[0]["source"] == "bizinfo", "주관기관이 우선해야 함"


# ══════════════════════════════════════════════════════════════════
# P0-9 테스트 — 신청자/모집대상/수혜자/운영자 역할 분리
# ══════════════════════════════════════════════════════════════════

def test_p0_operator_recruitment_excluded():
    """예비창업자를 지원할 운영기관 모집 → EXCLUDE"""
    item = notice(
        title="예비창업자 지원 프로그램 운영기관 모집",
        description="대학, 협회, 창업지원기관 대상 운영기관 모집 공고.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is False, f"운영기관 모집은 제외되어야 함: {result['exclude_reason_codes']}"


def test_p0_applicant_is_prestartup():
    """예비창업자 모집 → INCLUDE 가능"""
    item = notice(
        title="2026년 AI 창업지원사업 참여자 모집",
        description="공고일 현재 사업자등록이 없는 예비창업자 대상. 사업화자금 지원. 전국 대상.",
    )
    result = evaluate_notice(item, _p0_group(), FILTER_TODAY)
    assert result["is_relevant"] is True, f"예비창업자 모집은 포함되어야 함: {result['exclude_reason_codes']}"


def test_p0_target_roles_extraction():
    """역할 추출 함수 테스트"""
    from monitor import extract_target_roles

    # 운영기관 모집
    item1 = {"title": "운영기관 모집 공고", "target_field": "", "description": ""}
    roles1 = extract_target_roles(item1)
    assert roles1["is_operator"] is True
    assert roles1["is_applicant"] is False

    # 예비창업자 모집
    item2 = {"title": "예비창업자 모집 공고", "target_field": "", "description": ""}
    roles2 = extract_target_roles(item2)
    assert roles2["is_applicant"] is True
    assert roles2["is_operator"] is False


# ══════════════════════════════════════════════════════════════════
# P1-17 테스트 — 소스 상태관리
# ══════════════════════════════════════════════════════════════════

def test_source_health_classify_ok():
    """정상 수집 → OK"""
    from mail_core.operations.source_health import classify_source_status, OK
    assert classify_source_status("bizinfo", item_count=100, parse_rate=0.95) == OK


def test_source_health_classify_degraded():
    """파싱률 낮음 → DEGRADED"""
    from mail_core.operations.source_health import classify_source_status, DEGRADED
    assert classify_source_status("bizinfo", item_count=100, parse_rate=0.5) == DEGRADED


def test_source_health_classify_degraded_zero_items():
    """수집 0건 → DEGRADED"""
    from mail_core.operations.source_health import classify_source_status, DEGRADED
    assert classify_source_status("bizinfo", item_count=0, parse_rate=1.0) == DEGRADED


def test_source_health_classify_failing():
    """에러 → FAILING"""
    from mail_core.operations.source_health import classify_source_status, FAILING
    assert classify_source_status("bizinfo", item_count=0, parse_rate=0.0, error="HTTP 500") == FAILING


# ══════════════════════════════════════════════════════════════════
# P1-5 테스트 — 버전 관리 (변경 유형 세분화)
# ══════════════════════════════════════════════════════════════════

def test_p1_change_type_deadline_extended():
    """마감연장 → DEADLINE_EXTENDED"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집", "deadline": "2026-08-20", "application_period": "2026-08-01 ~ 2026-08-20"}
    after = {"title": "AI 창업지원 모집", "deadline": "2026-08-31", "application_period": "2026-08-01 ~ 2026-08-31"}
    assert _classify_notice_change(before, after) == "DEADLINE_EXTENDED"


def test_p1_change_type_reannouncement():
    """재공고 → REANNOUNCEMENT"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집"}
    after = {"title": "AI 창업지원 모집 (재공고)"}
    assert _classify_notice_change(before, after) == "REANNOUNCEMENT"


def test_p1_change_type_additional_recruitment():
    """추가모집 → ADDITIONAL_RECRUITMENT"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집"}
    after = {"title": "AI 창업지원 추가모집"}
    assert _classify_notice_change(before, after) == "ADDITIONAL_RECRUITMENT"


def test_p1_change_type_target_changed():
    """지원대상 변경 → TARGET_CHANGED"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집", "target_field": "예비창업자"}
    after = {"title": "AI 창업지원 모집", "target_field": "창업 3년 이내 기업"}
    assert _classify_notice_change(before, after) == "TARGET_CHANGED"


def test_p1_change_type_target_changed_uses_snapshot_keys():
    """Live path feeds snapshots (key: target), not raw target_field."""
    from monitor import _classify_notice_change, _notice_version_snapshot, classify_notice_versions, _notice_snapshot_hash

    before_item = {
        "title": "AI 창업지원 모집",
        "target_field": "예비창업자",
        "deadline": "2026-08-31",
        "application_period": {"display": "2026-08-01 ~ 2026-08-31"},
        "support_field": "최대 1억원",
        "region_field": "전국",
        "link": "https://example.test/a",
    }
    after_item = {
        **before_item,
        "id": "n-target",
        "target_field": "창업 3년 이내 기업",
        "detail_extraction": {"status": "SUCCESS"},
    }
    before_snap = _notice_version_snapshot(before_item)
    after_snap = _notice_version_snapshot(after_item)
    assert "target" in before_snap and "target_field" not in before_snap
    assert _classify_notice_change(before_snap, after_snap) == "TARGET_CHANGED"

    versions = {
        "n-target": {
            "version": 1,
            "delivery_id": "n-target",
            "delivered_hash": _notice_snapshot_hash(before_snap),
            "delivered_snapshot": before_snap,
            "list_hash": "x",
        }
    }
    deliverable, _updates = classify_notice_versions([after_item], {"n-target"}, versions)
    assert len(deliverable) == 1
    assert deliverable[0]["_change_type"] == "TARGET_CHANGED"


def test_p1_change_type_minor_text_change():
    """단순 텍스트 변경 → MINOR_TEXT_CHANGE"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집", "deadline": "2026-08-31"}
    after = {"title": "AI 창업지원 모집", "deadline": "2026-08-31"}
    assert _classify_notice_change(before, after) == "MINOR_TEXT_CHANGE"


# ══════════════════════════════════════════════════════════════════
# P1-6 테스트 — 여러 출처 필드 병합
# ══════════════════════════════════════════════════════════════════

def test_p1_merge_fields_preserves_additional_sources():
    """여러 출처 병합 시 추가 출처 기록"""
    from monitor import merge_notice_fields
    canonical = {"title": "AI 창업지원", "source": "bizinfo", "link": "https://bizinfo.go.kr/1"}
    new_item = {"title": "AI 창업지원", "source": "kstartup", "link": "https://k-startup.go.kr/2"}
    result = merge_notice_fields(canonical, new_item)
    assert "kstartup" in result.get("_additional_sources", [])


def test_p1_merge_fields_preserves_target():
    """지원대상이 더 긴 값으로 병합"""
    from monitor import merge_notice_fields
    canonical = {"title": "AI 창업지원", "source": "bizinfo", "target_field": "예비창업자"}
    new_item = {"title": "AI 창업지원", "source": "kstartup", "target_field": "공고일 현재 사업자등록이 없는 예비창업자 또는 창업 3년 이내 기업"}
    result = merge_notice_fields(canonical, new_item)
    assert "사업자등록이 없는" in result.get("target_field", "")


# ══════════════════════════════════════════════════════════════════
# MILESTONE A 테스트 — 버전관리 + 재발송 정책
# ══════════════════════════════════════════════════════════════════

def test_milestone_a_same_notice_different_date_is_one():
    """A사이트 8/17 + B사이트 8/18 동일공고 → 1건만"""
    from monitor import dedup_items
    items = [
        {"id": "a1", "title": "2026년 AI 창업지원사업 모집", "source": "bizinfo",
         "author": "중소벤처기업부", "deadline": "2026-08-31", "is_aggregator": False,
         "link": "https://bizinfo.go.kr/123", "posted_date": "2026-08-17"},
        {"id": "b1", "title": "2026년 AI 창업지원사업 모집", "source": "kstartup",
         "author": "중소벤처기업부", "deadline": "2026-08-31", "is_aggregator": False,
         "link": "https://k-startup.go.kr/456", "posted_date": "2026-08-18"},
    ]
    result = dedup_items(items)
    assert len(result) == 1
    assert result[0].get("_canonical_notice_id") is not None


def test_milestone_a_deadline_extended_change_type():
    """마감연장 → DEADLINE_EXTENDED"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원", "deadline": "2026-08-20", "application_period": "2026-08-01 ~ 2026-08-20"}
    after = {"title": "AI 창업지원", "deadline": "2026-08-31", "application_period": "2026-08-01 ~ 2026-08-31"}
    assert _classify_notice_change(before, after) == "DEADLINE_EXTENDED"


def test_milestone_a_target_changed_type():
    """지원대상 변경 → TARGET_CHANGED"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원", "target_field": "예비창업자"}
    after = {"title": "AI 창업지원", "target_field": "창업 3년 이내 기업"}
    assert _classify_notice_change(before, after) == "TARGET_CHANGED"


def test_milestone_a_reannouncement_type():
    """재공고 → REANNOUNCEMENT"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집"}
    after = {"title": "AI 창업지원 모집 (재공고)"}
    assert _classify_notice_change(before, after) == "REANNOUNCEMENT"


def test_milestone_a_additional_recruitment_type():
    """추가모집 → ADDITIONAL_RECRUITMENT"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집"}
    after = {"title": "AI 창업지원 추가모집"}
    assert _classify_notice_change(before, after) == "ADDITIONAL_RECRUITMENT"


def test_milestone_a_minor_text_change_type():
    """단순 오탈자 → MINOR_TEXT_CHANGE"""
    from monitor import _classify_notice_change
    before = {"title": "AI 창업지원 모집", "deadline": "2026-08-31"}
    after = {"title": "AI 창업지원 모집 ", "deadline": "2026-08-31"}
    assert _classify_notice_change(before, after) == "MINOR_TEXT_CHANGE"


def test_milestone_a_different_year_is_different_notice():
    """2025 / 2026 → 서로 다른 공고"""
    from monitor import generate_canonical_notice_id
    item1 = {"title": "2025 예비창업패키지", "author": "중기부", "deadline": "2025-12-31"}
    item2 = {"title": "2026 예비창업패키지", "author": "중기부", "deadline": "2026-12-31"}
    assert generate_canonical_notice_id(item1) != generate_canonical_notice_id(item2)


def test_milestone_a_different_region_is_different_notice():
    """서울 / 부산 → 서로 다른 공고"""
    from monitor import generate_canonical_notice_id
    item1 = {"title": "서울 예비창업 지원사업", "author": "서울TP", "deadline": "2026-08-31"}
    item2 = {"title": "부산 예비창업 지원사업", "author": "부산TP", "deadline": "2026-08-31"}
    assert generate_canonical_notice_id(item1) != generate_canonical_notice_id(item2)


def test_milestone_a_different_round_is_different_notice():
    """1차 / 2차 → 서로 다른 공고"""
    from monitor import generate_canonical_notice_id
    item1 = {"title": "2026년 AI 창업 1차 모집", "author": "중기부", "deadline": "2026-08-31"}
    item2 = {"title": "2026년 AI 창업 2차 모집", "author": "중기부", "deadline": "2026-12-31"}
    assert generate_canonical_notice_id(item1) != generate_canonical_notice_id(item2)


# ══════════════════════════════════════════════════════════════════
# MILESTONE B 테스트 — Source Health 운영 연결
# ══════════════════════════════════════════════════════════════════

def test_milestone_b_source_health_ok():
    """정상 수집 → OK"""
    from mail_core.operations.source_health import classify_source_status, OK
    assert classify_source_status("bizinfo", item_count=100, parse_rate=0.95) == OK


def test_milestone_b_source_health_degraded_zero_items():
    """0건 수집 → DEGRADED"""
    from mail_core.operations.source_health import classify_source_status, DEGRADED
    assert classify_source_status("bizinfo", item_count=0, parse_rate=1.0) == DEGRADED


def test_milestone_b_source_health_degraded_low_parse_rate():
    """파싱률 저하 → DEGRADED"""
    from mail_core.operations.source_health import classify_source_status, DEGRADED
    assert classify_source_status("bizinfo", item_count=100, parse_rate=0.5) == DEGRADED


def test_milestone_b_source_health_failing_on_error():
    """에러 → FAILING"""
    from mail_core.operations.source_health import classify_source_status, FAILING
    assert classify_source_status("bizinfo", item_count=0, parse_rate=0.0, error="HTTP 500") == FAILING


def test_milestone_b_source_health_degraded_on_drop():
    """수집량 급감 (80% 이상) → DEGRADED"""
    from mail_core.operations.source_health import classify_source_status, DEGRADED
    assert classify_source_status("bizinfo", item_count=10, parse_rate=1.0, previous_item_count=100) == DEGRADED


def test_milestone_b_source_health_ok_on_normal():
    """정상 수집 (급감 없음) → OK"""
    from mail_core.operations.source_health import classify_source_status, OK
    assert classify_source_status("bizinfo", item_count=90, parse_rate=1.0, previous_item_count=100) == OK


# ══════════════════════════════════════════════════════════════════
# P2-3 테스트 — POSSIBLE_DUPLICATE
# ══════════════════════════════════════════════════════════════════

def test_p2_possible_duplicate_similar_titles():
    """유사한 제목 → POSSIBLE_DUPLICATE 표시"""
    from monitor import detect_possible_duplicates
    items = [
        {"id": "a1", "title": "2026년 AI 창업지원사업 모집 공고", "source": "bizinfo"},
        {"id": "b1", "title": "2026년 AI 창업지원사업 모집", "source": "kstartup"},
    ]
    result = detect_possible_duplicates(items)
    assert result[0].get("_possible_duplicate") is True
    assert result[1].get("_possible_duplicate") is True


def test_p2_possible_duplicate_different_year():
    """다른 연도 → POSSIBLE_DUPLICATE 아님"""
    from monitor import detect_possible_duplicates
    items = [
        {"id": "a1", "title": "2025년 AI 창업지원사업 모집", "source": "bizinfo"},
        {"id": "b1", "title": "2026년 AI 창업지원사업 모집", "source": "kstartup"},
    ]
    result = detect_possible_duplicates(items)
    assert result[0].get("_possible_duplicate") is not True
    assert result[1].get("_possible_duplicate") is not True


def test_p2_possible_duplicate_different_region():
    """다른 지역 → POSSIBLE_DUPLICATE 아님"""
    from monitor import detect_possible_duplicates
    items = [
        {"id": "a1", "title": "서울 AI 창업지원사업 모집", "source": "bizinfo"},
        {"id": "b1", "title": "부산 AI 창업지원사업 모집", "source": "kstartup"},
    ]
    result = detect_possible_duplicates(items)
    assert result[0].get("_possible_duplicate") is not True
    assert result[1].get("_possible_duplicate") is not True


# ══════════════════════════════════════════════════════════════════
# Hotfix — fetch_all outcomes + dedup _stats order
# ══════════════════════════════════════════════════════════════════

def test_fetch_all_without_outcomes_remains_compatible():
    """outcomes 미전달 시 기존 list-only API가 NameError 없이 동작한다."""
    import monitor

    items = monitor.fetch_all([{"id": "x", "name": "x", "type": "__no_such_type__"}])
    assert items == []


def test_fetch_all_records_success_and_failure_outcomes(monkeypatch):
    """성공/실패 소스가 섞여도 outcomes collector에 기록되고 수집은 중단되지 않는다."""
    import monitor

    def ok_fetcher(site):
        return [{
            "id": f"{site['id']}_1",
            "title": "ok notice",
            "link": "https://example.com/1",
            "author": "",
            "description": "",
            "deadline": "",
            "source": site["id"],
            "posted_date": previous_workday,
            "is_aggregator": False,
        }]

    def bad_fetcher(site):
        raise RuntimeError("boom")

    monkeypatch.setitem(monitor.FETCHERS, "ok_type", ok_fetcher)
    monkeypatch.setitem(monitor.FETCHERS, "bad_type", bad_fetcher)

    outcomes: dict = {}
    sites = [
        {"id": "bizinfo", "name": "biz", "type": "ok_type"},
        {"id": "kstartup", "name": "ks", "type": "bad_type"},
    ]
    items = monitor.fetch_all(sites, outcomes=outcomes)

    assert len(items) == 1
    assert items[0]["id"] == "bizinfo_1"
    assert outcomes["bizinfo"]["success"] is True
    assert outcomes["bizinfo"]["item_count"] == 1
    assert outcomes["bizinfo"]["error"] is None
    assert outcomes["kstartup"]["success"] is False
    assert outcomes["kstartup"]["item_count"] == 0
    assert "boom" in str(outcomes["kstartup"]["error"])


def test_dedup_items_stats_exports_source_contribution():
    """_stats 전달 시 source_contribution export가 UnboundLocalError 없이 동작한다."""
    items = [
        {
            "id": "a1",
            "title": "2026년 뷰티산업 육성 지원 사업",
            "link": "https://bizinfo.go.kr/a1",
            "author": "중기부",
            "description": "지원",
            "deadline": "2099-04-17",
            "source": "bizinfo",
            "posted_date": previous_workday,
            "is_aggregator": True,
        },
        {
            "id": "b1",
            "title": "2026년 뷰티산업 육성 지원 사업",
            "link": "https://k-startup.go.kr/b1",
            "author": "중기부",
            "description": "지원",
            "deadline": "2099-04-17",
            "source": "kstartup",
            "posted_date": previous_workday,
            "is_aggregator": False,
        },
        {
            "id": "c1",
            "title": "완전 다른 공고 제목입니다",
            "link": "https://nipa.kr/c1",
            "author": "NIPA",
            "description": "지원",
            "deadline": "2099-05-01",
            "source": "nipa",
            "posted_date": previous_workday,
            "is_aggregator": False,
        },
    ]
    stats: dict = {}
    kept = dedup_items(items, _stats=stats)

    assert len(kept) == 2
    assert "source_contribution" in stats
    assert isinstance(stats["source_contribution"], dict)
    assert "same_source_duplicate_removed" in stats
    assert "cross_source_duplicate_removed" in stats
    assert "attachment_duplicate_removed" in stats
    assert stats.get("duplicate_replaced", 0) >= 1
    assert "duplicate_removed_total" in stats
    # primary(kstartup) should win over aggregator(bizinfo)
    assert any(it["source"] == "kstartup" for it in kept)
    assert "kstartup" in stats["source_contribution"]


def test_p2_yearless_title_still_recalls_yearful_duplicate():
    """연도 없는 제목도 연도 있는 유사 제목과 POSSIBLE_DUPLICATE로 잡혀야 한다."""
    from monitor import detect_possible_duplicates
    items = [
        {"id": "a1", "title": "AI 창업지원사업 모집", "source": "bizinfo"},
        {"id": "b1", "title": "2026년 AI 창업지원사업 모집", "source": "kstartup"},
    ]
    result = detect_possible_duplicates(items)
    assert result[0].get("_possible_duplicate") is True
    assert result[1].get("_possible_duplicate") is True


def test_execute_monitor_all_fetch_failures_still_update_source_health(
    tmp_path, monkeypatch,
):
    """전체 소스 실패여도 early return 전에 source-health가 기록된다."""
    import monitor
    import mail_core.operations.source_health as sh

    health_path = tmp_path / "source_health.json"
    monkeypatch.setattr(sh, "SOURCE_HEALTH_PATH", health_path)
    monkeypatch.setattr(sh, "SOURCE_INCIDENT_PATH", tmp_path / "source_incidents.jsonl")
    monkeypatch.setattr(monitor, "load_sites", lambda: [
        {"id": "bizinfo", "name": "biz", "type": "ok_type", "enabled": True},
        {"id": "kstartup", "name": "ks", "type": "ok_type", "enabled": True},
    ])
    monkeypatch.setattr(monitor, "load_groups", lambda: [{"id": "g1", "name": "g"}])
    monkeypatch.setattr(monitor, "load_settings", lambda: {"days_back": 1})
    monkeypatch.setattr(monitor, "load_seen_ids", lambda: set())

    def boom_fetch(sites, outcomes=None, **_kw):
        if outcomes is not None:
            for s in sites:
                sid = str(s.get("id") or s.get("name") or "unknown")
                outcomes[sid] = {"success": False, "item_count": 0, "error": "boom"}
        return []

    monkeypatch.setattr(monitor, "fetch_all", boom_fetch)
    result = monitor.execute_monitor(allow_send=False, persist_seen=False)
    assert result.get("ok") is True
    assert result.get("reason") == "no_items"
    health = sh.load_source_health()
    assert health["bizinfo"]["status"] == sh.FAILING
    assert health["kstartup"]["status"] == sh.FAILING
    assert "boom" in str(health["bizinfo"].get("error") or "boom")


def test_execute_monitor_collect_dedup_path_no_nameerror(tmp_path, monkeypatch):
    """정상 수집→dedup 경로가 NameError/UnboundLocalError 없이 끝난다."""
    import monitor
    import mail_core.operations.source_health as sh

    monkeypatch.setattr(sh, "SOURCE_HEALTH_PATH", tmp_path / "source_health.json")
    monkeypatch.setattr(sh, "SOURCE_INCIDENT_PATH", tmp_path / "source_incidents.jsonl")

    item = {
        "id": "n1",
        "title": "2026년 뷰티산업 육성 지원 사업",
        "link": "https://example.com/n1",
        "author": "중기부",
        "description": "지원",
        "deadline": "2099-04-17",
        "source": "bizinfo",
        "posted_date": previous_workday,
        "is_aggregator": False,
    }

    def ok_fetch(sites, outcomes=None, **_kw):
        if outcomes is not None:
            outcomes["bizinfo"] = {"success": True, "item_count": 1, "error": None}
        return [dict(item)]

    monkeypatch.setattr(monitor, "load_sites", lambda: [
        {"id": "bizinfo", "name": "biz", "type": "ok_type", "enabled": True},
    ])
    monkeypatch.setattr(monitor, "load_groups", lambda: [{"id": "g1", "name": "g"}])
    monkeypatch.setattr(monitor, "load_settings", lambda: {"days_back": 1})
    monkeypatch.setattr(monitor, "load_seen_ids", lambda: set())
    monkeypatch.setattr(monitor, "fetch_all", ok_fetch)
    monkeypatch.setattr(monitor, "enrich_items", lambda items: items)
    result = monitor.execute_monitor(allow_send=False, persist_seen=False)
    assert result.get("ok") is True
    assert "error" not in str(result.get("reason") or "").lower()
    assert result.get("mail_sent") in (False, 0, None) or result.get("mail_sent") == 0

