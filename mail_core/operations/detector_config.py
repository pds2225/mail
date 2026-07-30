"""사이트별 누락 탐지 설정 로더 (순수·monitor import 없음).

config/detector_sites.json 의 defaults + sites 오버라이드를 병합해
coverage_alert.classify_source_status(thresholds=...) 에 넣을 dict 를 만든다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mail_core.paths import CONFIG_DIR

DETECTOR_SITES_PATH = CONFIG_DIR / "detector_sites.json"

# classify DEFAULT_THRESHOLDS 와 키가 겹치는 항목만 thresholds 로 전달한다.
_THRESHOLD_KEYS = frozenset({
    "drop_ratio_p0",
    "drop_ratio_p1",
    "date_parse_min_rate",
    "date_parse_drop_pp",
    "detail_link_min_rate",
    "valid_record_min_rate",
    "suspicious_content_max_rate",
    "spike_ratio_p1",
    "spike_absolute_excess",
    "baseline_min_runs",
    "baseline_window_runs",
})


def load_detector_config(path: Path | None = None) -> dict[str, Any]:
    """detector_sites.json 로드. 없거나 깨지면 빈 defaults/sites."""
    target = path or DETECTOR_SITES_PATH
    try:
        if not target.exists():
            return {"defaults": {}, "sites": {}}
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"defaults": {}, "sites": {}}
        defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
        sites = data.get("sites") if isinstance(data.get("sites"), dict) else {}
        return {"defaults": dict(defaults), "sites": dict(sites)}
    except Exception:
        return {"defaults": {}, "sites": {}}


def site_policy(cfg: dict[str, Any] | None, site_id: str) -> dict[str, Any]:
    """defaults ← site override 병합 (정책 전체)."""
    cfg = cfg if isinstance(cfg, dict) else {}
    merged = dict(cfg.get("defaults") or {})
    site_over = (cfg.get("sites") or {}).get(site_id) or {}
    if isinstance(site_over, dict):
        merged.update(site_over)
    return merged


def thresholds_for_site(cfg: dict[str, Any] | None, site_id: str) -> dict[str, float]:
    """classify_source_status 에 넘길 thresholds 만 추출 (숫자 키)."""
    policy = site_policy(cfg, site_id)
    out: dict[str, float] = {}
    for key in _THRESHOLD_KEYS:
        if key not in policy:
            continue
        try:
            out[key] = float(policy[key])
        except (TypeError, ValueError):
            continue
    # drop_threshold(급감 비율 0.8) → drop_ratio_p0(잔존비 0.2) 변환 힌트
    if "drop_ratio_p0" not in out and "drop_threshold" in policy:
        try:
            drop = float(policy["drop_threshold"])
            if 0.0 < drop < 1.0:
                out["drop_ratio_p0"] = 1.0 - drop
        except (TypeError, ValueError):
            pass
    return out


def zero_item_policy_for_site(cfg: dict[str, Any] | None, site_id: str) -> str:
    """사이트별 0건 정책. 허용: p0_if_baseline / p0_always / warning / ignore_zero."""
    value = str(site_policy(cfg, site_id).get("zero_item_policy") or "p0_if_baseline")
    if value not in {"p0_if_baseline", "p0_always", "warning", "ignore_zero"}:
        return "p0_if_baseline"
    return value


def fetch_failed_risk_for_site(cfg: dict[str, Any] | None, site_id: str) -> str:
    """접속 실패(FETCH_FAILED) 등급. P0|P1 (기본 P0 — 미설정 시 보수적).

    지역·imported(imp_*) 소스의 만성 TLS/접속 실패가 매일 P0 37건 알림을
    만들던 사고(2026-07-26) 대응: defaults 를 P1 로 두고 핵심 소스만 P0.
    """
    value = str(site_policy(cfg, site_id).get("fetch_failed_risk") or "P0").upper()
    if value not in {"P0", "P1"}:
        return "P0"
    return value
