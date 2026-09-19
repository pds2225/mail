import base64
import gzip
import json
from pathlib import Path

from scripts.apply_admin_payload import run


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_group_patch_preserves_private_and_advanced_fields(tmp_path: Path) -> None:
    _write(
        tmp_path / "config/groups.json",
        [
            {
                "id": "g1",
                "name": "기존",
                "active": True,
                "or_keywords": ["기존"],
                "recipients": [],
                "company_id": "company-1",
                "score_threshold": 45,
            }
        ],
    )
    _write(
        tmp_path / ".apply/config-pending.json",
        {"v": 1, "resource": "group", "id": "g1", "patch": {"name": "변경", "or_keywords": ["AI"]}},
    )

    assert run(tmp_path) == "group:g1"
    group = json.loads((tmp_path / "config/groups.json").read_text(encoding="utf-8"))[0]
    assert group["name"] == "변경"
    assert group["or_keywords"] == ["AI"]
    assert group["company_id"] == "company-1"
    assert group["score_threshold"] == 45
    assert group["recipients"] == []
    assert not (tmp_path / ".apply/config-pending.json").exists()


def test_settings_patch_preserves_non_ui_policy(tmp_path: Path) -> None:
    _write(
        tmp_path / "config/settings.json",
        {
            "days_back": 3,
            "date_unknown_policy": "recall",
            "raw_store_enabled": True,
            "filter_trace_sheet_id": "sheet-id",
        },
    )
    _write(
        tmp_path / ".apply/config-pending.json",
        {"v": 1, "resource": "settings", "patch": {"days_back": 5}},
    )

    assert run(tmp_path) == "settings"
    settings = json.loads((tmp_path / "config/settings.json").read_text(encoding="utf-8"))
    assert settings["days_back"] == 5
    assert settings["date_unknown_policy"] == "recall"
    assert settings["raw_store_enabled"] is True
    assert settings["filter_trace_sheet_id"] == "sheet-id"


def test_review_patch_upserts_tier_c_without_mail(tmp_path: Path) -> None:
    labels = tmp_path / "data/golden/feedback_labels.jsonl"
    labels.parent.mkdir(parents=True, exist_ok=True)
    labels.write_text(
        json.dumps(
            {
                "id": "notice-1",
                "verdict": "X",
                "tier": "C",
                "source": "mail-feedback",
                "title": "",
                "first_seen": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write(
        tmp_path / ".apply/config-pending.json",
        {
            "v": 1,
            "resource": "review",
            "item": {"id": "notice-1", "title": "AI 지원사업", "verdict": "O"},
        },
    )

    assert run(tmp_path) == "review:O:notice-1"
    row = json.loads(labels.read_text(encoding="utf-8").strip())
    assert row["verdict"] == "O"
    assert row["tier"] == "C"
    assert row["source"] == "dashboard-ox"
    assert row["title"] == "AI 지원사업"
    assert row["first_seen"] == "2026-01-01T00:00:00Z"


def test_review_batch_upserts_multiple_items_in_one_commit(tmp_path: Path) -> None:
    """MAIL-018: 여러 건을 한 번의 저장으로 처리한다(개별 커밋 아님)."""
    labels = tmp_path / "data/golden/feedback_labels.jsonl"
    labels.parent.mkdir(parents=True, exist_ok=True)
    labels.write_text(
        json.dumps({"id": "notice-1", "verdict": "X", "tier": "C", "source": "mail-feedback",
                    "title": "", "first_seen": "2026-01-01T00:00:00Z", "last_seen": "2026-01-01T00:00:00Z"},
                   ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write(
        tmp_path / ".apply/config-pending.json",
        {
            "v": 1,
            "resource": "review",
            "items": [
                {"id": "notice-1", "title": "AI 지원사업", "verdict": "O"},
                {"id": "notice-2", "title": "제조 바우처", "verdict": "X"},
            ],
        },
    )

    assert run(tmp_path) == "review:2items"
    rows = [json.loads(line) for line in labels.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["id"]: row for row in rows}
    assert by_id["notice-1"]["verdict"] == "O"
    assert by_id["notice-1"]["first_seen"] == "2026-01-01T00:00:00Z"
    assert by_id["notice-2"]["verdict"] == "X"
    assert by_id["notice-2"]["title"] == "제조 바우처"
    assert not (tmp_path / ".apply/config-pending.json").exists()


def test_review_packed_batch_preserves_titles_and_verdicts(tmp_path: Path) -> None:
    items = [
        {"id": "notice-1", "title": "AI 지원사업", "verdict": "O"},
        {"id": "notice-2", "title": "제조 바우처", "verdict": "X"},
    ]
    packed = base64.b64encode(
        gzip.compress(json.dumps(items, ensure_ascii=False).encode("utf-8"))
    ).decode("ascii")
    _write(
        tmp_path / ".apply/config-pending.json",
        {
            "v": 1,
            "resource": "review",
            "encoding": "gzip-base64",
            "packed_items": packed,
        },
    )

    assert run(tmp_path) == "review:2items"
    labels = tmp_path / "data/golden/feedback_labels.jsonl"
    rows = [json.loads(line) for line in labels.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["id"]: row for row in rows}
    assert by_id["notice-1"]["title"] == "AI 지원사업"
    assert by_id["notice-1"]["verdict"] == "O"
    assert by_id["notice-2"]["title"] == "제조 바우처"
    assert by_id["notice-2"]["verdict"] == "X"


def test_review_packed_batch_rejects_invalid_encoded_data(tmp_path: Path) -> None:
    _write(
        tmp_path / ".apply/config-pending.json",
        {
            "v": 1,
            "resource": "review",
            "encoding": "gzip-base64",
            "packed_items": "not-valid-base64***",
        },
    )

    try:
        run(tmp_path)
        assert False, "expected ValueError for invalid packed payload"
    except ValueError as exc:
        assert "invalid packed review payload" in str(exc)


def test_review_batch_rejects_invalid_item_in_batch(tmp_path: Path) -> None:
    _write(
        tmp_path / ".apply/config-pending.json",
        {
            "v": 1,
            "resource": "review",
            "items": [
                {"id": "notice-1", "title": "ok", "verdict": "O"},
                {"id": "notice-2", "title": "bad", "verdict": "Y"},
            ],
        },
    )
    try:
        run(tmp_path)
        assert False, "expected ValueError for invalid verdict"
    except ValueError:
        pass
    labels = tmp_path / "data/golden/feedback_labels.jsonl"
    assert not labels.exists()
