"""Regression: Streamlit site-type selectbox must not coerce dedicated collectors.

Bug: SITE_TYPES omitted nipa_html/mss_html/kosme_api/… so selectbox index fell
back to 0 (bizinfo_api). Saving a source without changing the type permanently
rewrote type→bizinfo_api → wrong fetcher → permanent silent miss for that board.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_streamlit_helpers():
    """Import helpers without executing Streamlit UI side effects.

    streamlit_app.py runs init_defaults / st.set_page_config at import time, so
    we extract the pure helpers via AST for a lightweight unit test.
    """
    src = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    wanted = {"SITE_TYPES", "site_type_choices", "site_type_label"}
    ns: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SITE_TYPES":
                    ns["SITE_TYPES"] = ast.literal_eval(node.value)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            code = compile(ast.Module(body=[node], type_ignores=[]), "streamlit_app.py", "exec")
            exec(code, ns)  # noqa: S102 — test-only extract of pure helpers
    # site_type_* close over SITE_TYPES name from their globals
    ns["site_type_choices"].__globals__["SITE_TYPES"] = ns["SITE_TYPES"]
    ns["site_type_label"].__globals__["SITE_TYPES"] = ns["SITE_TYPES"]
    return ns


def test_site_type_choices_keeps_unknown_current_type_at_index_zero():
    helpers = _load_streamlit_helpers()
    choices = helpers["site_type_choices"]("future_collector_xyz")
    assert choices[0] == "future_collector_xyz"
    assert "bizinfo_api" in choices
    # Simulated pre-fix selectbox: unknown type ∉ SITE_TYPES → index 0 was bizinfo_api
    legacy_keys = [k for k in helpers["SITE_TYPES"] if k != "future_collector_xyz"]
    assert "future_collector_xyz" not in legacy_keys or True
    coerced_idx = 0  # old bug: type_keys.index(missing) fallback
    assert legacy_keys[coerced_idx] == "bizinfo_api"
    # New helper selects the real on-disk type
    assert choices.index("future_collector_xyz") == 0


def test_site_types_covers_all_enabled_sites_json_types():
    helpers = _load_streamlit_helpers()
    sites = json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))
    missing = sorted({
        str(s.get("type") or "")
        for s in sites
        if s.get("enabled") and str(s.get("type") or "") not in helpers["SITE_TYPES"]
    } - {""})
    assert missing == [], f"SITE_TYPES missing enabled collectors: {missing}"


def test_site_types_covers_monitor_fetchers_except_playwright():
    """Dedicated FETCHERS keys (non-pw_*) must appear in the dashboard map."""
    helpers = _load_streamlit_helpers()
    # Avoid importing monitor (env-gated). Parse FETCHERS keys from source.
    mon = (ROOT / "monitor.py").read_text(encoding="utf-8")
    start = mon.index("FETCHERS = {")
    end = mon.index("\n}", start)
    block = mon[start:end]
    keys = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("FETCHERS"):
            continue
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip().strip('"').strip("'")
        if key.startswith("pw_"):
            continue
        keys.append(key)
    missing = sorted(k for k in keys if k not in helpers["SITE_TYPES"])
    assert missing == [], f"SITE_TYPES missing FETCHERS: {missing}"


def test_site_type_label_falls_back_to_raw_key():
    helpers = _load_streamlit_helpers()
    assert helpers["site_type_label"]("bizinfo_api") == helpers["SITE_TYPES"]["bizinfo_api"]
    assert helpers["site_type_label"]("not_in_map_yet") == "not_in_map_yet"
