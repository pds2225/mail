"""MAIL-039: run #266 meta.json 이 '\\n'+이메일 마스킹으로 깨지던 문제 회귀."""
import gzip
import json

from scripts import mask_raw_emails as mre

META = {"notice_id": "startup_plus_PRJ007422",
        "description": "문의처\n(이메일/연락처)\nstaff@example.test\r\n  02-000-0000",
        "list": ["a\tops@example.test"], "nested": {"k": "x%40example.test"}}


def test_json_escape_safe(tmp_path):
    src, dst = tmp_path / "raw", tmp_path / "out"
    d = src / "2026-10-14" / "notices" / "startup_plus_PRJ007422"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps(META, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "detail.meta.json.gz").write_bytes(gzip.compress(json.dumps(META).encode()))
    (d / "rows.jsonl").write_text(json.dumps(META) + "\n" + json.dumps({"e": "\nz@example.test"}) + "\n")
    (d / "detail.html.gz").write_bytes(gzip.compress(b"<p>mail: staff@example.test</p>"))
    mre.mask_tree(src, dst)
    o = dst / d.relative_to(src)
    got = json.loads((o / "meta.json").read_text(encoding="utf-8"))
    assert got["description"] == "문의처\n(이메일/연락처)\n<email>\r\n  02-000-0000"
    assert got["list"] == ["a\t<email>"] and got["nested"]["k"] == "<email>"
    assert json.loads(gzip.decompress((o / "detail.meta.json.gz").read_bytes()))["description"].endswith("02-000-0000")
    rows = [json.loads(l) for l in (o / "rows.jsonl").read_text().splitlines() if l.strip()]
    assert rows[1]["e"] == "\n<email>"
    assert gzip.decompress((o / "detail.html.gz").read_bytes()) == b"<p>mail: <email></p>"
    for f in o.rglob("*"):
        raw = gzip.decompress(f.read_bytes()) if f.suffix == ".gz" else f.read_bytes()
        assert b"example.test" not in raw


def test_bytes_path_shows_old_bug_is_avoided():
    bad = json.dumps({"d": "x\nstaff@example.test"}).encode()
    assert json.loads(mre.mask_for("meta.json", bad))["d"] == "x\n<email>"


def test_unparseable_json_falls_back_to_bytes():
    assert mre.mask_for("meta.json", b"{broken staff@example.test") == b"{broken <email>"
