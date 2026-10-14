#!/usr/bin/env python3
"""var/raw 를 아티팩트로 묶기 전에 이메일 주소를 마스킹한 사본을 만든다(MAIL-036).

원본 var/raw 는 건드리지 않고 dst 에 같은 상대경로로 복사하면서 텍스트(.json/.html/.txt/.md 등)와
.gz 안의 텍스트에서 이메일 주소를 '<email>' 로 바꾼다. 바이너리는 그대로 복사.
사용: python scripts/mask_raw_emails.py var/raw var/logs/run_records/raw
"""
from __future__ import annotations

import gzip
import re
import shutil
import sys
from pathlib import Path

EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+\-]+(?:@|%40|&#64;|\(at\))[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TEXT_EXT = {".json", ".jsonl", ".html", ".htm", ".txt", ".md", ".csv", ".xml"}


def mask_bytes(data: bytes) -> bytes:
    return EMAIL_RE.sub(b"<email>", data)


def mask_tree(src: Path, dst: Path) -> int:
    n = 0
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if ".." in rel.parts:
            continue
        out = dst / rel
        if f.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix == ".gz" and Path(f.stem).suffix in TEXT_EXT:
            out.write_bytes(gzip.compress(mask_bytes(gzip.decompress(f.read_bytes()))))
            n += 1
        elif f.suffix in TEXT_EXT:
            out.write_bytes(mask_bytes(f.read_bytes()))
            n += 1
        else:
            shutil.copy2(f, out)
    return n


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if dst.exists():
        shutil.rmtree(dst)
    print(f"masked {mask_tree(src, dst)} files → {dst}")
