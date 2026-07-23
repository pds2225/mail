"""공고 링크 첨부 다운로더 단위 테스트 — 네트워크 0(respx) + 순수 로직.

핵심 회귀 포인트:
 1) content-disposition 한글 파일명 복원(CP949 latin-1 깨짐 → 원복)
 2) 공고 제목 추출(og:title 우선, 로그인/모집중 노이즈 제외, URL 폴백)
 3) 차단/오류 HTML 을 첨부로 저장하지 않음
 4) 공고별 폴더 번호 prefix 부여 / 기존 폴더 재사용
"""
import os
import sys
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")

from scripts.fetch_notice_attachments import (  # noqa: E402
    AttachmentCandidate,
    _looks_generic,
    _looks_like_html_body,
    _title_from_label,
    decode_cd_filename,
    download_attachment,
    extract_notice_title,
    gather_candidates,
    resolve_notice_dir,
)


# ---------- 1) content-disposition 파일명 복원 ----------

def test_decode_cd_cp949_korean_recovered():
    """K-Startup 실제 헤더 재현: CP949 한글이 latin-1 로 노출돼도 원복."""
    real = "1. (공고문) 「오픈그라운드 기술협업(O.I.) 프로그램」 참여기업 모집 공고.hwp"
    cd = 'attachment;filename="' + real.encode("cp949").decode("latin-1") + '"'
    assert decode_cd_filename(cd) == real


def test_decode_cd_rfc5987_utf8():
    cd = "attachment; filename*=UTF-8''%EA%B3%B5%EA%B3%A0%EB%AC%B8.hwp"
    assert decode_cd_filename(cd) == "공고문.hwp"


def test_decode_cd_plain_ascii_untouched():
    cd = 'attachment; filename="application_form.pdf"'
    assert decode_cd_filename(cd) == "application_form.pdf"


def test_decode_cd_percent_encoded_utf8():
    cd = 'attachment; filename="%EC%8B%A0%EC%B2%AD%EC%84%9C.hwp"'
    assert decode_cd_filename(cd) == "신청서.hwp"


def test_decode_cd_empty_returns_empty():
    assert decode_cd_filename("") == ""
    assert decode_cd_filename("inline") == ""


def test_decode_cd_java_urlencoder_plus_is_space():
    """캠코 실측: 퍼센트 인코딩 파일명의 '+' 는 공백(Java URLEncoder)."""
    cd = ('attachment; filename="1.%28%EA%B3%B5%EA%B3%A0%EB%AC%B8%292026%EB%85%84'
          '+KAMCO+Startup+TechBlaze+%EB%AA%A8%EC%A7%91%EA%B3%B5%EA%B3%A0.hwp"')
    assert decode_cd_filename(cd) == "1.(공고문)2026년 KAMCO Startup TechBlaze 모집공고.hwp"


def test_decode_cd_plain_plus_untouched():
    """퍼센트 인코딩이 아니면 '+' 를 건드리지 않는다(C++ 등 실제 파일명 보호)."""
    cd = 'attachment; filename="C++ programming guide.pdf"'
    assert decode_cd_filename(cd) == "C++ programming guide.pdf"


def test_decode_cd_raw_percent_with_plus_untouched():
    """%XX 시퀀스가 없는 raw '%' 파일명에서는 리터럴 '+' 를 보존한다."""
    cd = 'attachment; filename="할인10%+쿠폰안내.hwp"'
    assert decode_cd_filename(cd) == "할인10%+쿠폰안내.hwp"


# ---------- 2) 제목 추출 ----------

def test_extract_title_prefers_og_title():
    html = (
        '<html><head>'
        '<title>K-Startup 창업지원포털&gt;사업공고&gt;모집중&gt;상세화면</title>'
        '<meta property="og:title" content="『2026년 Bridge 오픈그라운드』기술협업(O.I.) 지원사업">'
        '</head><body><h2>모집중</h2>'
        '<div class="tit">중소벤처24 통합로그인 사이트</div></body></html>'
    )
    assert extract_notice_title(html, "http://x") == "『2026년 Bridge 오픈그라운드』기술협업(O.I.) 지원사업"


def test_extract_title_skips_noise_uses_class_title():
    html = (
        '<html><head></head><body>'
        '<h2>모집중</h2>'
        '<div class="title">2026년 관광벤처 예비창업자 모집 공고</div>'
        '</body></html>'
    )
    assert extract_notice_title(html, "http://x") == "2026년 관광벤처 예비창업자 모집 공고"


def test_extract_title_fallback_to_url_identifier():
    html = "<html><head><title>모집중</title></head><body><h2>마감</h2></body></html>"
    url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancClssCd=PBC010&schM=view&pbancSn=178336"
    assert extract_notice_title(html, url) == "공고_178336"


def test_looks_generic_detects_menu_and_site_names():
    assert _looks_generic("주요사업")
    assert _looks_generic("전체 : 정보통신산업진흥원")
    assert _looks_generic("공고_16827")
    assert not _looks_generic("2026년 인천광역시 우수디자인 시제품개발지원사업 모집 공고")


def test_title_from_attachment_label_nipa():
    label = "2026년 SaaS 전환지원센터 SaaS 전환 컨설팅 2차 수요기업 모집 공고.hwp (파일크기: 73 KB)"
    assert _title_from_label(label) == "2026년 SaaS 전환지원센터 SaaS 전환 컨설팅 2차 수요기업 모집"


def test_title_from_label_strips_bunim_prefix():
    label = "붙임. 하노이IT지원센터 '26년도 하반기 입주기업 모집 공고문.zip"
    assert _title_from_label(label) == "하노이IT지원센터 '26년도 하반기 입주기업 모집"


# ---------- 3) 차단/오류 HTML 판별 ----------

def test_looks_like_html_body_detects_block_page():
    assert _looks_like_html_body(b"   <!DOCTYPE html><html>")
    assert _looks_like_html_body(b"<center><h2>blocked</h2></center>")
    assert _looks_like_html_body(b"<br>\n<table>")


def test_looks_like_html_body_false_for_hwp_signature():
    # HWP/OLE2 매직넘버는 HTML 이 아니다
    assert not _looks_like_html_body(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert not _looks_like_html_body(b"%PDF-1.7")


@respx.mock
def test_download_rejects_blocked_html(tmp_path):
    url = "https://www.k-startup.go.kr/afile/fileDownload/zzz"
    respx.get(url).mock(return_value=httpx.Response(
        200, headers={"content-type": "text/html; charset=utf-8"},
        content="<center>blocked by firewall</center>".encode()))
    cand = AttachmentCandidate(url=url, label="다운로드", source="href")
    with pytest.raises(RuntimeError):
        download_attachment(cand, "https://www.k-startup.go.kr/detail", tmp_path, 1)


@respx.mock
def test_download_gnuboard_file_unknown_percent_name(tmp_path):
    """그누보드: content-type 이 file/unknown 이어도 cd 의 .pdf 로 저장, %인코딩 한글 복원."""
    url = "https://idsc.kr/_NBoard/download.php?bo_table=business&wr_id=937&no=0"
    cd = 'attachment; filename="%EB%B6%99%EC%9E%841_%EC%84%B8%EB%B6%80%EA%B3%B5%EA%B3%A0%EB%AC%B8.pdf"'
    respx.get(url).mock(return_value=httpx.Response(
        200, headers={"content-type": "file/unknown", "content-disposition": cd},
        content=b"%PDF-1.7\nbody"))
    cand = AttachmentCandidate(url=url, label="붙임1_세부공고문.pdf", source="href")
    name, path = download_attachment(cand, "https://idsc.kr/_NBoard/board.php?wr_id=937", tmp_path, 1)
    assert name == "붙임1_세부공고문.pdf"
    assert path.read_bytes().startswith(b"%PDF")


@respx.mock
def test_download_saves_real_file_with_recovered_name(tmp_path):
    url = "https://www.k-startup.go.kr/afile/fileDownload/sdbLn"
    real = "1. (공고문) 모집 공고.hwp"
    # 실제 서버가 보내는 바이트(CP949) 그대로 주면 httpx 가 latin-1 로 노출한다.
    cd_bytes = b'attachment;filename="' + real.encode("cp949") + b'"'
    respx.get(url).mock(return_value=httpx.Response(
        200,
        headers=[(b"content-type", b"application/octet-stream"),
                 (b"content-disposition", cd_bytes)],
        content=b"\xd0\xcf\x11\xe0HWPDATA"))
    cand = AttachmentCandidate(url=url, label="다운로드", source="href")
    name, path = download_attachment(cand, "https://www.k-startup.go.kr/detail", tmp_path, 1)
    assert name == real
    assert path.exists()
    assert path.read_bytes().startswith(b"\xd0\xcf\x11\xe0")


# ---------- 4) 공고 폴더 번호/재사용 ----------

def test_resolve_notice_dir_assigns_next_number(tmp_path):
    (tmp_path / "01_STAR-Exploration").mkdir()
    (tmp_path / "02_올해의_K-스타트업").mkdir()
    d = resolve_notice_dir(tmp_path, "새 공고 제목", number=True)
    assert d.name == "03_새 공고 제목"


def test_resolve_notice_dir_reuses_same_title(tmp_path):
    (tmp_path / "02_관광벤처 모집 공고").mkdir()
    d = resolve_notice_dir(tmp_path, "관광벤처 모집 공고", number=True)
    assert d.name == "02_관광벤처 모집 공고"


def test_resolve_notice_dir_empty_dir_starts_at_one(tmp_path):
    d = resolve_notice_dir(tmp_path, "첫 공고", number=True)
    assert d.name == "01_첫 공고"


# ---------- 5) 사이트 공통 매뉴얼 제외 (bizok 회귀) ----------

def test_gather_excludes_site_manual():
    html = (
        '<a href="/open_content/guide/manual.pdf">이용자 매뉴얼</a>'
        '<a href="/open_content/support.do?act=down&gb=online&fn=x.hwp&ofn=모집공고.hwp">모집공고</a>'
    )
    cands = gather_candidates(
        "https://bizok.incheon.go.kr/open_content/support.do?act=detail&policyno=7073", html)
    urls = [c.url for c in cands]
    assert not any("manual.pdf" in u for u in urls)   # 사이트 매뉴얼 제외
    assert any("act=down" in u for u in urls)          # 진짜 첨부는 유지


# ---------- 6.5) 캠코(eGovFrame) 회귀 — JS 첨부 인식·footer 오탐·제목 ----------
# 실측 버그(2026-07-08): 캠코 공고에서 진짜 첨부(HWP 3개, fn_egov_downFile JS)는 못 받고
# footer 의 사이트 공통 인증 PDF(KSQI·웹접근성) 2개를 받았으며, 제목도 footer 라벨
# "한국산업의 서비스 품질우수 기업" 으로 오인했다.

KAMCO_FX = Path(__file__).parent.parent / "fixtures" / "notice_attachments" / "kamco_view.html"
KAMCO_URL = "https://www.kamco.or.kr/portal/bbs/view.do?mId=0701010000&ptIdx=380&bIdx=27606"


def _kamco_html() -> str:
    return KAMCO_FX.read_text(encoding="utf-8")


def test_kamco_egov_downfile_urls_synthesized():
    """fn_egov_downFile('FILE_x','n') → /cmm/fms/FileDown.do URL 합성으로 첨부 3개 검출."""
    cands = gather_candidates(KAMCO_URL, _kamco_html())
    filedown = [c for c in cands if "/cmm/fms/FileDown.do" in c.url]
    assert len(filedown) == 3
    assert filedown[0].url == (
        "https://www.kamco.or.kr/cmm/fms/FileDown.do?atchFileId=FILE_000000000013068&fileSn=0")
    assert {c.url.rsplit("fileSn=", 1)[1] for c in filedown} == {"0", "1", "2"}
    assert "모집공고" in filedown[0].label


def test_kamco_footer_cert_pdfs_excluded():
    """footer 의 KSQI·웹접근성 인증 PDF 는 게시물 첨부가 아니다 — 오탐 차단."""
    cands = gather_candidates(KAMCO_URL, _kamco_html())
    urls = [c.url for c in cands]
    assert not any("KSQI" in u or "WA_kamco" in u for u in urls)


def test_kamco_title_from_view_table():
    """제목은 상세 표의 '제목' 행에서 — 메뉴명(공지사항)·footer 라벨 오인 금지."""
    assert extract_notice_title(_kamco_html(), KAMCO_URL) == "「2026 KAMCO Startup TechBlaze」 개최 안내"


def test_body_doc_link_kept_footer_dropped():
    """chrome 필터는 footer 만 제외하고 본문 영역의 직링크 첨부는 유지해야 한다."""
    html = (
        '<html><body>'
        '<div class="board-view"><a href="/files/2026_모집공고문.pdf">2026_모집공고문.pdf</a></div>'
        '<footer><a href="/portal/Downfiles/KSQI.pdf">인증서</a></footer>'
        '<div class="footer-mark-group"><a href="/wa/cert.pdf">웹접근성</a></div>'
        '</body></html>'
    )
    cands = gather_candidates("https://example.go.kr/view.do?idx=1", html)
    urls = [c.url for c in cands]
    assert any("모집공고문" in u for u in urls)          # 본문 첨부 유지
    assert not any("KSQI" in u for u in urls)            # <footer> 제외
    assert not any("/wa/cert" in u for u in urls)        # footer-* 클래스 제외


def test_non_egov_onclick_not_synthesized():
    """표준 함수명이 아니면 URL 을 지어내지 않는다(날조 금지)."""
    html = '<a href="#" onclick="fn_custom_down(\'FILE_1\',\'0\')">첨부.hwp</a>'
    cands = gather_candidates("https://example.go.kr/view.do?idx=2", html)
    assert not any("FileDown.do" in c.url for c in cands)


def test_egov_context_fallback_url_derivation():
    """컨텍스트 패스 폴백 URL 유도(TASK-010): 상세 URL 첫 디렉터리 세그먼트 접두."""
    from scripts.download_kstartup_targets import egov_context_fallback_url

    root = "https://x.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_1&fileSn=0"
    assert egov_context_fallback_url(
        root, "https://x.go.kr/portal/bbs/view.do?id=2"
    ) == "https://x.go.kr/portal/cmm/fms/FileDown.do?atchFileId=FILE_1&fileSn=0"
    # 상세가 루트 바로 아래면(디렉터리 세그먼트 없음) 폴백 없음
    assert egov_context_fallback_url(root, "https://x.go.kr/view.do?id=2") == ""
    # eGov 합성 URL 이 아니면 폴백 없음
    assert egov_context_fallback_url(
        "https://x.go.kr/board/download.do?f=1", "https://x.go.kr/portal/bbs/view.do") == ""


@respx.mock
def test_egov_root_404_falls_back_to_context_path(tmp_path):
    """루트 FileDown.do 가 404 인 컨텍스트 패스 배포 사이트 — 폴백으로 받는다(TASK-010)."""
    detail = "https://ctx.go.kr/portal/bbs/view.do?bIdx=1"
    html = ('<div class="bbs_view"><a href="#" '
            'onclick="fn_egov_downFile(\'FILE_7\',\'0\'); return false;">공고문.hwp</a></div>')
    respx.get(detail).mock(return_value=httpx.Response(200, html=html))
    respx.get("https://ctx.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_7&fileSn=0").mock(
        return_value=httpx.Response(404))
    respx.get("https://ctx.go.kr/portal/cmm/fms/FileDown.do?atchFileId=FILE_7&fileSn=0").mock(
        return_value=httpx.Response(
            200,
            headers=[(b"content-type", b"application/x-msdownload"),
                     (b"content-disposition",
                      b'attachment; filename="' + "공고문.hwp".encode("cp949") + b'"')],
            content=b"\xd0\xcf\x11\xe0HWPDATA"))
    from scripts.fetch_notice_attachments import process_url
    results = process_url(detail, tmp_path, dry_run=False)
    assert [r.status for r in results] == ["DOWNLOADED"]
    assert results[0].file_name == "공고문.hwp"
    assert "portal/cmm/fms" in results[0].file_url   # 실제 사용한 URL = 폴백


def test_malformed_unclosed_nav_does_not_swallow_attachments():
    """미닫힘 <nav>(malformed HTML)가 본문을 삼켜도 첨부를 잃지 않는다(TASK-009 가드).

    파서가 본문 전체를 nav 자손으로 넣는 경우 — 매치 조상이 body 텍스트의
    절반 이상이면 chrome 으로 보지 않아야 한다.
    """
    html = (
        '<body><nav class="gnb"><ul><li>메뉴1</li><li>메뉴2</li></ul>'   # </nav> 누락
        '<div id="contents"><table class="bbs_view"><tr><th>첨부파일</th><td>'
        '<a href="#" onclick="fn_egov_downFile(\'FILE_1\',\'0\')">공고문 및 신청 안내 문서.hwp</a> '
        '<a href="/board/download.do?f=1">신청서식 첨부 파일.hwp</a>'
        '</td></tr></table></div></body>'
    )
    cands = gather_candidates("https://example.go.kr/view.do?idx=7", html)
    urls = [c.url for c in cands]
    assert any("FileDown.do" in u for u in urls)       # eGov 합성 유지
    assert any("download.do" in u for u in urls)       # 직링크 유지


def test_normal_footer_still_excluded_despite_guard():
    """가드가 있어도 정상(소분율) footer 의 인증 PDF 는 계속 제외된다."""
    html = (
        '<body><div id="contents"><h4>사업 안내 본문이 충분히 긴 페이지입니다. '
        '지원 대상과 신청 방법, 제출 서류 안내가 이어집니다.</h4>'
        '<a href="/files/공고문.pdf">공고문.pdf</a></div>'
        '<footer><a href="/portal/Downfiles/KSQI.pdf">인증</a></footer></body>'
    )
    cands = gather_candidates("https://example.go.kr/view.do?idx=8", html)
    urls = [c.url for c in cands]
    assert any("공고문.pdf" in u for u in urls)
    assert not any("KSQI" in u for u in urls)


def test_egov_3arg_variant_no_fake_filename_candidate():
    """3인자 eGov 변형: 합성 URL 1개만 — 파일명 인자로 가짜 상대경로 후보를 만들지 않는다."""
    html = ('<a href="#" onclick="fn_egov_downFile(\'FILE_9\',\'0\',\'1.공고문.hwp\')">'
            '1.공고문.hwp</a>')
    cands = gather_candidates("https://example.go.kr/board/view.do?idx=3", html)
    urls = [c.url for c in cands]
    assert "https://example.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_9&fileSn=0" in urls
    assert not any(u.endswith("공고문.hwp") for u in urls)   # onclick 인자 → URL 날조 금지


@respx.mock
def test_download_rejects_html_even_with_doc_ext_url(tmp_path):
    """죽은 .hwp 직링크가 200 HTML(soft-404)을 줘도 파일로 저장하지 않는다."""
    url = "https://example.go.kr/files/old_notice.hwp"
    respx.get(url).mock(return_value=httpx.Response(
        200, headers={"content-type": "application/octet-stream"},
        content=b"<!DOCTYPE html><html><body>404 not found</body></html>"))
    cand = AttachmentCandidate(url=url, label="공고문.hwp", source="href")
    with pytest.raises(RuntimeError):
        download_attachment(cand, "https://example.go.kr/view.do", tmp_path, 1)


@respx.mock
def test_kamco_process_url_end_to_end(tmp_path):
    """캠코 상세 → 첨부 3개 다운로드·제목 폴더·오탐 0 의 전 구간 회귀."""
    from scripts.fetch_notice_attachments import process_url

    respx.get(KAMCO_URL).mock(return_value=httpx.Response(200, html=_kamco_html()))
    names = [
        "1.(공고문)2026년 KAMCO Startup TechBlaze 모집공고.hwp",
        "2.(제출서류 양식1)2026년 KAMCO Startup TechBlaze 신청서_모집부문1_(예비)창업가.hwp",
        "3.(제출서류 양식2)2026년 KAMCO Startup TechBlaze 신청서_모집부문2_전국민 아이디어 제안.hwp",
    ]
    for sn, real in enumerate(names):
        cd_bytes = b'attachment; filename="' + real.encode("cp949") + b'"'
        respx.get(
            "https://www.kamco.or.kr/cmm/fms/FileDown.do"
            f"?atchFileId=FILE_000000000013068&fileSn={sn}"
        ).mock(return_value=httpx.Response(
            200,
            headers=[(b"content-type", b"application/x-msdownload;charset=UTF-8"),
                     (b"content-disposition", cd_bytes)],
            content=b"\xd0\xcf\x11\xe0HWP" + str(sn).encode()))

    results = process_url(KAMCO_URL, tmp_path, dry_run=False)
    # footer 인증 PDF 가 후보로 부활하면 respx 미등록 요청이 except 에 삼켜져
    # DOWNLOAD_FAILED 로 results 에 남는다 — 상태 전수 단언으로 오탐 0 을 고정한다.
    assert [r.status for r in results] == ["DOWNLOADED"] * 3
    downloaded = results
    assert {r.file_name for r in downloaded} == set(names)
    assert all(r.notice_title == "「2026 KAMCO Startup TechBlaze」 개최 안내" for r in results)
    folder = Path(downloaded[0].save_path).parent
    assert folder.name.endswith("「2026 KAMCO Startup TechBlaze」 개최 안내")
    assert len(list(folder.iterdir())) == 3


# ---------- 6) --notify 팝업(실패해도 CLI 계속) ----------

def test_try_notify_popup_no_crash(monkeypatch):
    from scripts.fetch_notice_attachments import _try_notify_popup

    monkeypatch.setattr(
        "scripts.fetch_notice_attachments.Path.home",
        lambda: Path("/nonexistent"),
    )
    _try_notify_popup("테스트")  # 스크립트 없으면 조용히 return


def test_notify_download_done_calls_popup(monkeypatch, tmp_path):
    from scripts.fetch_notice_attachments import _notify_download_done

    calls: list[str] = []
    monkeypatch.setattr(
        "scripts.fetch_notice_attachments._try_notify_popup",
        lambda m: calls.append(m),
    )
    _notify_download_done(3, 1, tmp_path)
    assert calls and "3개" in calls[0]


def test_main_notify_gate_uses_downloaded_status(monkeypatch, tmp_path):
    """--notify 게이트는 counts['DOWNLOADED'] 를 본다 — 'OK' 로 회귀하면 팝업 영구 미발동."""
    import scripts.fetch_notice_attachments as fna

    def fake_handle(url, out_dir, dry_run, open_flag, opened_dirs, all_results):
        all_results.append(fna.FileResult(
            notice_title="티", detail_url=url, status="DOWNLOADED",
            file_name="a.hwp", save_path=str(out_dir / "01_티" / "a.hwp")))

    notified: list[int] = []
    monkeypatch.setattr(fna, "_handle_url", fake_handle)
    monkeypatch.setattr(fna, "_notify_download_done", lambda ok, n, d: notified.append(ok))
    monkeypatch.setattr(sys, "argv", [
        "prog", "https://example.go.kr/view.do?idx=9",
        "--out-dir", str(tmp_path), "--notify", "--quiet"])
    assert fna.main() == 0
    assert notified == [1]
