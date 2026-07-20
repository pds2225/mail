"""[원본전체] 보고 메일 정렬 + 잡공고 제거 회귀 테스트.
요청: ①출처·지역순 정렬(기업마당>K스타트업>전국>서울>경기>인천>충청>기타) ②공지·결과·채용 등 잡공고 제외.
"""
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


def test_is_report_junk_detects_notices():
    for t in ["2026년 우수기업 선정결과 발표", "신입 채용공고", "서포터즈 모집",
              "정기총회 개최 안내", "낙찰 결과 공고", "운영위원 모집"]:
        assert m.is_report_junk({"title": t}) is True, t


def test_is_report_junk_keeps_real_grants():
    for t in ["AI 바우처 지원사업 참여기업 모집 공고", "수출바우처 공고",
              "2026 해외전시회 참가기업 모집", "스마트공장 구축 지원사업"]:
        assert m.is_report_junk({"title": t}) is False, t


def test_report_rank_source_first_then_region():
    assert m._report_rank({"source": "기업마당(Bizinfo)", "author": "", "title": "x"}) == 1
    assert m._report_rank({"source": "K-Startup", "author": "", "title": "x"}) == 2
    assert m._report_rank({"source": "기타", "author": "", "title": "전국 중소기업 지원", "description": ""}) == 3
    assert m._report_rank({"source": "기타", "author": "", "title": "[서울] 지원사업", "description": ""}) == 4
    assert m._report_rank({"source": "기타", "author": "인천테크노파크", "title": "지원사업", "description": ""}) == 6
    # 지역 미표기 → 전국 기본
    assert m._report_rank({"source": "기타", "author": "중소벤처기업부", "title": "지원사업", "description": ""}) == 3


def test_render_all_buckets_in_requested_order():
    items = [
        {"id": "a", "title": "인천 공고", "author": "인천테크노파크", "source": "s", "posted_date": ""},
        {"id": "b", "title": "공고1", "author": "", "source": "기업마당(Bizinfo)", "posted_date": ""},
        {"id": "c", "title": "공고2", "author": "", "source": "s", "description": "전국 중소기업", "posted_date": ""},
    ]
    body = m.render_all(items, 0, 0)
    i_corp = body.index("━━━ 기업마당")
    i_nat = body.index("━━━ 전국 대상")
    i_inc = body.index("━━━ 인천")
    assert i_corp < i_nat < i_inc
