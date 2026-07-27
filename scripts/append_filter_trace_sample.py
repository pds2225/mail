#!/usr/bin/env python3
"""filter_trace 샘플 1행을 로컬 JSONL(+설정 시 Google Sheet)에 누적."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations.filter_trace import build_trace  # noqa: E402
from mail_core.storage.filter_trace_sheet import accumulate_traces, sheet_configured  # noqa: E402


def main() -> int:
    trace = build_trace(
        notice_id="bizinfo_SAMPLE_001",
        group_id="grp_ai_saas",
        site_id="bizinfo",
        core=True,
        title="생성형AI SaaS 사업화 지원 (샘플)",
        bucket="included",
        stages=[
            {"step": "extract", "ok": True, "status": "SUCCESS", "reasons": []},
            {"step": "hard_exclude", "ok": True, "reasons": []},
            {
                "step": "region",
                "ok": True,
                "status": "NOT_SPECIFIED",
                "reasons": ["APPLICANT_SCOPE_UNSTATED"],
            },
            {
                "step": "keyword",
                "ok": True,
                "status": "STRONG",
                "reasons": ["OR_HIT:AI", "OR_HIT:SaaS"],
            },
            {
                "step": "track",
                "ok": True,
                "status": "MAIN",
                "reasons": ["CORE_STRONG_UNSPECIFIED"],
            },
        ],
    )
    result = accumulate_traces([trace])
    print(json.dumps({"trace_context": trace["context"], **result, "sheet_configured": sheet_configured()}, ensure_ascii=False, indent=2))
    return 0 if result.get("sheet", {}).get("ok") or result.get("jsonl_path") else 1


if __name__ == "__main__":
    raise SystemExit(main())
