"""메일 표시 개선 회귀 테스트.
사용자 요청: ①키워드는 제목 X, 본문 최하단 숨김 ②제목=그룹명 ③불필요정보(HTML코드 등) 숨김.
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


def test_plain_text_strips_html_and_entities():
    s = '<p>AI 도입과 활용<br>최적화된 솔루션</p><p style="line-height: 1.8;">상시근로자 20인</p>&nbsp;끝'
    out = m._plain_text(s)
    assert "<" not in out and ">" not in out
    assert "style" not in out and "&nbsp;" not in out
    assert "AI 도입과 활용" in out and "상시근로자 20인" in out


def test_fallback_body_hides_html_and_internal_fields():
    it = {
        "id": "1", "title": "2026년 중소기업 AI 훈련 참여기업 모집",
        "author": "고용노동부", "description": '<p>AI 도입 지원</p><p style="x">맞춤 컨설팅</p>',
        "deadline": "2099-12-31", "source": "기업마당", "posted_date": "2026-06-12",
        "is_aggregator": False, "_types": ["컨설팅·교육·상담"],
        "matched_keywords": ["글로벌"], "priority_keywords": [], "priority_keyword": False,
        "region_status": "eligible", "eligible_regions": [], "applicant_region_city": "서울특별시",
    }
    body = m.fallback_body([it])
    # HTML/코드 노출 없음
    assert "<p>" not in body and "style" not in body
    # 내부정보 숨김
    assert "매칭 키워드" not in body
    assert "우선 키워드" not in body
    assert "스마트공장 관련성" not in body
    assert "글로벌" not in body          # 매칭키워드(캐럿글로벌 류) 노출 안 함
    # 비제약 지역('서울특별시 전체')은 생략
    assert "전체" not in body
    # 필요한 정보는 평문으로 보임
    assert "AI 도입 지원" in body and "맞춤 컨설팅" in body
    assert "고용노동부" in body


def test_execute_monitor_subject_groupname_and_keyword_footer(monkeypatch):
    items = [{"id": "a1", "title": "AI 솔루션 도입 지원 신청접수", "description": "서울 전국 중소기업 대상",
              "link": "https://x/1", "author": "기관", "deadline": "2099-12-31", "source": "기업마당",
              "posted_date": "", "is_aggregator": False}]
    monkeypatch.setattr(m, "fetch_all", lambda s, **k: list(items))
    monkeypatch.setattr(m, "enrich_items", lambda its, **k: its)
    monkeypatch.setattr(m, "load_sites", lambda: [{"id": "s", "enabled": True}])
    monkeypatch.setattr(m, "load_groups", lambda: [{
        "id": "g", "name": "AI팀", "active": True, "or_keywords": ["AI"],
        "required_conditions": {"regions": ["전국"]},
        "applicant_region_city": "서울특별시", "applicant_region_label": "서울",
        "recipients": ["ekth3691@gmail.com"]}])
    monkeypatch.setattr(m, "load_settings", lambda: {
        "date_filter_enabled": False, "raw_all_enabled": False, "raw_all_recipients": [],
        "company_match_enabled": False})
    monkeypatch.setattr(m, "load_watchlist", lambda: {"keywords": [], "urls": [], "recipients": []})
    monkeypatch.setattr(m, "claude_summarize", lambda items, group: m.fallback_body(items))
    sent = []
    monkeypatch.setattr(m, "send_to_list", lambda s, b, r: sent.append((s, b)))

    m.execute_monitor(allow_send=True, include_raw_all=False, persist_seen=False)

    grp = [s for s in sent if s[0].startswith("[AI팀]")]
    assert grp, "그룹 메일 제목이 그룹명으로 시작해야 함"
    subj, body = grp[0]
    # 제목엔 'mail_topic'(수출·해외진출/공고 라벨) 없음 — 그룹명 + 건수만
    assert "수출·해외진출" not in subj
    assert "공고" not in subj
    # 키워드는 본문 최하단 푸터에만
    assert "검색조건(참고)" in body
    header = body.split("검색조건")[0]
    assert "키워드:" not in header     # 상단 헤더엔 키워드 없음
