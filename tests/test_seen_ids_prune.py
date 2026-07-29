"""seen_ids_prune 단위 테스트 — 기업마당 PBLN 탈락 회귀 방지."""
from mail_core.storage.seen_ids_prune import (
    CORE_SEEN_PREFIXES,
    prune_seen_ids,
    seen_id_sort_key,
)


def test_core_prefixes_include_bizinfo_family():
    assert "PBLN_" in CORE_SEEN_PREFIXES
    assert "kstartup_" in CORE_SEEN_PREFIXES


def test_prune_prefers_core_when_over_cap():
    ids = [f"zzzz_{i}" for i in range(100)]
    ids += [f"PBLN_{i:015d}" for i in range(10)]
    ids += [f"kstartup_{i}" for i in range(5)]
    kept = prune_seen_ids(ids, max_keep=20)
    assert len(kept) == 20
    assert sum(1 for x in kept if x.startswith("PBLN_")) == 10
    assert sum(1 for x in kept if x.startswith("kstartup_")) == 5


def test_seen_id_sort_key_ignores_leading_zeros_as_year():
    assert seen_id_sort_key("PBLN_000000000124731") == "PBLN_000000000124731"
