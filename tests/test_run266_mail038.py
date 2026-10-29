"""MAIL-038: run #266(10/14 12:20 KST 발송) digest dump 실제 문자열 회귀."""
from datetime import datetime

import pytest

import monitor
from mail_core.delivery import digest_lint as dl

NOW = datetime(2026, 10, 14, 12, 20, tzinfo=monitor.KST)
MENU = "KOR ENG JPN CHN ARB 검색 폼 SEARCH 검색 [일반] 고양 글로벌 투자 서밋 개최"


def _item(title, deadline="2026-10-30", **kw):
    return {"id": kw.pop("id", title[:12]), "title": title, "deadline": deadline,
            "description": kw.pop("description", ""), "link": kw.pop("link", "https://example.test/n"), **kw}


def test_lang_search_menu_is_junk_in_extractor():
    assert monitor.is_support_junk(MENU)
    it = _item("고양 글로벌 투자 서밋 개최", "", description=MENU,
               link="https://www.gipa.or.kr/community/01_1.php?no=4921")
    assert monitor._mail_support_summary(it) == ""
    assert not monitor.is_support_junk("ENG 통번역 비용 지원")  # 단독 ENG 는 메뉴 아님


def test_lang_search_menu_flagged_by_lint_without_callable():
    body = ("📋 지원사업 공고 목록\n\n■ 기타 (1건)\n고양 글로벌 투자 서밋 개최\n"
            "   💰 KOR ENG JPN CHN ARB 검색 폼 SEARCH 검색 [일반]…\n   경기 · 확인필요\n")
    r = dl.lint_digest("[g] 1건 (10/14 오후)", body, is_junk=None)
    assert "JUNK_SUPPORT" in r["codes"]
    assert "KOR ENG" not in dl.strip_junk_support_lines(body, lambda s: False)


def test_jbci_multiword_category_prefix():
    link = "https://www.jbci.or.kr/sub/business_1_view.html?id=6860"
    assert monitor.clean_item_title(_item("입주&보육 군산시 2026년 창업플랫폼 예비창업자 모집 공고", link=link)) == \
        "군산시 2026년 창업플랫폼 예비창업자 모집 공고"
    assert monitor.clean_item_title(_item("교육·행사 2026 창업 아카데미 모집", link=link)) == "2026 창업 아카데미 모집"
    assert monitor.clean_item_title(_item("사업화 2026년 2차 중소기업 정보보호 지원 사업", link=link)).startswith("2026년")
    assert monitor.clean_item_title(_item("입주&보육 군산시 모집", link="https://other.example.test/x")).startswith("입주&보육")


def test_title_amount_preferred_over_page_amount():
    it = _item("바른동행 4차 모집｜선발 시 최대 5억원 투자", "2026-10-27",
               description="운용자산 최대 100억원 규모 펀드에서 투자합니다")
    assert monitor._mail_support_summary(it) == "최대 5억원"
    same = _item("수출바우처 최대 3,000만원 지원", description="기업당 최대 3,000만원 바우처 지급")
    assert monitor._mail_support_summary(same).startswith("최대 3천만원")
    no_title_amt = _item("2026년 강원 미래모빌리티 기업지원 프로그램 모집 공고(재공고)",
                         description="기업당 최대 3,900만원 지원")
    assert monitor._mail_support_summary(no_title_amt).startswith("최대 3,900만원")


@pytest.mark.parametrize(("day", "expected_ids"), [
    (14, ["a", "c", "b"]),  # run #266: section order differs from input order
    (21, ["a", "c"]),       # expired notices must disappear from both lists
    (28, ["a"]),
    (31, []),
])
def test_feedback_order_matches_card_order(monkeypatch, day, expected_ids):
    now = NOW.replace(day=day)
    # Production run_monitor freezes _now_kst for all renderers. Passing now to
    # the assembler alone leaves fallback_body on the wall clock instead.
    monkeypatch.setattr(monitor, "_now_kst", lambda: now)
    monkeypatch.setenv("MONITOR_DIGEST_LLM", "0")
    monkeypatch.setattr(monitor, "_feedback_links_enabled", lambda: True)
    items = [
        _item("2026년 강원 미래모빌리티 기업지원 프로그램 모집 공고(재공고)", "2026-10-30", id="a",
              description="바우처를 지원합니다"),
        _item("고양 글로벌 투자 서밋 개최", "2026-10-20", id="b"),
        _item("바른동행 4차 모집｜선발 시 최대 5억원 투자", "2026-10-27", id="c",
              support_field="수출바우처"),
    ]
    out = monitor._build_group_mail_content(
        group={"name": "g"}, g_items=items, ru_mail_items=[], ru_items=[], ru_limit=10, filtered_new=items,
        window_label="w", days_back=3, date_str=monitor._send_date_label(now), now=now)
    body = out["body"]
    if not expected_ids:
        assert "📋" not in body and "🙋" not in body
        assert "그룹 매칭 0건" in body
        return
    cards = body[body.index("📋"):body.index("🙋")]
    card_titles = [l for l in cards.split("\n") if l and not l.startswith(" ") and not l.startswith(("■", "📋", "─"))]
    fb = body[body.index("🙋"):]
    fb_titles = [l.split(". ", 1)[1] for l in fb.split("\n") if l[:1].isdigit() and ". " in l]
    expected_titles = [next(it["title"] for it in items if it["id"] == nid) for nid in expected_ids]
    assert fb_titles == card_titles == expected_titles
