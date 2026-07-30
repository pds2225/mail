"""운영 엔트리포인트용 상세본문 DOM 호환 어댑터.

보호 파일인 monitor.py를 수정하지 않고도 K-Startup의 2026년 현재 DOM
(``#contentViewHtml``)을 기존 상세 파서가 읽고, KITA가 같은 전용 상세호스트
판정을 사용하게 한다. 기존 selector와 호스트는 그대로 보존한다.
"""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

KSTARTUP_LEGACY_SELECTOR = ".view_cont, .content_view, #contents"
KSTARTUP_CURRENT_SELECTOR = (
    "#contentViewHtml, .app_notice_details-wrap, .content_wrap"
)
MIN_BODY_TEXT_CHARS = 80


def _text_len(node: Any) -> int:
    if node is None:
        return 0
    try:
        return len(" ".join(node.get_text(" ", strip=True).split()))
    except Exception:
        return 0


def install_kstartup_body_selector_adapter() -> bool:
    """BeautifulSoup의 해당 결합 selector만 현재 DOM fallback으로 보강.

    같은 프로세스에서 여러 번 호출해도 한 번만 설치한다.
    """
    from bs4.element import Tag

    if getattr(Tag, "_mail_kstartup_body_adapter_installed", False):
        return False

    original = Tag.select_one

    def select_one_with_current_kstartup_dom(
        self: Any,
        selector: str,
        namespaces: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        found = original(self, selector, namespaces=namespaces, **kwargs)
        if selector != KSTARTUP_LEGACY_SELECTOR or _text_len(found) >= MIN_BODY_TEXT_CHARS:
            return found
        current = original(
            self,
            KSTARTUP_CURRENT_SELECTOR,
            namespaces=namespaces,
            **kwargs,
        )
        return current if _text_len(current) >= MIN_BODY_TEXT_CHARS else found

    Tag.select_one = select_one_with_current_kstartup_dom
    Tag._mail_kstartup_body_adapter_installed = True
    Tag._mail_kstartup_body_adapter_original = original
    return True


def install_priority_detail_hosts_adapter(
    runtime_globals: MutableMapping[str, Any],
) -> bool:
    """monitor 런타임의 전용호스트를 4대 핵심소스 기준으로 정렬."""
    from mail_core.matching.core_sources import PRIORITY_DETAIL_HOSTS

    current = tuple(runtime_globals.get("DETAIL_ENRICH_HOSTS") or ())
    updated = tuple(dict.fromkeys((*current, *PRIORITY_DETAIL_HOSTS)))
    if updated == current:
        return False
    runtime_globals["DETAIL_ENRICH_HOSTS"] = updated
    return True
