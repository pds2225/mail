"""2026-10-13 실발송(run #263, '예비창업 AI') 메일 원문으로 만든 회귀 테스트."""
from datetime import date

import monitor
from mail_core.delivery import digest_table as dt

TODAY = date(2026, 10, 13)
JUNK_GTP = "공지사항 공지사항 HOME 공고ㆍ안내 공지사항 공지사항 지역기술혁신의 허브 선착순 마감 2026-12-31"


def _item(title, deadline, desc="", **kw):
    return {"title": title, "deadline": deadline, "description": desc, "link": "https://example.org/x", **kw}


REAL = [
    _item("인천서구]2025년 해외지사화 지원사업 2차 참가신청 모집", "2025-09-03",
          "최대 100만원 관리자 2025-09-04 12:58:00 hit 62 선착순"),
    _item("모집중(2026-207호) 2026년 강원 미래모빌리티 기업지원 프로그램 모집 통합공고", "2026-10-13",
          "완료 제 목 :"),
    _item("2026년 중앙부처 및 지자체 창업지원사업 통합공고", "2025-12-19",
          "지원분야 사업화 대상연령 전체 기관구분 공공기관 담당부서 사업관리실 수시모집", author="창업진흥원"),
    _item("[교육안내] 2026년 광명상생플랫폼 운영지원사업 온라인 마케팅 2차 교육 참석자 모집", "9/28", JUNK_GTP),
    _item("[교육안내] 2026년 양주시 중소기업 온라인 마케팅 교육 안내 (7.10)", "7/8", JUNK_GTP),
    _item("2026년 안산시 청년창업 온라인 마케팅 지원사업 '시민파워셀러' 4회차 교육", "9/14", JUNK_GTP),
    _item("[교육안내] 2026년 파주시 청년창업 온라인 마케팅 실무교육 2차 교육", "7/6", JUNK_GTP),
]


def test_expired_deadlines_dropped_even_with_junk_keywords():
    for it in REAL:
        expect_closed = it["deadline"] != "2026-10-13"
        assert monitor._digest_is_closed(it, TODAY) is expect_closed, it["title"]
    body = monitor.fallback_body(REAL, today=TODAY)
    for d in ("2025/9/3", "2025/12/19", "9/28", "7/8", "9/14", "7/6"):
        assert f" · {d}" not in body
    assert "10/13 (D-0)" in body


def test_yearless_md_inference():
    assert monitor._digest_deadline_end(_item("t", "9/28"), TODAY) == date(2026, 9, 28)
    assert monitor._digest_deadline_end(_item("t", "1/15"), TODAY) == date(2027, 1, 15)
    assert monitor._digest_is_closed(_item("t", "1/15"), TODAY) is False
    assert monitor._digest_is_closed(_item("t", "10/20"), TODAY) is False


def test_support_junk_detector_real_strings():
    for junk in ("공지사항 공지사항 HOME 공고ㆍ안내 공지사항 공지사항 지역기술혁신의",
                 "관리자 2025-09-04 12:58:00 hit 62", "완료 제 목 :",
                 "지원분야 사업화 대상연령 전체 기관구분 공공기관 담당부서 사업관리실 지"):
        assert monitor.is_support_junk(junk), junk
    assert not monitor.is_support_junk("해외 마케팅 비용 및 현지 지사화 컨설팅 지원")


def test_support_line_hidden_or_amount_only():
    assert monitor._mail_support_summary(REAL[0]) == "최대 100만원"
    assert monitor._mail_support_summary(REAL[1]) == ""
    assert monitor._mail_support_summary(REAL[3]) == ""
    it = dict(REAL[1], ai_summary="AI 요약: 미래모빌리티 기업 시제품·인증 지원")
    assert monitor._mail_support_summary(it).startswith("AI 요약")


REAL_PLAIN_TAIL = """📋 지원사업 공고 목록

■ 판로·실증 (1건)
[교육안내] 2026년 광명상생플랫폼 운영지원사업 온라인 마케팅 2차 교육 참석자 모집
   💰 공지사항 공지사항 HOME 공고ㆍ안내 공지사항 공지사항 지역기술혁신의…
   확인필요 · 확인필요 · 서울 · 9/28
   https://www.gtp.or.kr/web/bbs/noticeView.jsp?gubun=&cPage=1&no=29725

■ 기타 (3건)
[교육안내] 2026년 양주시 중소기업 온라인 마케팅 교육 안내 (7.10)
   확인필요 · 확인필요 · 서울 · 7/8
   https://www.gtp.or.kr/web/bbs/noticeView.jsp?gubun=&cPage=1&no=29492
2026년 안산시 청년창업 온라인 마케팅 지원사업 '시민파워셀러' 4회차 교육
   확인필요 · 확인필요 · 서울 · 9/14
   https://www.gtp.or.kr/web/bbs/noticeView.jsp?gubun=&cPage=1&no=29686
[교육안내] 2026년 파주시 청년창업 온라인 마케팅 실무교육 2차 교육
   확인필요 · 확인필요 · 서울 · 7/6
   https://www.gtp.or.kr/web/bbs/noticeView.jsp?gubun=&cPage=1&no=29507
────────────────────────────────
🙋 이 추천, 맞았나요? — 아래 링크를 누르면 메일 작성창이 자동으로 열립니다.
   그대로 '전송'만 누르면 정답으로 기록돼 다음부터 더 정확해집니다. (한 건만 눌러도 도움돼요)
"""


def test_footer_not_parsed_as_card_and_sections_match():
    _before, rows, after = dt.parse_plain_table(REAL_PLAIN_TAIL)
    assert len(rows) == 4
    assert after.startswith("────")
    html = dt.html_email_inner(REAL_PLAIN_TAIL, lambda s: s)
    assert "판로·실증 (1건)" in html and "기타 (3건)" in html
    assert "기타 (6건)" not in html
    assert "확인필요 · 확인필요 · 확인필요" not in html
    assert "🙋 이 추천" in html  # 꼬리말은 일반 텍스트로 유지
