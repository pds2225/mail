"""집중 모니터링 워치리스트 회귀 테스트 (네트워크/SMTP 없음).

사용자가 키워드/제목·URL을 주면 그 공고를 날짜·그룹 필터 우회 강제포함 + 전용메일·푸시로
'절대 안 놓치게' 하는 기능을 고정한다.
"""
import json
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

WL = {
    "keywords": ["지식재산", "IP나래"],
    "urls": ["https://pms.ripc.org/pms/biz/smallBusiness/"],
    "recipients": ["ekth3691@gmail.com"],
}


def test_is_watchlisted_keyword():
    assert m.is_watchlisted({"title": "2026 지식재산 활용 지원사업 공고"}, WL) is True
    assert m.is_watchlisted({"title": "IP나래 프로그램 참여기업 모집"}, WL) is True


def test_is_watchlisted_url_prefix():
    """워치 URL(게시판) 하위의 상세페이지 링크도 매칭."""
    it = {"title": "x", "link": "https://pms.ripc.org/pms/biz/smallBusiness/board/viewBoardDetail.do?id=5"}
    assert m.is_watchlisted(it, WL) is True


def test_is_watchlisted_ascii_word_boundary():
    """ASCII 키워드 'IP'가 'equipment' 부분문자열에 오매칭되면 안 된다."""
    wl = {"keywords": ["IP"], "urls": [], "recipients": []}
    assert m.is_watchlisted({"title": "equipment 도입 지원"}, wl) is False
    assert m.is_watchlisted({"title": "IP 나래 지원사업"}, wl) is True


def test_is_watchlisted_none():
    assert m.is_watchlisted({"title": "일반 공고", "link": "https://other.go.kr/x"}, WL) is False


def test_load_watchlist_normalizes(tmp_path, monkeypatch):
    p = tmp_path / "watchlist.json"
    p.write_text(json.dumps({"keywords": ["지식재산", "  ", ""], "urls": ["u"], "recipients": ["r@x.com"]}),
                 encoding="utf-8")
    monkeypatch.setattr(m, "WATCHLIST_PATH", p)
    wl = m.load_watchlist()
    assert wl["keywords"] == ["지식재산"]
    assert wl["urls"] == ["u"] and wl["recipients"] == ["r@x.com"]


def test_load_watchlist_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "WATCHLIST_PATH", tmp_path / "nope.json")
    wl = m.load_watchlist()
    assert wl == {"keywords": [], "urls": [], "recipients": []}


def test_execute_monitor_force_includes_and_sends_focus_mail(monkeypatch):
    """워치공고는 오래된 날짜라 날짜필터로 빠지지만, 강제포함 + 전용 메일로 보장된다."""
    items = [
        {"id": "w1", "title": "지식재산 활용 지원사업 공고", "description": "", "link": "https://x/1",
         "author": "기관", "deadline": "2099-12-31", "source": "RIPC", "posted_date": "2000-01-01",
         "is_aggregator": False},
        {"id": "n1", "title": "일반 공고", "description": "", "link": "https://x/2",
         "author": "기관", "deadline": "", "source": "s", "posted_date": "2000-01-01",
         "is_aggregator": False},
    ]
    monkeypatch.setattr(m, "fetch_all", lambda sites, **k: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **k: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [{"id": "g", "name": "t", "active": True,
                                                    "or_keywords": ["존재하지않는키워드zzz"], "recipients": []}])
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": True, "days_back": 1, "raw_all_enabled": False,
        "raw_all_recipients": [], "company_match_enabled": False,
    })
    monkeypatch.setattr(m, "load_watchlist", lambda: {
        "keywords": ["지식재산"], "urls": [], "recipients": ["ekth3691@gmail.com"]})
    sent = []
    monkeypatch.setattr(m, "send_to_list", lambda s, b, r: sent.append((s, b, r)))
    pushed = []
    monkeypatch.setattr(m, "alert_ntfy", lambda *a, **k: pushed.append(a))

    res = m.execute_monitor(allow_send=True, include_raw_all=False, persist_seen=False)

    focus = [s for s in sent if s[0].startswith("🎯 [집중 모니터링]")]
    assert focus, "집중 모니터링 전용 메일이 발송돼야 함"
    subj, body, recip = focus[0]
    assert "지식재산" in body
    assert recip == ["ekth3691@gmail.com"]
    assert pushed, "워치 매칭 시 ntfy 푸시가 호출돼야 함"
    assert res["filtered_items"] >= 1   # 강제포함 확인
