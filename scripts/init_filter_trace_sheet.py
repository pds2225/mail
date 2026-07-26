#!/usr/bin/env python3
"""filter_trace 시트 탭·헤더 초기화 (+ 선택 샘플 1행).

필요:
  GOOGLE_SERVICE_ACCOUNT_JSON 또는 PATH / secrets/google_service_account.json
  시트 ID는 env 또는 config/settings.json.filter_trace_sheet_id

사용:
  python3 scripts/init_filter_trace_sheet.py
  python3 scripts/init_filter_trace_sheet.py --sample
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.operations.filter_trace import SHEET_HEADERS, build_trace  # noqa: E402
from mail_core.storage.filter_trace_sheet import (  # noqa: E402
    accumulate_traces,
    ensure_filter_trace_tab,
    sheet_configured,
    sheet_url,
    _sheet_id,
    _tab_name,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Init filter_trace Google Sheet tab/headers")
    ap.add_argument("--sample", action="store_true", help="헤더 보장 후 샘플 1행 append")
    args = ap.parse_args()

    base = {
        "sheet_id": _sheet_id(),
        "tab": _tab_name(),
        "url": sheet_url(),
        "sheet_configured": sheet_configured(),
        "headers": SHEET_HEADERS,
    }
    init = ensure_filter_trace_tab()
    out: dict = {**base, "ensure": init}

    if args.sample and init.get("ok"):
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
        out["sample"] = accumulate_traces([trace])
        out["trace_context"] = trace.get("context")

    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not sheet_configured():
        print(
            "\n# 다음 필요:\n"
            "# 1) 서비스 계정 JSON → GOOGLE_SERVICE_ACCOUNT_JSON (Cloud Secret) 또는 secrets/\n"
            "# 2) 시트를 그 서비스 계정 이메일에 편집자 공유\n"
            "# 3) 탭 이름 filter_trace 1행에 헤더 붙여넣기(아래):\n"
            + ",".join(SHEET_HEADERS),
            file=sys.stderr,
        )
        return 2
    return 0 if init.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
