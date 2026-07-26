"""K-Startup 수집 정책 — 페이지·중복·공공우선 (순수 로직).

실측(2026-07-26):
  - 페이지 파라미터는 `page` (`pageIndex`/`currentPage` 무효)
  - 페이지당 ~15건 고정(viewCount=100 무시)
  - 공공(PBC010) ~15페이지/225건, 민간(PBC020) ~4페이지/50건
  - 끝단은 빈 HTML이 아니라 '카드 1건·신규 0' 잔여 페이지가 나옴
    → 신규 0 연속 2회면 종료(중복 루프·잔여 페이지 모두 흡수)

정책:
  1) 공공 먼저 전량, 민간은 후순위(더 작은 페이지 상한)
  2) sn 전역 중복 제거(공공에 이미 있으면 민간에서 스킵)
  3) max_pages 는 안전캡 — 실제 종료는 신규0 연속
"""
from __future__ import annotations

from typing import Any

# 수집 순서 = 우선순위 (공공 → 민간)
KSTARTUP_CLASS_ORDER: tuple[dict[str, Any], ...] = (
    {"clss": "PBC010", "label": "공공", "priority": 0},
    {"clss": "PBC020", "label": "민간", "priority": 1},
)

DEFAULT_VIEW_COUNT = 15
DEFAULT_PUBLIC_MAX_PAGES = 30   # 실측 15p + 여유(목록 증가 대비)
DEFAULT_PRIVATE_MAX_PAGES = 10  # 실측 4p + 여유, 후순위라 짧게
DEFAULT_EMPTY_NEW_STREAK = 2    # 신규 0 연속 N회 → 종료


def page_param_name() -> str:
    """서버가 실제로 읽는 페이지 키. pageIndex 금지."""
    return "page"


def forbidden_page_params() -> frozenset[str]:
    return frozenset({"pageIndex", "currentPage", "pageNo"})


def build_list_params(
    *,
    page: int,
    clss: str,
    view_count: int = DEFAULT_VIEW_COUNT,
    status: str = "ing",
) -> dict[str, str]:
    """목록 요청 파라미터. pageIndex 를 절대 넣지 않는다."""
    return {
        "schMenuId": "10090",
        page_param_name(): str(int(page)),
        "viewCount": str(int(view_count)),
        "pbancSttus": status,
        "pbancClssCd": str(clss),
    }


def class_plan(site: dict | None = None) -> list[dict[str, Any]]:
    """사이트 설정 → 분류별 수집 계획(공공 먼저)."""
    site = site if isinstance(site, dict) else {}
    # 하위호환: max_pages 만 있으면 공공 상한으로 사용(민간은 별도 기본)
    legacy = int(site.get("max_pages") or 0)
    public_max = int(
        site.get("max_pages_public")
        or (legacy if legacy > 0 else DEFAULT_PUBLIC_MAX_PAGES)
    )
    private_max = int(
        site.get("max_pages_private")
        or min(DEFAULT_PRIVATE_MAX_PAGES, public_max)
    )
    view_count = int(site.get("view_count") or DEFAULT_VIEW_COUNT)
    streak = int(site.get("empty_new_streak") or DEFAULT_EMPTY_NEW_STREAK)
    plan: list[dict[str, Any]] = []
    for spec in KSTARTUP_CLASS_ORDER:
        clss = spec["clss"]
        max_pages = public_max if clss == "PBC010" else private_max
        plan.append({
            **spec,
            "max_pages": max(1, max_pages),
            "view_count": max(1, view_count),
            "empty_new_streak": max(1, streak),
        })
    # priority 오름차순 고정(공공=0 먼저)
    plan.sort(key=lambda x: int(x.get("priority", 99)))
    return plan


def stop_reason_after_page(
    *,
    page: int,
    max_pages: int,
    raw_count: int,
    new_count: int,
    empty_new_streak: int,
    streak_limit: int,
) -> str | None:
    """한 페이지 처리 후 종료 사유. None 이면 계속.

    - FETCH 결과는 호출측에서 처리
    - raw_count==0: 진짜 빈 페이지 → streak 증가와 동일하게 취급(호출측이 streak 갱신)
    - new_count==0: 중복만 / 잔여 고스트 페이지
    - empty_new_streak >= limit: 종료
    - page >= max_pages: 안전캡
    """
    if empty_new_streak >= streak_limit:
        return "EMPTY_NEW_STREAK"
    if page >= max_pages:
        return "MAX_PAGES_HIT"
    # 힌트용(종료는 streak/max 가 담당). raw>0 & new==0 은 잔여/루프.
    _ = (raw_count, new_count)
    return None


def merge_unique_items(
    collected: list[dict],
    page_items: list[dict],
    seen_ids: set[str],
) -> tuple[list[dict], int]:
    """페이지 결과를 전역 seen 기준으로 합친다. (추가된 리스트, 신규 건수)."""
    added: list[dict] = []
    for it in page_items or []:
        iid = str((it or {}).get("id") or "")
        if not iid or iid in seen_ids:
            continue
        seen_ids.add(iid)
        added.append(it)
    collected.extend(added)
    return added, len(added)
