import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/mail")
from scripts.download_kstartup_targets import collect_kstartup_items, match_notice, load_targets

items = collect_kstartup_items(max_pages=30)
targets = load_targets(Path("targets/kstartup_20260623.txt"))
found = 0
for t in targets:
    item, score = match_notice(t, items)
    if item and score >= 0.72:
        found += 1
        print(f"OK {score:.2f} {t[:50]}")
print("found", found, "/", len(targets))
