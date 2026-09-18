"""rule_version — MAIL-P0D-03: 규칙 변경 후 과거 판정 재현을 위한 rule_version·config_snapshot_id.

evaluate_notice()의 판정 로직(EXCLUSION_RULES 등 규칙을 정의하는 소스 코드)과, 판정에 쓰인
그룹 설정(키워드·지역 조건)을 각각 짧은 해시로 식별한다. 같은 fixture를 같은 rule_version +
같은 config_snapshot_id 로 재평가하면 항상 같은 결과가 나온다 — 규칙이 바뀌면(rule_version이
바뀌면) 과거 판정과 현재 판정을 구분해 비교할 수 있다.

Secrets·수신자 이메일 등 개인정보·비식별 무관 필드는 해시 입력에 절대 포함하지 않는다
(FORBIDDEN: 전체 설정파일 복제 / 개인정보 스냅샷).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# 그룹 설정 중 "판정 로직에 실제로 쓰이는" 필드만 스냅샷 대상으로 삼는다.
# recipients(수신자 이메일)·name·id 등은 판정과 무관하거나 개인정보라 절대 포함하지 않는다.
_SAFE_GROUP_KEYS = (
    "or_keywords",
    "and_keyword_groups",
    "exclude_keywords",
    "priority_keywords",
    "applicant_region_city",
    "applicant_region_district",
    "required_conditions",
)


def compute_version_hash(*parts: str) -> str:
    """여러 소스 조각(함수 소스·규칙 테이블 repr 등)을 합쳐 짧은(16자) sha256 식별자를 만든다."""
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def config_snapshot_id(group: dict[str, Any] | None) -> str:
    """판정에 쓰인 그룹 설정만 골라 해시로 식별한다(개인정보·무관 필드 제외)."""
    g = group or {}
    safe = {k: g.get(k) for k in _SAFE_GROUP_KEYS if k in g}
    raw = json.dumps(safe, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def diff_versions(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """변경 전후 두 판정결과(evaluate_notice 반환값)를 rule_version 관점에서 비교한다.

    같은 rule_version·config_snapshot_id 인데 is_relevant/exclude_reason_codes 가
    달라지면 비결정적 버그(재현성 위반)라는 신호다 — 그 경우를 최우선으로 드러낸다.
    """
    same_version = (
        before.get("rule_version") == after.get("rule_version")
        and before.get("config_snapshot_id") == after.get("config_snapshot_id")
    )
    changed_fields = {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in ("is_relevant", "exclude_reason_codes", "notice_type", "target_type")
        if before.get(field) != after.get(field)
    }
    return {
        "rule_version_before": before.get("rule_version"),
        "rule_version_after": after.get("rule_version"),
        "config_snapshot_before": before.get("config_snapshot_id"),
        "config_snapshot_after": after.get("config_snapshot_id"),
        "same_rule_and_config": same_version,
        "nondeterministic": same_version and bool(changed_fields),
        "changed_fields": changed_fields,
    }
