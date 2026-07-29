from bs4 import BeautifulSoup

from mail_core.operations.detail_runtime_adapter import (
    KSTARTUP_LEGACY_SELECTOR,
    install_kstartup_body_selector_adapter,
    install_priority_detail_hosts_adapter,
)


def test_kstartup_current_dom_replaces_tiny_legacy_match():
    install_kstartup_body_selector_adapter()
    body = (
        "신청방법 및 대상 신청기간 2026-07-01부터 2026-08-01까지 "
        "서울 소재 인공지능 예비창업자를 대상으로 사업화 자금과 교육을 지원합니다. "
        "신청대상과 지원내용을 상세히 확인해 주시기 바랍니다."
    )
    soup = BeautifulSoup(
        f"""
        <html><body>
          <div class="view_cont">사업화</div>
          <div id="contentViewHtml"><div class="app_notice_details-wrap">{body}</div></div>
        </body></html>
        """,
        "html.parser",
    )
    selected = soup.select_one(KSTARTUP_LEGACY_SELECTOR)
    assert selected is not None
    assert "인공지능 예비창업자" in selected.get_text(" ", strip=True)
    assert len(selected.get_text(" ", strip=True)) >= 80


def test_existing_full_legacy_body_is_preserved():
    install_kstartup_body_selector_adapter()
    legacy = "기존 상세 본문 " * 20
    current = "현재 DOM 본문 " * 20
    soup = BeautifulSoup(
        f"""
        <html><body>
          <div class="view_cont">{legacy}</div>
          <div id="contentViewHtml">{current}</div>
        </body></html>
        """,
        "html.parser",
    )
    selected = soup.select_one(KSTARTUP_LEGACY_SELECTOR)
    assert selected is not None
    assert "기존 상세 본문" in selected.get_text(" ", strip=True)


def test_priority_hosts_extend_monitor_runtime_without_replacing_existing():
    runtime_globals = {
        "DETAIL_ENRICH_HOSTS": (
            "exportvoucher.com",
            "k-startup.go.kr",
            "nipa.kr",
            "bizinfo.go.kr",
        ),
    }

    assert install_priority_detail_hosts_adapter(runtime_globals) is True
    assert runtime_globals["DETAIL_ENRICH_HOSTS"] == (
        "exportvoucher.com",
        "k-startup.go.kr",
        "nipa.kr",
        "bizinfo.go.kr",
        "kita.net",
    )
    assert install_priority_detail_hosts_adapter(runtime_globals) is False
