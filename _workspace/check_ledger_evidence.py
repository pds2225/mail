# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess

a = Path("docs/project/ZERO_MISS_GUARDRAILS.md").read_text(encoding="utf-8")
b = Path("_to delete/wip-side-20260801/docs__project__ZERO_MISS_GUARDRAILS.md").read_text(encoding="utf-8")
print("HEAD len", len(a), "WIP len", len(b))
print("HEAD has 오늘(KST)", "오늘(KST)" in a)
print("WIP has 오늘(KST)", "오늘(KST)" in b)
for line in b.splitlines():
    if any(x in line for x in ("LLM", "오늘", "연도")):
        print("WIP:", line[:140])

out = subprocess.check_output(
    ["git", "show", "7861ca6d6:config/watchlist.json"],
    cwd=r"d:\mail",
    text=True,
    encoding="utf-8",
    errors="replace",
)
print("snapshot has 벤처캠프", "벤처캠프" in out)
print("snapshot has 네스트", "네스트" in out)
print("snapshot has 기보", "기보" in out)

cur = Path("config/watchlist.json").read_text(encoding="utf-8")
print("current has 벤처캠프", "벤처캠프" in cur)
print("SESSION_RECAP exists", Path("SESSION_RECAP.md").exists())
print("REQUEST_LEDGER exists", Path("REQUEST_LEDGER.md").exists())
