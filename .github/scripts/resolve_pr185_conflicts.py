from __future__ import annotations

import json
from pathlib import Path


def resolve_conflicts_keep_ours(path: Path) -> None:
    """Keep current-main text inside conflict hunks, preserving all non-conflicting cherry-pick edits."""
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not any(line.startswith("<<<<<<< ") for line in lines):
        return

    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("<<<<<<< "):
            output.append(line)
            i += 1
            continue

        i += 1
        ours: list[str] = []
        while i < len(lines) and not lines[i].startswith(("||||||| ", "=======")):
            ours.append(lines[i])
            i += 1

        if i < len(lines) and lines[i].startswith("||||||| "):
            i += 1
            while i < len(lines) and not lines[i].startswith("======="):
                i += 1

        if i >= len(lines) or not lines[i].startswith("======="):
            raise RuntimeError(f"Malformed conflict block in {path}")
        i += 1
        while i < len(lines) and not lines[i].startswith(">>>>>>> "):
            i += 1
        if i >= len(lines):
            raise RuntimeError(f"Unterminated conflict block in {path}")
        i += 1
        output.extend(ours)

    path.write_text("".join(output), encoding="utf-8")


def patch_incheon_source() -> None:
    path = Path("config/sites.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    found = False
    for site in data:
        if site.get("id") != "incheon_city":
            continue
        site["url"] = (
            "http://announce.incheon.go.kr/citynet/jsp/sap/"
            "SAPGosiBizProcess.do?command=searchList&flag=gosiGL&svp=Y&sido=ic"
        )
        site["note"] = (
            "인천시 고시/공고 조회 시스템 "
            "(기존 IC010205 는 보도자료 게시판이라 교체, 2026-07-24)"
        )
        found = True
        break
    if not found:
        raise RuntimeError("config/sites.json에서 incheon_city를 찾지 못했습니다.")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_pr185_markers() -> None:
    text = Path("monitor.py").read_text(encoding="utf-8")
    required = (
        "def strip_title_badges",
        "_COMMITTEE_TITLE_RE",
        "def _nonlink_hangul_len",
        "claimed_spans: list[tuple[int, int]]",
        "키워드는 '제목·주관기관'만 본다",
        "announce.incheon.go.kr/citynet",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"PR #185 핵심 변경 누락: {missing}")

    factory_block = text.split("FACTORY_REQUIRED_TERMS = [", 1)[1].split("]", 1)[0]
    if '"입주기업"' in factory_block:
        raise RuntimeError("FACTORY_REQUIRED_TERMS에 입주기업이 남아 있습니다.")


if __name__ == "__main__":
    resolve_conflicts_keep_ours(Path("monitor.py"))
    patch_incheon_source()
    Path("sites.json").unlink(missing_ok=True)
    verify_pr185_markers()
