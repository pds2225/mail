#!/usr/bin/env python3
"""GHA MDR 아티팩트(_gha_*)를 정규 var/reviews/<date>/ 로 승격.

var/reviews 는 gitignore — 커밋하지 않는다. ledger PASS만 보고 경로가
비어 보이는 오판을 막기 위한 로컬 운영 도구.

Usage (repo root):
  python scripts/promote_mdr_artifact.py var/reviews/_gha_30723439338
  python scripts/promote_mdr_artifact.py var/reviews/_gha_30723439338 --dry-run
  python scripts/promote_mdr_artifact.py --run-id 30723439338
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "var" / "reviews"


def _find_day_dirs(src: Path) -> list[Path]:
    """review_{am|pm}.{md,json} 을 포함한 YYYY-MM-DD 디렉터리 목록."""
    found: dict[Path, Path] = {}
    if not src.exists():
        return []
    for path in src.rglob("review_*.md"):
        parent = path.parent
        name = parent.name
        if len(name) == 10 and name[4] == "-" and name[7] == "-":
            found[parent.resolve()] = parent
    for path in src.rglob("review_*.json"):
        parent = path.parent
        name = parent.name
        if len(name) == 10 and name[4] == "-" and name[7] == "-":
            found[parent.resolve()] = parent
    return sorted(found.values(), key=lambda p: p.name)


def promote(src: Path, *, dest_root: Path = REVIEWS, dry_run: bool = False) -> list[Path]:
    days = _find_day_dirs(src)
    written: list[Path] = []
    for day_dir in days:
        target = dest_root / day_dir.name
        if dry_run:
            print(f"[dry-run] {day_dir} -> {target}")
            written.append(target)
            continue
        target.mkdir(parents=True, exist_ok=True)
        for child in day_dir.iterdir():
            if not child.is_file():
                continue
            out = target / child.name
            shutil.copy2(child, out)
            written.append(out)
            print(f"copied {child.relative_to(src) if src in child.parents else child} -> {out}")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote GHA MDR artifact into var/reviews/<date>/")
    parser.add_argument(
        "src",
        nargs="?",
        type=Path,
        help="다운로드 루트 (예: var/reviews/_gha_<run_id>)",
    )
    parser.add_argument("--run-id", help="있으면 var/reviews/_gha_<run_id> 를 src 로 사용")
    parser.add_argument("--dest", type=Path, default=REVIEWS, help="기본: var/reviews")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    src = args.src
    if args.run_id:
        src = REVIEWS / f"_gha_{args.run_id}"
    if src is None:
        parser.error("src 또는 --run-id 필요")
    src = src.resolve()
    if not src.exists():
        print(f"error: src not found: {src}", file=sys.stderr)
        return 1

    written = promote(src, dest_root=args.dest.resolve(), dry_run=args.dry_run)
    if not written:
        print(f"error: no review_*/YYYY-MM-DD dirs under {src}", file=sys.stderr)
        return 2
    print(f"ok: {len(written)} path(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
