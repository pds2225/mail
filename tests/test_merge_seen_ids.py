"""seen_ids 합집합 병합 회귀 테스트.

발송 워크플로가 seen_ids push 거부(원격 앞섬) 시 로컬·원격을 합집합 병합해 재push 한다.
핵심 성질: ① 합집합(어느 이력도 안 잃음=중복 재발송 방지) ② 5000 상한 ③ monitor.save_seen_ids
와 동일 정렬·직렬화(불필요 diff·동작 비대칭 방지).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import merge_seen_ids as m  # noqa: E402  (scripts/merge_seen_ids.py)


def _write(p, ids):
    p.write_text(json.dumps(list(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def test_union_keeps_both_sides(tmp_path):
    """로컬에만·원격에만 있는 id 가 모두 남는다(어느 발송 이력도 유실 없음)."""
    local = tmp_path / "seen.json"
    remote = tmp_path / "remote.json"
    _write(local, ["a_1", "b_2", "c_3"])
    _write(remote, ["c_3", "d_4", "e_5"])   # c_3 겹침 + d_4/e_5 원격 신규
    merged = m.merge_files(local, remote)
    assert set(merged) == {"a_1", "b_2", "c_3", "d_4", "e_5"}
    # 파일에도 동일하게 반영
    assert set(json.loads(local.read_text(encoding="utf-8"))) == set(merged)


def test_caps_at_max_keeping_latest_by_datekey(tmp_path):
    """5000 초과 시 날짜키 기준 최신 MAX_SEEN_IDS 만 유지(save_seen_ids 정합)."""
    local = tmp_path / "seen.json"
    remote = tmp_path / "remote.json"
    # 날짜 포함 id 6000개 → 최신 5000만 남고, 가장 오래된 날짜는 잘려야 한다.
    old = [f"src_2020-01-{d:02d}_{n}" for d in range(1, 10) for n in range(300)]  # 2700
    new = [f"src_2026-07-{d:02d}_{n}" for d in range(1, 12) for n in range(300)]  # 3300
    _write(local, old)
    _write(remote, new)
    merged = m.merge_files(local, remote)
    assert len(merged) == m.MAX_SEEN_IDS == 5000
    # 최신(2026) 은 유지, 가장 오래된(2020-01-01) 은 잘림
    assert any("2026-07-11" in x for x in merged)
    assert not any("2020-01-01" in x for x in merged)


def test_serialization_matches_save_json(tmp_path):
    """indent=2·ensure_ascii=False·트레일링 개행 없음 — monitor.save_json 과 동일 포맷."""
    local = tmp_path / "seen.json"
    remote = tmp_path / "remote.json"
    _write(local, ["한글_1", "b_2"])
    _write(remote, ["b_2"])
    m.merge_files(local, remote)
    text = local.read_text(encoding="utf-8")
    assert not text.endswith("\n")           # save_json 은 트레일링 개행 없음
    assert "한글_1" in text                    # ensure_ascii=False (한글 그대로)
    assert text.startswith("[\n  ")           # indent=2


def test_missing_or_broken_files_are_safe(tmp_path):
    """없는/깨진 파일은 빈 집합으로 취급(크래시 없이 병합 진행)."""
    local = tmp_path / "seen.json"
    _write(local, ["a_1"])
    missing = tmp_path / "nope.json"
    merged = m.merge_files(local, missing)
    assert set(merged) == {"a_1"}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    merged2 = m.merge_files(local, broken)
    assert set(merged2) == {"a_1"}
