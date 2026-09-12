#!/usr/bin/env python3
r"""merge_seen_ids — 두 seen_ids.json(문자열 id 리스트)을 합집합으로 병합.

왜 필요한가:
  발송 워크플로(monitor.yml)가 seen_ids.json 을 커밋백할 때, 3시간 실행 도중 원격 main 이
  앞서가면(다른 실행/머지) `git push` 가 거부된다. 기존엔 `git push || true` 라 조용히
  버려져 **오늘 발송 이력이 원격에 저장 안 됨 → 다음날 같은 공고 중복 재발송** 위험이 있었다.
  이 스크립트는 그 재시도 경로에서 로컬과 원격 seen_ids 를 **합집합**으로 병합해 어느 쪽
  이력도 잃지 않게 한다(=중복 재발송 방지).

동작:
  monitor.save_seen_ids 와 동일하게 mail_core.storage.seen_ids_prune 상한·정렬을 적용하고,
  atomic_write_json(tmp→replace) 으로 기록한다. Path.write_text('w') 는 열자마자 truncate
  하므로 ENOSPC/킬 시 빈·부분 JSON 이 커밋될 수 있었다(GHA checkout 엔 state_backups 없음).

사용 (repo 루트):
  python scripts/merge_seen_ids.py <local.json> <remote.json>   # 결과를 local 에 기록
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mail_core.storage.seen_ids_prune import MAX_SEEN_IDS, prune_seen_ids  # noqa: E402
from mail_core.storage.state_store import atomic_write_json  # noqa: E402


def _load(path: str | Path) -> set[str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(x) for x in raw if x} if isinstance(raw, list) else set()


def merge_files(local_path: str | Path, remote_path: str | Path) -> list[str]:
    """local ∪ remote → 정렬·상한 적용 후 local 에 기록. 병합 결과 리스트 반환."""
    ids = _load(local_path) | _load(remote_path)
    merged = prune_seen_ids(ids, max_keep=MAX_SEEN_IDS)
    # monitor.save_json 과 동일 포맷(indent=2·ensure_ascii=False·트레일링 개행 없음).
    # 반드시 atomic — write_text('w') truncate-then-write 는 실패 시 seen_ids 를 비운다.
    atomic_write_json(local_path, merged, indent=2, backup=True)
    return merged


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: merge_seen_ids.py <local.json> <remote.json>", file=sys.stderr)
        return 2
    merged = merge_files(argv[1], argv[2])
    print(f"merged seen_ids: {len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
