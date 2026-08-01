# -*- coding: utf-8 -*-
"""Extract user_query snippets from Cursor agent transcripts (parent sessions)."""
import re
from datetime import datetime
from pathlib import Path

base = Path(r"C:\Users\ekth3\.cursor\projects\d-mail\agent-transcripts")
files = []
for d in base.iterdir():
    if not d.is_dir():
        continue
    f = d / f"{d.name}.jsonl"
    if f.exists():
        files.append(f)
files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
print(f"parent sessions: {len(files)}")

uq_re = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.S)

for f in files[:18]:
    mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    print(f"\n===== {f.parent.name} | {mtime} =====")
    n = 0
    with open(f, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "user_query" not in line:
                continue
            if '"role":"user"' not in line and '"role": "user"' not in line:
                continue
            m = uq_re.search(line)
            if not m:
                continue
            n += 1
            if n > 25:
                break
            q = m.group(1)
            # Prefer the human ask at the end for skill-attached messages
            if "manually_attached_skills" in q or "SKILL.md content" in q:
                # take last 500 chars which usually hold the actual request
                tail = q[-600:]
                # try to find Korean/command start
                for marker in (
                    "/ultragoal",
                    "/요청사항체크",
                    "요청사항",
                    "해줘",
                    "진행",
                    "확인",
                    "결과",
                    "task",
                    "TASK",
                    "깃",
                    "완료",
                ):
                    idx = tail.rfind(marker)
                    if idx >= 0:
                        q = tail[idx:]
                        break
                else:
                    q = tail
            q = q.replace("\\n", "\n").strip()
            q = re.sub(r"\s+", " ", q)
            if len(q) > 380:
                q = q[:380] + "..."
            print(f"[{n}] {q}")
