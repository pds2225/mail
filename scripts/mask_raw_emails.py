#!/usr/bin/env python3
"""var/raw 를 아티팩트로 묶기 전에 이메일 주소를 마스킹한 사본을 만든다(MAIL-036).

원본 var/raw 는 건드리지 않고 dst 에 같은 상대경로로 복사하면서 텍스트(.json/.html/.txt/.md 등)와
.gz 안의 텍스트에서 이메일 주소를 '<email>' 로 바꾼다. 바이너리는 그대로 복사.
사용: python scripts/mask_raw_emails.py var/raw var/logs/run_records/raw
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import sys
from pathlib import Path

EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+\-]+(?:@|%40|&#64;|\(at\))[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TEXT_EXT = {".json", ".jsonl", ".html", ".htm", ".txt", ".md", ".csv", ".xml"}


EMAIL_STR_RE = re.compile(EMAIL_RE.pattern.decode())


def mask_bytes(data: bytes) -> bytes:
    """HTML·평문용 바이트 치환. JSON 에는 쓰지 않는다(이스케이프 '\\n'+주소의 n 까지 지워 깨짐 — MAIL-039)."""
    return EMAIL_RE.sub(b"<email>", data)


def _mask_value(v):
    if isinstance(v, str):
        return EMAIL_STR_RE.sub("<email>", v)
    if isinstance(v, list):
        return [_mask_value(x) for x in v]
    if isinstance(v, dict):
        return {(_mask_value(k) if isinstance(k, str) else k): _mask_value(x) for k, x in v.items()}
    return v


def _mask_json_doc(data: bytes, jsonl: bool) -> bytes:
    """JSON 은 파싱 후 문자열 값만 마스킹하고 다시 직렬화(이스케이프 안전). 파싱 실패 시 바이트 치환으로 폴백."""
    try:
        text = data.decode("utf-8")
        if jsonl:
            out = [json.dumps(_mask_value(json.loads(l)), ensure_ascii=False) if l.strip() else l
                   for l in text.split("\n")]
            return "\n".join(out).encode("utf-8")
        return json.dumps(_mask_value(json.loads(text)), ensure_ascii=False, indent=1).encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return mask_bytes(data)


def mask_for(name: str, data: bytes) -> bytes:
    if name.endswith(".jsonl"):
        return _mask_json_doc(data, jsonl=True)
    if name.endswith(".json"):
        return _mask_json_doc(data, jsonl=False)
    return mask_bytes(data)


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
            out.write_bytes(gzip.compress(mask_for(f.stem, gzip.decompress(f.read_bytes()))))
            n += 1
        elif f.suffix in TEXT_EXT:
            out.write_bytes(mask_for(f.name, f.read_bytes()))
            n += 1
        else:
            shutil.copy2(f, out)
    return n


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if dst.exists():
        shutil.rmtree(dst)
    print(f"masked {mask_tree(src, dst)} files → {dst}")
