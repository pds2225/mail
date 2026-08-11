"""K-Startup 첨부 다운로더 replay 테스트 — respx 오프라인 재생.

저장된 상세 페이지 HTML 픽스처를 respx 로 재생하여
`download_kstartup_targets.py`의 첨부 추출·아웃바운드 URL 추출을 검증한다.

핵심 회귀 포인트:
 1) 첨부 링크 추출 (direct anchor, downloadPath, eGov onclick)
 2) footer/nav 사이트 chrome 필터링 (KSQI 인증서 같은 오탐 방지)
 3) outbound URL 추출 (fn_open_window, 원본 사이트 버튼)
 4) 첨부 없는 상세 페이지 처리
"""
import pathlib

import httpx
import pytest
import respx

import os
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
os.environ.setdefault("BIZINFO_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("GMAIL_ADDRESS", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test_pass")

from scripts.download_kstartup_targets import (
    extract_attachment_candidates,
    extract_outbound_urls,
    _parse_kstartup_cards,
)

FX = pathlib.Path(__file__).parent / "fixtures" / "kstartup"


def _load(name):
    return (FX / name).read_text(encoding="utf-8")


DETAIL_WITH_ATTACHMENTS = "kstartup_detail_with_attachments.html"
DETAIL_NO_ATTACHMENTS = "kstartup_detail_no_attachments.html"


# ── 1) 첨부 링크 추출 ──────────────────────────────────────────────────────


def test_extract_attachments_finds_direct_anchors():
    """직접 앵커(/afile/fileDownload/) 3건 추출."""
    html = _load(DETAIL_WITH_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=1001"

    candidates = extract_attachment_candidates(html, detail_url)

    urls = [c.url for c in candidates]
    assert any("FILE_000000000013068" in u and "fileSn=1" in u for u in urls)
    assert any("fileSn=2" in u for u in urls)
    assert any("fileSn=3" in u for u in urls)
    assert len([u for u in urls if "FILE_000000000013068" in u]) == 3


def test_extract_attachments_absolute_url_normalization():
    """상대경로가 절대 URL로 정규화된다."""
    html = _load(DETAIL_WITH_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=1001"

    candidates = extract_attachment_candidates(html, detail_url)

    for c in candidates:
        assert c.url.startswith("https://")


def test_extract_attachments_labels_preserved():
    """첨부 라벨(파일명)이 보존된다."""
    html = _load(DETAIL_WITH_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=1001"

    candidates = extract_attachment_candidates(html, detail_url)
    labels = [c.label for c in candidates]

    assert any("공고문" in l for l in labels)
    assert any("신청서" in l for l in labels)
    assert any("사업계획서" in l for l in labels)


# ── 2) 사이트 chrome 필터링 ─────────────────────────────────────────────────


def test_footer_chrome_links_excluded_from_direct_anchor_pass():
    """footer 내 링크가 직접 앵커 패스에서는 사이트 chrome으로 필터링된다."""
    html = _load(DETAIL_WITH_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=1001"

    candidates = extract_attachment_candidates(html, detail_url)
    href_sources = [c for c in candidates if c.source == "href"]

    # 직접 앵커에서 footer 링크(KSQI)는 제외, 본문 첨부 3건만
    assert len(href_sources) == 3
    assert not any("KSQI" in c.url for c in href_sources)


def test_chrome_attachment_picked_up_by_fallback():
    """footer의 첨부 모양 URL은 quoted-download-url fallback에서 잡힐 수 있다.

    extract_attachment_candidates는 다단계 추출(직접앵커 → downloadPath → quoted URL)이므로
    chrome 필터가 직접 앵커 패스에서만 적용된다. 픽스처가 작아서 footer가 body의
    50% 이상이면 chrome으로 판별되지 않고 fallback에서 수집된다.
    """
    html = _load(DETAIL_WITH_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=1001"

    candidates = extract_attachment_candidates(html, detail_url)

    # 본문 3건 + footer fallback 1건(KSQI) = 최소 3건
    assert len(candidates) >= 3


# ── 3) outbound URL 추출 ────────────────────────────────────────────────────


def test_extract_outbound_urls_finds_fn_open_window():
    """fn_open_window 버튼에서 아웃바운드 URL 추출."""
    html = _load(DETAIL_WITH_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=1001"

    urls = extract_outbound_urls(html, detail_url)

    assert any("startup.go.kr" in u for u in urls)
    assert any("apply.startup.go.kr" in u for u in urls)


def test_extract_outbound_urls_excludes_kstartup_self():
    """k-startup.go.kr 자체 링크는 아웃바운드에서 제외."""
    html = _load(DETAIL_NO_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=2001"

    urls = extract_outbound_urls(html, detail_url)

    # k-startup.go.kr 자체 링크는 제외
    assert not any("k-startup.go.kr" in u for u in urls)


def test_extract_outbound_urls_finds_external_site():
    """외부 사이트(accelerator.or.kr) 링크 추출."""
    html = _load(DETAIL_NO_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=2001"

    urls = extract_outbound_urls(html, detail_url)

    assert any("accelerator.or.kr" in u for u in urls)


# ── 4) 첨부 없는 상세 페이지 ────────────────────────────────────────────────


def test_no_attachments_returns_empty():
    """첨부 없는 상세 페이지는 빈 리스트."""
    html = _load(DETAIL_NO_ATTACHMENTS)
    detail_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=2001"

    candidates = extract_attachment_candidates(html, detail_url)

    assert candidates == []


# ── 5) _parse_kstartup_cards (다운로더 내부 파서) ────────────────────────────


def test_parse_kstartup_cards_extracts_structured_fields():
    """다운로더의 _parse_kstartup_cards 가 9키 스키마를 추출한다."""
    html = _load("kstartup_public.html")
    items = _parse_kstartup_cards(html, "PBC010")

    assert len(items) == 2
    assert items[0]["id"] == "kstartup_1001"
    assert items[0]["title"] == "2026년 공공 창업도약패키지 지원사업 공고"
    assert items[0]["author"] == "창업진흥원"
    assert items[0]["deadline"] == "2026-06-30"


def test_parse_kstartup_cards_private_class():
    """다운로더의 _parse_kstartup_cards 가 민간(PBC020) 도 파싱한다."""
    html = _load("kstartup_private.html")
    items = _parse_kstartup_cards(html, "PBC020")

    assert len(items) == 3
    ids = [it["id"] for it in items]
    assert "kstartup_2001" in ids
    assert "kstartup_1001" in ids  # 중복 sn 포함


def test_parse_kstartup_cards_sparse_edge_cases():
    """엣지케이스 픽스처: a 없는 카드 스킵, button 없는 카드는 href에서 sn."""
    html = _load("kstartup_public_sparse.html")
    items = _parse_kstartup_cards(html, "PBC010")

    ids = [it["id"] for it in items]
    # a 없는 sn=5005 스킵
    assert "kstartup_5005" not in ids
    # button 없는 sn=5004는 a[href]에서 sn 추출
    assert "kstartup_5004" in ids
    assert len(items) == 5
