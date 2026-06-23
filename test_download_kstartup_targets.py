"""Unit tests for K-Startup target notice finding and outbound link parsing."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")

from scripts.download_kstartup_targets import (  # noqa: E402
    _apply_anchor_boost,
    accept_match,
    _looks_like_real_download_url,
    extract_outbound_urls,
    find_notice_for_target,
    match_notice,
    search_keywords_from_title,
)


def test_search_keywords_from_title_extracts_bracket_and_tokens():
    kws = search_keywords_from_title("「2026 헬스엑스챌린지 서울」 참여기업 모집")
    assert "2026 헬스엑스챌린지 서울" in kws
    assert any("헬스엑스" in k for k in kws)


def test_match_notice_token_overlap_boosts_partial_title():
    target = "2026년 판교허브 투자유치 밸류업 패키지 지원기업 모집"
    items = [{
        "title": "2026년 판교허브 투자유치 밸류업 패키지 지원기업 모집 공고",
        "link": "https://example.test/1",
    }]
    item, score = match_notice(target, items)
    assert item is not None
    assert score >= 0.72


def test_extract_outbound_urls_from_fn_open_window():
    html = """
    <button onclick="javascript:fn_open_window('cbpm.cbnu.ac.kr/notice/notice/?mod=document&uid=1243');">
      사업안내 바로가기
    </button>
    <a href="https://www.k-startup.go.kr/magicsso/requestAuthEx.jsp?RelayState=https://www.bizinfo.go.kr">
      기업마당
    </a>
    """
    urls = extract_outbound_urls(html, "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=1")
    assert any("cbpm.cbnu.ac.kr" in u for u in urls)
    assert not any("magicsso" in u for u in urls)


def test_anchor_boost_accepts_healthx_on_kstartup_title():
    score = _apply_anchor_boost(
        "「2026 헬스엑스챌린지 서울」 참여기업 모집",
        "「2026 헬스엑스챌린지 서울」 참여기업 모집 새로운게시글",
        0.58,
    )
    assert score >= 0.76


def test_reject_empty_orgFileNm_download_url():
    assert not _looks_like_real_download_url("https://www.k-startup.go.kr/web/comm/fileDownHwp.do?orgFileNm=")


def test_find_notice_for_target_prefers_kstartup_then_bizinfo():
    class EmptySearchClient:
        def get(self, *args, **kwargs):
            class Resp:
                text = "<html><body></body></html>"

                @staticmethod
                def raise_for_status():
                    return None

            return Resp()

    kstartup_pool = [{
        "title": "「2026 헬스엑스챌린지 서울」 참여기업 모집",
        "link": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=99",
    }]
    bizinfo_pool = [{
        "title": "다른 공고",
        "link": "https://www.bizinfo.go.kr/detail/1",
    }]
    item, score, source = find_notice_for_target(
        "「2026 헬스엑스챌린지 서울」 참여기업 모집",
        kstartup_pool,
        EmptySearchClient(),
        bizinfo_pool=bizinfo_pool,
        extra_pool=None,
        monitor_pool=None,
        min_score=0.72,
    )
    assert source == "kstartup"
    assert score >= 0.72
    assert "k-startup.go.kr" in item["link"]

    item2, score2, source2 = find_notice_for_target(
        "2026년 판교허브 투자유치 밸류업 패키지 지원기업 모집",
        [],
        EmptySearchClient(),
        bizinfo_pool=[{
            "title": "2026년 판교허브 투자유치 밸류업 패키지 지원기업 모집 공고",
            "link": "https://www.bizinfo.go.kr/detail/2",
        }],
        extra_pool=None,
        monitor_pool=None,
        min_score=0.72,
        use_bizinfo=True,
    )
    assert source2 == "bizinfo"
    assert score2 >= 0.72
    assert "bizinfo.go.kr" in item2["link"]
