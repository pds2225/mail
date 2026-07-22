#!/usr/bin/env python3
"""delivery_state — (기준일·그룹·수신자) 단위 발송 멱등 상태 (재발송·부분실패 안전).

문제(진단서 #113·#114·#115·#116·#144):
  현재 발송은 성공/실패를 카운터로만 남기고 *누구에게 무엇을 보냈는지* 상태가 없다.
  발송 루프 도중 크래시하거나 일부 수신자 SMTP 실패 후 재실행하면 이미 받은 수신자에게
  또 발송되거나(중복), 반대로 seen 이 먼저 기록돼 미발송분이 영구 누락될 수 있다.

이 모듈:
  발송 단위를 (기준일자, 그룹, 수신자)로 보고, **성공 즉시** delivery_state.json 에
  체크포인트한다(원자적 교체). 재실행 시 이미 성공한 (일자·그룹·수신자)는 건너뛴다
  → 크래시/부분실패 후 재실행이 성공 수신자에게 중복 발송하지 않는다(멱등).

안전:
  - 읽기 실패·깨진 파일은 빈 상태로 취급(발송을 막지 않음 — 최악의 경우 종전처럼 발송).
  - 원자적 쓰기(tmp→os.replace)로 동시/중단 시 파일 손상 방지.
  - prune 으로 최근 N일 키만 유지(무한 증가 방지).

주의(파트 경계): GitHub Actions 는 매 실행 새 컨테이너다. **실행 간** 멱등이 되려면 워크플로가
  delivery_state.json 을 seen_ids 와 함께 커밋백해야 한다(.github/workflows/monitor.yml — Part B).
  본 모듈·배선(Part A)은 그와 무관하게 단독 동작한다(같은 컨테이너 내 재시도·부분실패 안전).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

MAX_KEEP_DATES = 30  # 최근 N개 기준일자의 키만 유지(무한 증가 방지)


def key(date: str, group: str, recipient: str) -> str:
    """발송 멱등 키 — (기준일자|그룹|수신자소문자). 수신자 공백·대소문자 정규화."""
    d = (date or "").strip()
    g = (group or "").strip()
    r = (recipient or "").strip().lower()
    return f"{d}|{g}|{r}"


def load(path: str | os.PathLike) -> set[str]:
    """저장된 발송 키 집합을 읽는다(없거나 깨졌으면 빈 집합 — 발송을 막지 않는다)."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return set()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return set()
    if isinstance(data, dict):  # {key: ts} 형태도 허용
        return {str(k) for k in data}
    if isinstance(data, list):
        return {str(k) for k in data}
    return set()


def _prune(keys: set[str]) -> set[str]:
    """기준일자 기준 최근 MAX_KEEP_DATES 개 날짜의 키만 남긴다."""
    dates = sorted({k.split("|", 1)[0] for k in keys if "|" in k}, reverse=True)
    if len(dates) <= MAX_KEEP_DATES:
        return keys
    keep = set(dates[:MAX_KEEP_DATES])
    return {k for k in keys if k.split("|", 1)[0] in keep}


def save(path: str | os.PathLike, keys: set[str]) -> None:
    """발송 키 집합을 원자적으로 저장(tmp→replace). seen_ids 와 동일 포맷 규약(정렬·개행없음)."""
    keys = _prune(set(keys))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(sorted(keys), ensure_ascii=False, indent=1)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".delivery_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)  # 원자적 교체 — 중단 시 원본 보존
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def mark(path: str | os.PathLike, k: str, _cache: set[str] | None = None) -> set[str]:
    """키 하나를 발송완료로 기록하고 즉시 저장(체크포인트). 갱신된 집합을 반환한다.

    _cache 를 넘기면 파일 재로딩 없이 그 집합에 추가해 저장한다(수신자 루프 최적화).
    """
    keys = _cache if _cache is not None else load(path)
    keys.add(k)
    save(path, keys)
    return keys
