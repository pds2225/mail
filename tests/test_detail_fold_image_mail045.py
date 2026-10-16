from datetime import date
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

import monitor as mon
from mail_core.operations.detail_runtime_adapter import extract_body_candidate
from mail_core.operations.field_status import should_force_review_for_extraction
from mail_core.delivery.digest_table import parse_plain_table, render_html_blocks
from mail_core.delivery.digest_lint import lint_digest


def notice():
    return {"id": "fold-fixture", "title": "전국 제조기업 성장지원 사업 참여기업 모집",
            "description": "", "deadline": "", "posted_date": "2026-10-16",
            "link": "https://www.nipa.kr/notice/fixture", "author": "지원기관"}


@pytest.mark.parametrize("attributes", ['hidden', 'style="display: none"',
    'aria-expanded="false"', 'class="more"'])
def test_hidden_support_reaches_money_line(attributes, monkeypatch):
    html = f'''<div class="detail"><p>지원대상: 전국 제조기업</p>
        <div {attributes}>지원내용: 시제품 제작비 최대 2천만원 지원</div>
        <button>더보기</button><script>비밀 잡텍스트 9억원</script><style>잡스타일</style></div>'''
    monkeypatch.setattr(mon, "_http_get", lambda *a, **k: SimpleNamespace(text=html))
    enriched = mon.enrich_item_from_detail(notice())
    assert "2천만원" in enriched["description"]
    assert "잡텍스트" not in enriched["description"] and "잡스타일" not in enriched["description"]
    assert "더보기" not in enriched["description"]
    body = mon.fallback_body([enriched], today=date(2026, 10, 16))
    assert "💰" in body and "2천만원" in body
    assert lint_digest("[공고] 1건", body)["ok"]


@pytest.mark.parametrize("host,container", [("www.nipa.kr", 'class="detail"'),
    ("www.k-startup.go.kr", 'id="contentViewHtml"'),
    ("www.bizinfo.go.kr", 'class="view_cont"'),
    ("example.test", 'class="board_view"')])
def test_image_only_has_review_status_without_junk_or_fake_metadata(host, container, monkeypatch):
    html = f'<header><img src="logo.png">메뉴</header><div {container}><button>더보기</button><img src="notice.png"></div>'
    monkeypatch.setattr(mon, "_http_get", lambda *a, **k: SimpleNamespace(text=html))
    enriched = mon.enrich_item_from_detail({**notice(), "link": f"https://{host}/notice/fixture"})
    assert enriched["body_status"] == "IMAGE_ONLY"
    assert enriched["detail_extraction"]["reason"] == "image_only_detail"
    assert should_force_review_for_extraction(enriched)
    assert enriched["detail_extraction"]["fields"]["application_period"]["status"] == "PARSE_FAILED"
    row = mon._digest_row(enriched, today=date(2026, 10, 16))
    body = mon.fallback_body([enriched], today=date(2026, 10, 16))
    assert row["마감"] == "확인필요" and not row["지원내용"]
    assert "💰" not in body and "더보기" not in body and "메뉴" not in body
    assert parse_plain_table(body)[1][0]["마감"] == "확인필요"
    assert "확인필요" in render_html_blocks([row])
    assert lint_digest("[공고] 1건", body)["ok"]


def test_body_logo_does_not_make_long_text_image_only():
    soup = BeautifulSoup('<article><img src="logo.png"><p>' + '지원사업 상세 안내문입니다. ' * 12 + '</p></article>', 'html.parser')
    assert extract_body_candidate(soup.article)["body_status"] == "TEXT"


def test_header_image_is_not_a_body_image(monkeypatch):
    html = '<header><img src="logo.png"></header><article>본문이 없습니다.</article>'
    fields = mon._parse_detail_from_page(BeautifulSoup(html, "html.parser"), "https://example.test/notice")
    assert fields.get("body_status") != "IMAGE_ONLY"


def test_extraction_does_not_mutate_original_dom():
    soup = BeautifulSoup('<article><div hidden>지원내용 100만원</div><script>ignored</script></article>', 'html.parser')
    before = str(soup)
    extract_body_candidate(soup.article)
    assert str(soup) == before


def test_explicit_more_target_outside_body_is_included(monkeypatch):
    html = '<div class="detail"><p>전국 기업 대상</p><button aria-expanded="false" aria-controls="more-body">더보기</button></div><div id="more-body" hidden>지원내용: 시제품 제작비 최대 2천만원 지원</div>'
    monkeypatch.setattr(mon, "_http_get", lambda *a, **k: SimpleNamespace(text=html))
    enriched = mon.enrich_item_from_detail(notice())
    assert enriched["description"].count("2천만원") == 1
    assert "2천만원" in mon.fallback_body([enriched], today=date(2026, 10, 16))


def test_missing_dynamic_more_target_requires_review(monkeypatch):
    html = '<div class="detail"><p>일부 본문만 표시됨</p><button aria-expanded="false" aria-controls="not-loaded">더보기</button></div>'
    monkeypatch.setattr(mon, "_http_get", lambda *a, **k: SimpleNamespace(text=html))
    enriched = mon.enrich_item_from_detail(notice())
    assert enriched["body_status"] == "FOLDED_INCOMPLETE"
    assert should_force_review_for_extraction(enriched)
    assert mon._mail_deadline_cell(enriched, date(2026, 10, 16)) == "확인필요"


def test_image_only_status_is_persisted_in_raw_meta(tmp_path):
    import json
    from mail_core.storage.raw_store import RawStore
    store = RawStore(root=tmp_path, run_day=date(2026, 10, 16))
    path = store.save_item_meta({**notice(), "body_status": "IMAGE_ONLY"})
    assert json.loads(path.read_text(encoding="utf-8"))["body_status"] == "IMAGE_ONLY"
