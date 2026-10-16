"""운영 엔트리포인트용 상세본문 DOM 호환 어댑터.

보호 파일인 monitor.py를 수정하지 않고도 K-Startup의 2026년 현재 DOM
(``#contentViewHtml``)을 기존 상세 파서가 읽고, KITA가 같은 전용 상세호스트
판정을 사용하게 한다. 기존 selector와 호스트는 그대로 보존한다.
"""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any
import re

KSTARTUP_LEGACY_SELECTOR = ".view_cont, .content_view, #contents"
KSTARTUP_CURRENT_SELECTOR = (
    "#contentViewHtml, .app_notice_details-wrap, .content_wrap"
)
MIN_BODY_TEXT_CHARS = 80


def extract_body_candidate(node: Any) -> dict[str, Any]:
    """숨김은 CSS 표시 상태일 뿐이다. 원문 DOM의 본문을 읽고 이미지 전용을 구분한다."""
    if node is None:
        return {}
    from bs4 import BeautifulSoup
    from mail_core.operations.field_status import IMAGE_ONLY

    clone = BeautifulSoup(str(node), "html.parser")
    root = node
    while getattr(root, "parent", None) is not None:
        root = root.parent
    unresolved = False
    appended: set[str] = set()
    # 본문 밖의 접힘 영역도 명시적으로 연결된 경우에만 읽는다(메뉴 .more는 배제).
    for control in node.select("[aria-controls], [data-target]"):
        target_ids = str(control.get("aria-controls") or control.get("data-target") or "").split()
        for target_id in target_ids:
            target_id = target_id.lstrip("#")
            if not target_id or not re.fullmatch(r"[\w-]+", target_id):
                continue
            target = root.find(id=target_id)
            if target is None:
                unresolved = True
            elif target is not node and node not in target.parents and target not in node.parents and target_id not in appended:
                if target.find_parent(("nav", "header", "footer", "aside")) is None:
                    clone.append(BeautifulSoup(str(target), "html.parser"))
                    appended.add(target_id)
    for tag in clone.select("script, style, noscript, nav, header, footer, aside"):
        tag.decompose()
    folded = bool(clone.select("[hidden], [aria-expanded=false], .more")) or any(
        re.search(r"display\s*:\s*none", str(tag.get("style") or ""), re.I)
        for tag in clone.select("[style]")
    )
    for tag in clone.select("button, a[role=button]"):
        if tag.get_text(" ", strip=True) in {"더보기", "내용 더보기", "접기"}:
            tag.decompose()
    text = clone.get_text("\n", strip=True)[:12000]
    image_only = len(" ".join(text.split())) < MIN_BODY_TEXT_CHARS and bool(clone.find("img"))
    if not text and not image_only:
        return {}
    return {"body": "" if image_only else text,
            "body_status": IMAGE_ONLY if image_only else ("FOLDED_INCOMPLETE" if unresolved else "TEXT"),
            "has_folded_content": folded}


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
