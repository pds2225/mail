from datetime import date

from loan.semas.keywords import detect_keywords, keyword_presence
from loan.semas.parser import SemasNotice, classify_notices, parse_notices


def test_keyword_detection_policy_restart_closed_budget():
    text = "정책자금 재도전특별자금 접수 안내: 신청 마감 및 예산소진 가능"
    assert "정책자금" in detect_keywords(text)
    assert "재도전특별자금" in detect_keywords(text)
    presence = keyword_presence(text)
    assert presence["정책자금"] is True
    assert presence["재도전특별자금"] is True
    assert presence["마감"] is True
    assert presence["예산소진"] is True


def test_parse_notices_extracts_relevant_anchor_and_date():
    html = """
    <table><tr>
      <td><a href="/notice/123">2026년 소상공인 정책자금 직접대출 접수 안내</a></td>
      <td>2026.05.26</td>
    </tr></table>
    """
    notices = parse_notices(html, "https://ols.semas.or.kr/ols/man/SMAN051M/page.do")
    assert len(notices) == 1
    assert notices[0].posted_date == "2026-05-26"
    assert notices[0].url == "https://ols.semas.or.kr/notice/123"
    assert "정책자금" in notices[0].keywords




def test_parse_notices_skips_navigation_links():
    html = """
    <nav>
      <a href="/ols/man/SMAN018M/page.do">정책자금한눈에보기</a>
      <a href="/ols/man/SMAN055M/page.do">직접대출</a>
      <a href="https://www.juso.go.kr/openIndexPage.do">도로명주소안내</a>
    </nav>
    """
    assert parse_notices(html, "https://ols.semas.or.kr/ols/man/SMAN051M/page.do") == []

def test_date_filter_splits_today_recent_old_and_unknown():
    notices = [
        SemasNotice("오늘 정책자금 공지", "https://example.com/a", "2026-05-26", ["정책자금"]),
        SemasNotice("최근 재도전특별자금 안내", "https://example.com/b", "2026-05-24", ["재도전특별자금"]),
        SemasNotice("오래된 정책자금 공지", "https://example.com/c", "2026-05-20", ["정책자금"]),
        SemasNotice("날짜없는 접수 안내", "https://example.com/d", "", ["접수"]),
    ]
    result = classify_notices(notices, set(), 3, today=date(2026, 5, 26))
    titles = {notice.title for notice in result["new"]}
    assert "오늘 정책자금 공지" in titles
    assert "최근 재도전특별자금 안내" in titles
    assert "날짜없는 접수 안내" in titles
    assert "오래된 정책자금 공지" not in titles


def test_duplicate_detection_uses_title_url_and_date():
    first = SemasNotice("정책자금 접수 안내", "https://example.com/a", "2026-05-26", ["정책자금"])
    duplicate = SemasNotice("정책자금 접수 안내", "https://example.com/a", "2026-05-26", ["정책자금"])
    changed_date = SemasNotice("정책자금 접수 안내", "https://example.com/a", "2026-05-25", ["정책자금"])
    result = classify_notices([first, duplicate, changed_date], set(), 3, today=date(2026, 5, 26))
    assert result["duplicate_removed_count"] == 1
    assert len(result["unique"]) == 2


def test_duplicate_detection_falls_back_to_title_url_without_date():
    first = SemasNotice("정책자금 접수 안내", "https://example.com/a", "", ["정책자금"])
    duplicate = SemasNotice("정책자금 접수 안내", "https://example.com/a", "", ["정책자금"])
    result = classify_notices([first, duplicate], set(), 3, today=date(2026, 5, 26))
    assert result["duplicate_removed_count"] == 1
    assert len(result["unique"]) == 1

