"""[임시] 보고용 [원본전체] 메일 — 직전영업일 모든 공고(그룹 필터 없음) → ekth3691 단독. 실행 후 삭제.
monitor.py 무수정. 런타임 설정만 오버라이드. 다른 수신자/그룹메일 전부 차단.
"""
import os, sys
from pathlib import Path

envf = Path(r"D:\mail\.env")
for line in envf.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ.setdefault("MONITOR_NO_PERSIST_SEEN", "1")
sys.path.insert(0, r"D:\mail")
import monitor as m  # noqa: E402

ONLY = "ekth3691@gmail.com"
_og = m.load_groups
m.load_groups = lambda: [{**g, "recipients": []} for g in _og()]   # 그룹메일 발송 차단(다른 수신자 보호)
_os = m.load_settings
def _s():
    s = _os()
    s["date_filter_enabled"] = True            # 직전영업일 기준
    s["raw_all_enabled"] = True
    s["raw_all_recipients"] = [ONLY]           # 보고용은 나에게만
    return s
m.load_settings = _s
m.load_seen_ids = lambda: set()                 # 직전영업일 '모든' 공고(이미 발송분도 포함)
m.load_watchlist = lambda: {"keywords": [], "urls": [], "recipients": []}

print("보고용 [원본전체] 발송 (직전영업일·필터없음) -> %s ..." % ONLY, flush=True)
res = m.execute_monitor(allow_send=True, include_raw_all=True, persist_seen=False)
print("RESULT:", {k: res.get(k) for k in ("ok", "collected", "deduped", "new_items", "filtered_items", "date_unknown_items", "mail_sent")}, flush=True)
