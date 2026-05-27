"""
monitor.py v6 파이프라인 테스트 (실제 API/이메일 호출 없음)
테스트 항목: ① 중복제거 ② 날짜필터 ③ 지역필터 ④ 키워드필터 ⑤ 지원유형 분류
"""
import sys
import os
from datetime import datetime, timedelta
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
    fetch_html_generic, extract_date_from_text,
    _extract_mssmiv_application_period, _mssmiv_detail,
    KST, ALL_SUPPORT_TYPES,
)

# ── 테스트용 mock 공고 ────────────────────────────────────────────
yesterday = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")
today     = datetime.now(KST).strftime("%Y-%m-%d")

MOCK_ITEMS = [
    # [A] 기업마당(통합) + K-Startup(주관) 동일 공고 → K-Startup 유지
    {
        "id": "bizinfo_001",
        "title": "2026년 뷰티산업 육성 지원 사업 뷰티 디자인 개발 과제 참여기업 모집",
        "link": "https://bizinfo.go.kr/001", "author": "중소벤처기업부",
        "description": "뷰티 디자인 개발 사업화 지원금 바우처",
        "deadline": "2026-04-17", "source": "기업마당",
        "posted_date": yesterday, "is_aggregator": True,
    },
    {
        "id": "kstartup_176993",
        "title": "2026년 뷰티산업 육성 지원 사업 「뷰티 디자인 개발 과제」참여기업 모집",
        "link": "https://k-startup.go.kr/176993", "author": "중소벤처기업부",
        "description": "뷰티 디자인 개발 사업화 지원",
        "deadline": "2026-04-17", "source": "K-Startup",
        "posted_date": yesterday, "is_aggregator": False,
    },
    # [B] 인천 화장품 수출바우처 → 인천 그룹 매칭
    {
        "id": "nipa_001",
        "title": "2026년 인천 화장품 수출바우처 지원사업",
        "link": "https://nipa.kr/001", "author": "인천테크노파크",
        "description": "인천 소재 화장품 제조업체 수출바우처 지원",
        "deadline": "2026-05-30", "source": "NIPA",
        "posted_date": yesterday, "is_aggregator": False,
    },
    # [C] 경남 로봇 전시회 → 인천 그룹 제외 (타지역)
    {
        "id": "bizinfo_002",
        "title": "2026 경남 로봇 해외전시회 참가지원",
        "link": "https://bizinfo.go.kr/002", "author": "경남테크노파크",
        "description": "경남 소재 로봇기업 해외전시회 참가비 지원",
        "deadline": "2026-04-20", "source": "기업마당",
        "posted_date": yesterday, "is_aggregator": True,
    },
    # [D] 날짜 없음 (날짜불명) → 포함 처리
    {
        "id": "myfair_001",
        "title": "K-뷰티 해외박람회 참가 지원",
        "link": "https://myfair.co/001", "author": "KOTRA",
        "description": "K-뷰티 기업 해외박람회 참가비 바우처",
        "deadline": "2026-06-30", "source": "마이페어",
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
    # [F] 전국 화장품 교육 → 인천 그룹 포함 (전국)
    {
        "id": "kotra_001",
        "title": "화장품 수출역량강화 교육",
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


def test_extract_mssmiv_application_period_from_detail_text():
    text = (
        "2026년 중소기업 혁신바우처사업 2차 지원계획을 붙임과 같이 공고합니다. "
        "□ 신청방법 : 26.2.27.(금) 10시 ~ 26.3.13(금) 18시 까지 "
        "중소기업 혁신플랫폼에서 신청 □ 사업문의 : 고객센터"
    )

    assert _extract_mssmiv_application_period(text) == (
        "신청방법 : 26.2.27.(금) 10시 ~ 26.3.13(금) 18시 까지"
    )


def test_mssmiv_detail_extracts_posted_date_and_description():
    html = """
    <table class="table view">
      <thead>
        <tr><th>
          <div class="title-top">
            <span class="tit">2026년 중소기업 혁신바우처 사업 2차 지원계획공고</span>
            <div class="writer">
              <dl><dt>작성자</dt><dd>박기둥</dd></dl>
              <dl><dt>등록일</dt><dd class="date">2026-02-27</dd></dl>
            </div>
          </div>
        </th></tr>
      </thead>
      <tbody><tr><td>
        <textarea id="nttCn">&lt;p&gt;□ 신청방법 : 26.2.27.(금) 10시 ~ 26.3.13(금) 18시 까지 신청&lt;/p&gt;</textarea>
      </td></tr></tbody>
    </table>
    """

    class DummyResponse:
        text = html

        def raise_for_status(self):
            return None

    class DummyClient:
        def post(self, *args, **kwargs):
            return DummyResponse()

    title, posted, desc = _mssmiv_detail(DummyClient(), {"bbs_id": "1"}, "971", "https://example.com")

    assert title == "2026년 중소기업 혁신바우처 사업 2차 지원계획공고"
    assert posted == "2026-02-27"
    assert "신청방법 : 26.2.27.(금) 10시 ~ 26.3.13(금) 18시 까지 신청" in desc


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
