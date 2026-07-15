r"""extract_golden_labels — 약라벨(Tier A) 골든셋 추출 (읽기전용, append-only).

raw store 의 meta.json 에 채워진 region_field(공고의 정답 지역)를 골든셋으로 모은다.
게이트 판정의 1차 정답으로 쓰이는 Tier A 라벨. 사람확인(Tier C) 라벨은 절대 덮어쓰지
않는다 — 같은 id 가 이미 있으면 기존 우선(사람확인 보존), 신규만 추가.

산출물:
  D:\mail\data\golden\region_labels.jsonl   (append-only, 1줄=1라벨)

각 줄 스키마:
  {"id","region_field","source","title","tier":"A","first_seen","last_seen"}

실행 (PowerShell, D:\mail 에서):
  python scripts\extract_golden_labels.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GOLDEN = BASE_DIR / "data" / "golden" / "region_labels.jsonl"


def _fix_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _notice_key(it: dict) -> str:
    for f in ("id", "notice_id", "url", "link", "detail_url"):
        v = it.get(f)
        if v:
            return str(v)
    return "t:" + str(it.get("title", ""))[:90]


def _load_existing() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not GOLDEN.exists():
        return out
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if d.get("id"):
            out[d["id"]] = d
    return out


def main() -> int:
    _fix_console()
    data_root = BASE_DIR / "data" / "raw"
    if not data_root.exists():
        print(f"[SKIP] raw store 없음: {data_root}")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = _load_existing()
    added = 0
    updated = 0
    seen_key: set[str] = set()

    for mp in sorted(data_root.glob("*/notices/*/meta.json")):
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        rf = str(d.get("region_field") or "").strip()
        if not rf:
            continue
        k = _notice_key(d)
        if k in seen_key:
            continue
        seen_key.add(k)
        rec = {
            "id": k,
            "region_field": rf,
            # 5필드 스냅샷(지역 외 4) — 추출값 약참조(Tier A). 드리프트·회귀 감지용.
            "posted_date": str(d.get("posted_date") or "").strip(),
            "application_period": d.get("application_period") or "",
            "deadline": str(d.get("deadline") or "").strip(),
            "support_field": str(d.get("support_field") or "").strip(),
            "source": str(d.get("source") or d.get("site") or d.get("agency") or ""),
            "title": str(d.get("title", ""))[:120],
            "tier": "A",
        }
        if k in existing:
            prev = existing[k]
            # 사람확인(Tier C) 라벨은 보존 — region_field/tier 덮어쓰지 않음
            if prev.get("tier") == "C":
                continue
            prev.update({**rec, "tier": prev.get("tier", "A")})
            prev["last_seen"] = now
            prev.setdefault("first_seen", now)
            existing[k] = prev
            updated += 1
        else:
            rec["first_seen"] = now
            rec["last_seen"] = now
            existing[k] = rec
            added += 1

    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(existing[k], ensure_ascii=False) for k in sorted(existing)]
    GOLDEN.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    tier_counts: dict[str, int] = {}
    for v in existing.values():
        tier_counts[v.get("tier", "A")] = tier_counts.get(v.get("tier", "A"), 0) + 1
    print(f"[golden] 총 {len(existing)}건 (신규 {added} · 갱신 {updated}) tier={tier_counts}")
    print(f"[out] {GOLDEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
