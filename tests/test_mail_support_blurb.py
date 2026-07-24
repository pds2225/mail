"""메일 '지원내용' 크롬·장문 정리 회귀 (2026-07-24).

배경: 상세 추출 실패/셀렉터 오탐 시 description 에 nav·푸터·메뉴가 통째로 실려
그룹 메일의 '지원내용'이 수백 자의 불필요 텍스트로 채워졌다.
표시 전용 mail_support_blurb 가 크롬을 거르고 480자로 유계한다.
매칭/필터용 description 원문은 변경하지 않는다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import monitor as m  # noqa: E402

GNTP_CHROME = (
    "메인 회원가입 로그인 텍스트크기 고객센터 공직비리익명신고(TP) 소극행정신고센터 "
    "국가인적자원개발컨소시엄 재단소개 인사말 연혁 비전 조직도 지원사업 지원사업신청 "
    "스마트공장지원 입찰정보 공지사항 채용정보 패밀리 사이트 강원테크노파크 서울테크노파크 "
    "홈화면 > 공지사항 > 게시글 상세보기 공지사항 제목 "
    "AI기반 종단간 미래자동차 E2E 고속자율주행 고성능 특화플랫폼 검증 기반구축 기획위원(후보자) 모집공고 "
    "첨부 1 기획위원 모집공고 및 관련서식.hwp 다운로드 내용보기 ■ 담당자정보 사업 담당자 윤문영 "
    "개인정보처리방침 ｜ 이메일무단수집거부 ｜ Copyright ⓒ 2014 재단법인 경남테크노파크 "
    "대표전화 1688-3360"
)


def test_chrome_dump_is_short_and_drops_nav():
    blurb = m.mail_support_blurb({
        "title": "AI기반 종단간 미래자동차 E2E 고속자율주행 고성능 특화플랫폼 검증 기반구축 기획위원(후보자) 모집공고",
        "description": GNTP_CHROME,
    })
    assert "회원가입" not in blurb
    assert "패밀리 사이트" not in blurb
    assert "Copyright" not in blurb
    assert "개인정보처리방침" not in blurb
    assert len(blurb) <= m.MAIL_SUPPORT_BLURB_LIMIT + 5  # … 여유
    # 제목 앵커 이후 알맹이(또는 빈 문자열) — 긴 nav 덤프는 아님
    assert len(blurb) < len(GNTP_CHROME) * 0.5


def test_chrome_only_falls_back_to_support_field():
    blurb = m.mail_support_blurb({
        "title": "2026 서울 AI 허브 입주기업 모집",
        "description": "회원가입 로그인 텍스트크기 개인정보처리방침 Copyright ⓒ 2026",
        "support_field": "시설ㆍ공간ㆍ보육",
    })
    assert blurb == "시설ㆍ공간ㆍ보육"
    assert "회원가입" not in blurb


def test_real_grant_body_kept_readable():
    unit = (
        "서울 소재 AI 스타트업을 대상으로 사업화 자금과 멘토링을 지원합니다. "
        "신청기간 내 온라인 접수. 선정 시 최대 5천만원. "
    )
    body = unit * 20  # >> MAIL_SUPPORT_BLURB_LIMIT
    blurb = m.mail_support_blurb({
        "title": "2026 AI 사업화 지원 참여기업 모집",
        "description": body,
        "support_field": "사업화",
    })
    assert "스타트업" in blurb or "사업화" in blurb
    assert "회원가입" not in blurb
    assert len(blurb) <= m.MAIL_SUPPORT_BLURB_LIMIT + 5
    assert blurb.endswith("…")  # 장문은 말줄임
    assert len(body) > m.MAIL_SUPPORT_BLURB_LIMIT


def test_fallback_body_uses_cleaned_blurb_not_raw_chrome():
    it = {
        "id": "1",
        "title": "AI기반 기획위원 모집공고",
        "author": "경남TP",
        "description": GNTP_CHROME,
        "deadline": "2099-12-31",
        "source": "경남테크노파크",
        "posted_date": "2026-07-23",
        "_types": ["그외"],
        "priority_keyword": False,
        "priority_keywords": [],
        "region_status": "eligible",
        "eligible_regions": [],
        "applicant_region_city": "서울특별시",
    }
    body = m.fallback_body([it])
    assert "지원내용:" in body
    assert "회원가입" not in body
    assert "패밀리 사이트" not in body
    # 원문 description 은 그대로(매칭용) — 표시만 정리
    assert "회원가입" in it["description"]


def test_empty_after_chrome_omits_support_line():
    it = {
        "id": "2",
        "title": "안내",
        "author": "x",
        "description": "회원가입 로그인 텍스트크기 Copyright",
        "deadline": "2099-12-31",
        "source": "s",
        "posted_date": "2026-07-23",
        "_types": ["그외"],
        "priority_keyword": False,
        "priority_keywords": [],
        "region_status": "eligible",
        "eligible_regions": [],
        "applicant_region_city": "서울특별시",
    }
    body = m.fallback_body([it])
    assert "지원내용:" not in body
