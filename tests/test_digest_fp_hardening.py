"""2026-07-24 그룹 digest 오발송(예비창업 AI) 실사고 회귀 테스트.

실제 발송된 메일에서 확인된 결함 5종을 고정한다:
  ① 연도 포함 날짜의 꼬리('2025. 7. 22.'의 ' 7. 22')를 연도 생략 패턴이 재매칭해
     실행연도로 오인 → 작년 마감 공고가 '모집중(open)'으로 판정돼 우선 추천 1번에 올랐다.
  ② 워치리스트 키워드가 상세 보강된 6KB 본문의 우연 문자열('한국지식재산보호원')에
     걸려, 날짜필터로 제외된 옛 공고가 그룹 digest 로 강제 유입됐다.
  ③ '기획위원(후보자) 모집공고'(개인 전문가 위촉)가 기업 지원사업으로 발송됐다.
  ④ 목록 앵커의 아이콘 텍스트('file'·'새로운게시글')가 제목에 붙은 채 발송됐다.
     K-Startup 카드의 span.list[0] 이 제목 복제/사업분류일 때 지원기관이 오표기됐다.
  ⑤ '입주기업'(AI허브 입주 모집)만으로 '공장보유 필요'가 오표시됐다.
"""
import datetime
import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup  # noqa: E402

import monitor as m  # noqa: E402

TODAY = datetime.date(2026, 7, 24)


# ── ① 연도 포함 날짜 꼬리 재매칭 ────────────────────────────────────────────────

def test_parse_date_candidates_no_yearless_rematch_inside_yearful():
    """'2025. 7. 22.(화) ~ 2025. 8. 5.(화)' 에서 2026년 후보가 생기면 안 된다."""
    dates = [d for _, d in m._parse_date_candidates("2025. 7. 22.(화) ~ 2025. 8. 5.(화)")]
    assert dates == [datetime.date(2025, 7, 22), datetime.date(2025, 8, 5)]


def test_parse_date_candidates_standalone_short_dates_still_parse():
    """겹치지 않는 진짜 연도 생략 표기(M.D)는 계속 파싱된다(recall 유지)."""
    dates = [d for _, d in m._parse_date_candidates("접수: 7.28 ~ 8.15", base_year=2026)]
    assert datetime.date(2026, 7, 28) in dates and datetime.date(2026, 8, 15) in dates


def test_last_year_notice_classified_closed():
    """작년 모집기간 공고(인천TP 방산 실사례 축약)는 closed 로 판정돼야 한다."""
    item = {
        "title": "[인천테크노파크]2026년도 방산 중소기업 생산성향상 지원사업 수혜 후보기업 모집 공고",
        "description": "모집기간 2025. 7. 22.(화) ~ 2025. 8. 5.(화) 신청서 접수",
        "posted_date": "2025-07-22",
    }
    assert m.classify_deadline_status(item, today=TODAY) == "closed"
    ev = m.evaluate_notice(item, {"name": "g"}, today=TODAY)
    assert "CLOSED_DEADLINE" in ev["exclude_reason_codes"]
    assert ev["is_relevant"] is False


# ── ② 워치리스트 키워드는 제목·기관만 본다 ─────────────────────────────────────

_WL = {"keywords": ["지식재산"], "urls": [], "recipients": []}


def test_watchlist_ignores_enriched_body():
    """본문 깊숙한 우연 문자열('한국지식재산보호원')로는 강제포함되지 않는다."""
    item = {
        "title": "수요기관 임직원 사칭 허위구매 사기피해 예방 안내",
        "author": "이노비즈협회",
        "description": "피해기관 목록 … 한국지식재산보호원, 부산대학교병원 …",
    }
    assert m.is_watchlisted(item, _WL) is False


def test_watchlist_still_matches_title_and_author():
    assert m.is_watchlisted({"title": "2026 지식재산 활용 지원사업 공고"}, _WL) is True
    assert m.is_watchlisted({"title": "x", "author": "지식재산처"}, _WL) is True


# ── ③ 위원(개인 전문가) 위촉·모집 공고 제외 ────────────────────────────────────

def test_committee_recruitment_excluded_by_title():
    item = {
        "title": "AI기반 미래자동차 검증 기반구축 기획위원(후보자) 모집공고",
        "description": "신청접수 안내",
        "posted_date": "2026-07-23",
    }
    ev = m.evaluate_notice(item, {"name": "g"}, today=TODAY)
    assert "COMMITTEE_RECRUITMENT" in ev["exclude_reason_codes"]
    assert ev["is_relevant"] is False
    assert ev["review_needed"] is False


def test_committee_mention_in_body_does_not_block_real_notice():
    """본문의 '평가위원회 심의' 우연 언급으로 진짜 지원공고를 막지 않는다(제목 앵커)."""
    item = {
        "title": "2026년 수출바우처 지원사업 참여기업 모집공고",
        "description": "선정은 평가위원회 심의를 거쳐 확정. 신청접수 2026.07.20 ~ 2026.08.20",
        "posted_date": "2026-07-23",
    }
    ev = m.evaluate_notice(item, None, today=TODAY)
    assert "COMMITTEE_RECRUITMENT" not in ev["exclude_reason_codes"]


def test_report_junk_covers_committee_titles():
    assert m.is_report_junk({"title": "스마트제조 고도화 기획위원 모집"}) is True


# ── ④ 제목 아이콘 텍스트 제거 + K-Startup 지원기관 선택 ────────────────────────

def test_strip_title_badges():
    assert m.strip_title_badges("모집 공고 file") == "모집 공고"
    assert m.strip_title_badges("2026년 2차 서울 AI 허브 신규 입주기업 모집 안내 새로운게시글") == \
        "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내"
    assert m.strip_title_badges("이미지 없음 지원사업 공고") == "지원사업 공고"
    # 오탐 방지: 제목 중간/의미 있는 꼬리는 건드리지 않는다
    assert m.strip_title_badges("파일 관리 시스템 구축 지원") == "파일 관리 시스템 구축 지원"


_KS_CARD = """
<ul>
 <li class="notice">
  <span class="flag day">D-19</span>
  <span class="flag">시설ㆍ공간ㆍ보육</span>
  <a href="/web/contents/bizpbanc-ongoing.do?pbancSn=178661">
    2026년 2차 서울 AI 허브 신규 입주기업 모집 안내 <span>새로운게시글</span></a>
  <button type="button" onclick="goView('178661');">상세</button>
  <span class="list">2026년 2차 서울 AI 허브 신규 입주기업 모집 안내</span>
  <span class="list">서울대학교산학협력단(서울 AI 허브)</span>
  <span class="list">등록일자 2026-07-23</span>
  <span class="list">시작일자 2026-07-22</span>
  <span class="list">마감일자 2026-08-11</span>
  <span class="list">조회 1,086</span>
 </li>
</ul>
"""


def test_kstartup_org_is_last_span_before_labels():
    soup = BeautifulSoup(_KS_CARD, "html.parser")
    items = m._kstartup_cards_from_soup(
        soup, "PBC010", {"url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do",
                         "name": "K-Startup", "is_aggregator": False}, set())
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내"   # 배지 제거
    assert it["author"] == "서울대학교산학협력단(서울 AI 허브)"               # 제목 복제 span 건너뜀
    assert it["deadline"] == "2026-08-11"
    assert it["posted_date"] == "2026-07-23"


# ── ⑤ '입주기업' 단독으로 공장보유 필요 오표시 금지 ────────────────────────────

def test_ai_hub_move_in_notice_not_factory_required():
    ev = m.evaluate_notice({
        "title": "2026년 2차 서울 AI 허브 신규 입주기업 모집 안내",
        "description": "입주기업 모집. 신청접수 2026.07.22 ~ 2026.08.11",
        "posted_date": "2026-07-23",
    }, None, today=TODAY)
    assert ev["factory_required"] is False


def test_real_factory_terms_still_flag():
    ev = m.evaluate_notice({
        "title": "제조 중소기업 생산성향상 지원사업 참여기업 모집공고",
        "description": "공장등록증 보유 기업 대상. 신청접수 2026.07.20 ~ 2026.08.20",
        "posted_date": "2026-07-23",
    }, None, today=TODAY)
    assert ev["factory_required"] is True


# ── 인천시 고시/공고(citynet) 파서 ───────────────────────────────────────────────

_INCHEON_LIST = """
<table><tbody>
<tr onclick="viewData('67225','A')">
 <td>2026-1618</td>
 <td>2026년 관광서비스 기반 강화사업 민간위탁적격자 선정 결과</td>
 <td>국제협력국 관광마이스과</td>
 <td>2026-07-24</td>
 <td>11</td>
</tr>
<tr onclick="viewData('67230','B')">
 <td>2026-1620</td>
 <td>2026년 중소기업 지원사업 참여기업 모집 공고</td>
 <td>경제산업국</td>
 <td>2026-07-23</td>
 <td>3</td>
</tr>
</tbody></table>
"""


def test_fetch_incheon_city_parses_citynet_rows(monkeypatch):
    monkeypatch.setattr(m, "_soup", lambda url, **k: BeautifulSoup(_INCHEON_LIST, "html.parser"))
    items = m.fetch_incheon_city({"id": "incheon_city", "name": "인천광역시청 - 공고/고시",
                                  "url": "http://announce.incheon.go.kr/x", "is_aggregator": False})
    assert len(items) == 2
    it = items[1]
    assert it["id"] == "incheon_city_67230"
    assert it["title"] == "2026년 중소기업 지원사업 참여기업 모집 공고"
    assert it["author"] == "경제산업국"
    assert it["posted_date"] == "2026-07-23"
    assert "sno=67230&gosiGbn=B" in it["link"]


# ── 범용 본문 추출: 링크 덩어리(nav) 대신 실제 본문 선택 ────────────────────────

def test_extract_main_content_prefers_nonlink_text():
    html = """
    <html><body>
      <div class="menuwrap">
        <a>재단소개</a><a>인사말</a><a>연혁</a><a>비전</a><a>조직도</a><a>재단현황</a>
        <a>업무안내</a><a>정책기획단</a><a>기업지원단</a><a>미래자동차본부</a><a>지능기계본부</a>
        <a>우주항공본부</a><a>조선해양본부</a><a>나노융합본부</a><a>에너지바이오본부</a>
        <a>방위산업본부</a><a>경영지원실</a><a>지원사업신청</a><a>스마트공장지원</a>
        <a>기관별지원사업안내</a><a>입주지원</a><a>장비지원</a><a>윤리경영실</a><a>알림마당</a>
      </div>
      <div class="bbs">
        <td>제목 AI기반 미래자동차 검증 기반구축 기획위원 모집공고 사업 담당자 윤문영
        부서 자동차산업팀 직급 전임연구원 연락처 이메일 신청기간 이천이십육년 칠월 이십삼일부터
        접수 바랍니다 자세한 내용은 첨부파일을 확인해 주시기 바랍니다</td>
      </div>
    </body></html>
    """
    body = m._extract_main_content(BeautifulSoup(html, "html.parser"))
    assert "기획위원 모집공고" in body
    assert "재단소개" not in body
