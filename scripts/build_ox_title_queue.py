#!/usr/bin/env python3
"""히스토리 제목으로 OX 판정 큐를 만든다 (메일 불필요).

Usage:
  python3 scripts/build_ox_title_queue.py
  python3 scripts/build_ox_title_queue.py --limit 120
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NV_PATH = ROOT / "var" / "state" / "notice_versions.json"
OUT_JSON = ROOT / "data" / "golden" / "ox_title_queue.json"
OUT_MD = ROOT / "data" / "golden" / "ox_title_queue.md"

NOISE_KW = [
    "설명회", "교육생", "위원", "선정결과", "공시송달", "모니터링단", "보도자료",
    "채용공고", "제도 안내", "수강생", "서포터즈", "합격자", "교육일정", "교육 일정",
]
GRANT_KW = ["바우처", "지원사업", "참여기업 모집", "사업화", "시제품", "지원금"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    nv = json.loads(NV_PATH.read_text(encoding="utf-8")) if NV_PATH.exists() else {}
    titles: list[tuple[str, str]] = []
    for iid, rec in nv.items():
        if not isinstance(rec, dict):
            continue
        snap = rec.get("delivered_snapshot") or rec.get("observed_snapshot") or {}
        t = str(snap.get("title") or "").strip()
        if t:
            titles.append((str(iid), t))

    noise, grants, other = [], [], []
    for iid, t in titles:
        if any(k in t for k in NOISE_KW):
            noise.append((iid, t))
        elif any(k in t for k in GRANT_KW):
            grants.append((iid, t))
        else:
            other.append((iid, t))

    seen: set[str] = set()
    rows: list[dict] = []
    for bucket in (noise, grants, other):
        for iid, t in bucket:
            if t in seen:
                continue
            seen.add(t)
            rows.append({"id": iid, "title": t})
            if len(rows) >= args.limit:
                break
        if len(rows) >= args.limit:
            break

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"count": len(rows), "items": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# OX 제목 판정 큐",
        "",
        "대시보드 **공고 검수 → 제목 O/X** 탭에서 버튼만 누르면 됩니다 (메일 발송 없음).",
        "",
        f"총 {len(rows)}건",
        "",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. `{r['id']}` — {r['title']}")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON} ({len(rows)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
