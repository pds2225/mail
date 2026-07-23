"""Unit tests for K-Startup target notice finding and outbound link parsing."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")

import httpx  # noqa: E402

from scripts import download_kstartup_targets as dl  # noqa: E402
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


# ── 회귀 3종 (origin/cursor/critical-bug-investigation-3f02 흡수) ──────────────
def _notice_html(sn: int, title: str, org: str = "Agency") -> str:
    return f"""
    <div class="notice">
      <a href="#" title="{title}">{title}</a>
      <button onclick="goView('{sn}')">detail</button>
      <span class="list">{org}</span>
      <span class="list">마감일자 2026.07.31</span>
      <span class="list">등록일자 2026.06.23</span>
      <span class="flag">모집중</span>
    </div>
    """


def test_extract_attachment_candidates_keeps_real_downloads_and_rejects_noise():
    """실다운로드(직링크·data-url·onclick·downloadPath)는 유지, JS 잡음·비첨부 링크는 제외."""
    html = """
    <html>
      <body>
        <a href="/afile/fileDownload/101?fileSn=1">공고문 다운로드</a>
        <a href="/afile/fileDownload/101?fileSn=1">공고문 다운로드 중복</a>
        <button data-url="/board/attach/application.hwpx">붙임 신청서</button>
        <button onclick="downloadFile('/web/cmm/fms/FileDown.do?atchFileId=abc')">
          서식 다운로드
        </button>
        <a href="javascript:void(0)">다운로드 버튼</a>
        <a href="/web/contents/bizpbanc-ongoing.do">상세보기</a>
        <script>
          var downloadBtn = 'downloadBtn';
          var fileName = 'plainToken';
          var data = { downloadPath: '/afile/fileDownload/202?fileSn=2' };
        </script>
      </body>
    </html>
    """

    candidates = dl.extract_attachment_candidates(
        html,
        "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do",
    )

    urls = [c.url for c in candidates]
    assert urls == [
        "https://www.k-startup.go.kr/afile/fileDownload/101?fileSn=1",
        "https://www.k-startup.go.kr/board/attach/application.hwpx",
        "https://www.k-startup.go.kr/web/cmm/fms/FileDown.do?atchFileId=abc",
        "https://www.k-startup.go.kr/afile/fileDownload/202?fileSn=2",
    ]
    assert all("javascript:" not in url for url in urls)
    assert all("downloadBtn" not in url and "plainToken" not in url for url in urls)


def test_candidate_from_url_rejects_bare_script_tokens():
    """bare JS 토큰(downloadBtn·fileName)·javascript: 는 후보 불가, ../상대경로는 정규화."""
    base_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"

    assert dl.candidate_from_url("downloadBtn", "다운로드", base_url, "onclick") is None
    assert dl.candidate_from_url("fileName", "다운로드", base_url, "onclick") is None
    assert dl.candidate_from_url("javascript:void(0)", "다운로드", base_url, "href") is None

    candidate = dl.candidate_from_url(
        "../afile/fileDownload/301?fileSn=3",
        "사업계획서 양식",
        base_url,
        "href",
    )
    assert candidate is not None
    assert candidate.url == "https://www.k-startup.go.kr/web/afile/fileDownload/301?fileSn=3"


def test_collect_kstartup_items_paginates_classes_and_deduplicates(monkeypatch):
    """공공(PBC010)·민간(PBC020) 페이지네이션 순회 + pbancSn 기준 중복 제거."""
    pages = {
        ("PBC010", "1"): _notice_html(1001, "Public first notice", "Public Agency"),
        ("PBC010", "2"): _notice_html(1002, "Public second page notice", "Public Agency"),
        ("PBC020", "1"): (
            _notice_html(1002, "Duplicate private notice", "Private Agency")
            + _notice_html(2001, "Private first notice", "Private Agency")
        ),
        ("PBC020", "2"): "",
    }
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params):
            calls.append((params["pbancClssCd"], params["pageIndex"]))
            html = pages.get((params["pbancClssCd"], params["pageIndex"]), "")
            return httpx.Response(200, text=html, request=httpx.Request("GET", url))

    monkeypatch.setattr(dl.httpx, "Client", FakeClient)

    items = dl.collect_kstartup_items(max_pages=2)

    assert [item["id"] for item in items] == [
        "kstartup_1001",
        "kstartup_1002",
        "kstartup_2001",
    ]
    assert any("pageIndex=2" not in item["link"] for item in items)
    assert ("PBC010", "2") in calls
    assert ("PBC020", "2") in calls
    assert next(item for item in items if item["id"] == "kstartup_1002")["link"].endswith(
        "pbancClssCd=PBC010&schM=view&pbancSn=1002"
    )


def test_get_with_ssl_fallback_order_and_status_error_no_fallback(monkeypatch):
    """SSL 폴백 순서(strict→no_verify→legacy) 검증 + 4xx/5xx 는 폴백 없이 즉시 전파."""
    import ssl

    url = "https://legacy-tls.example.go.kr/notice/file.hwp"
    seen_verify: list = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.verify = kwargs.get("verify")
            seen_verify.append(self.verify)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, got_url):
            # strict(True)·no_verify(False) 단계는 핸드셰이크 실패를 재현
            if self.verify is True or self.verify is False:
                raise httpx.ConnectError("ssl handshake failure", request=httpx.Request("GET", got_url))
            return httpx.Response(200, text="ok", request=httpx.Request("GET", got_url))

    monkeypatch.setattr(dl.httpx, "Client", FakeClient)
    r = dl.get_with_ssl_fallback(url, headers={}, timeout=5)
    assert r.status_code == 200 and r.text == "ok"
    assert seen_verify[0] is True and seen_verify[1] is False
    assert isinstance(seen_verify[2], ssl.SSLContext)  # legacy 단계 = 구식 TLS 컨텍스트
    assert len(seen_verify) == 3

    # 서버가 응답한 HTTP 오류는 SSL 문제가 아니므로 다음 단계로 넘어가지 않는다.
    seen_verify.clear()

    class FakeClient404(FakeClient):
        def get(self, got_url):
            req = httpx.Request("GET", got_url)
            return httpx.Response(404, request=req)

    monkeypatch.setattr(dl.httpx, "Client", FakeClient404)
    try:
        dl.get_with_ssl_fallback(url, headers={}, timeout=5)
        raise AssertionError("HTTPStatusError expected")
    except httpx.HTTPStatusError:
        pass
    assert seen_verify == [True]  # strict 1회 시도 후 즉시 전파(폴백 미발동)
