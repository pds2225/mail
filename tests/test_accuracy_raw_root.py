"""정확도 하네스가 수집 원본(raw store)을 실제로 찾는지 지키는 회귀 테스트.

배경: raw store 가 `data/raw` → `var/raw` 로 이사한 뒤에도 채점·라벨 스크립트가
구 경로를 하드코딩하고 있어서, 전수 채점이 "공고 0건"으로 조용히 통과했다.
정확도 게이트가 통째로 무력화됐는데 종료코드는 0 이라 아무도 몰랐다.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_notice(root: Path, date: str, nid: str) -> None:
    d = root / date / "notices" / nid
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(
        json.dumps({"id": nid, "title": f"테스트 공고 {nid}"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_paths(monkeypatch, var_dir: Path):
    monkeypatch.setenv("MAIL_VAR_DIR", str(var_dir))
    import mail_core.paths as paths

    return importlib.reload(paths)


def test_resolve_raw_root_prefers_var_raw(monkeypatch, tmp_path):
    """정본(var/raw)에 수집분이 있으면 그것을 쓴다."""
    var_dir = tmp_path / "var"
    _write_notice(var_dir / "raw", "2026-08-04", "n1")
    paths = _load_paths(monkeypatch, var_dir)
    try:
        assert paths.resolve_raw_root() == paths.RAW_DIR
    finally:
        monkeypatch.delenv("MAIL_VAR_DIR", raising=False)
        importlib.reload(paths)


def test_resolve_raw_root_falls_back_to_legacy(monkeypatch, tmp_path):
    """정본이 비어 있고 구 경로(data/raw)에만 수집분이 있으면 구 경로를 쓴다."""
    var_dir = tmp_path / "var"
    (var_dir / "raw").mkdir(parents=True)
    paths = _load_paths(monkeypatch, var_dir)
    try:
        if not paths.LEGACY_RAW_DIR.exists():
            pytest.skip("구 경로가 없는 저장소")
        # 구 경로에 공고가 있을 때만 폴백이 의미 있다.
        legacy_has = next(paths.LEGACY_RAW_DIR.glob("*/notices/*/meta.json"), None)
        expected = paths.LEGACY_RAW_DIR if legacy_has else paths.RAW_DIR
        assert paths.resolve_raw_root() == expected
    finally:
        monkeypatch.delenv("MAIL_VAR_DIR", raising=False)
        importlib.reload(paths)


def test_accuracy_matrix_fails_loudly_when_raw_store_empty(tmp_path):
    """수집 원본이 비면 종료코드 0(성공)이 아니라 실패로 끝나야 한다.

    이게 0 이면 CI·오케스트레이터가 '측정 불가'를 '이상 없음'으로 읽는다.
    """
    empty_var = tmp_path / "var"
    (empty_var / "raw").mkdir(parents=True)
    env = {
        **dict(__import__("os").environ),
        "MAIL_VAR_DIR": str(empty_var),
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "accuracy_matrix.py"), "--max", "1"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if "필수 환경변수 누락" in (proc.stderr or ""):
        pytest.skip(".env 없는 환경(CI 시크릿 미주입)")
    assert proc.returncode != 0, f"빈 raw store 인데 성공으로 끝났다:\n{proc.stdout}"


def test_no_script_hardcodes_legacy_raw_path():
    """정확도 스크립트가 구 경로를 다시 하드코딩하지 못하게 막는다."""
    offenders = []
    for name in (
        "accuracy_matrix.py",
        "accuracy_eval.py",
        "extract_golden_labels.py",
        "expand_golden_labels.py",
        "fn_triage.py",
    ):
        text = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            if '"data" / "raw"' in line or '"data/raw"' in line:
                offenders.append(f"{name}: {stripped}")
    assert not offenders, "raw store 경로는 mail_core.paths.resolve_raw_root() 로 정한다:\n" + "\n".join(offenders)
