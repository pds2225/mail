import httpx

from scripts import download_kstartup_targets as dl


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
            return httpx.Response(200, text=html)

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
