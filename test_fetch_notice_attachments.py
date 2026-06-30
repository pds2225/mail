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

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")

from scripts.fetch_notice_attachments import (  # noqa: E402
    AttachmentCandidate,
    _looks_like_html_body,
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
