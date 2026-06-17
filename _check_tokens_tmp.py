import json, os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

base = r"D:\google-tasks-mcp"
for f in ["token.json", "token-cloud.json", "token_calendar.json", "token_write.json", "cloud_token.json"]:
    p = os.path.join(base, f)
    if not os.path.exists(p):
        print(f, "MISSING"); continue
    try:
        info = json.load(open(p, encoding="utf-8"))
        c = Credentials.from_authorized_user_info(info)
        if (not c.valid) and c.refresh_token:
            c.refresh(Request())
        scopes = info.get("scopes") or ([info["scope"]] if info.get("scope") else [])
        has_cal = any("calendar" in s for s in scopes)
        has_task = any("tasks" in s for s in scopes)
        try:
            build("calendar", "v3", credentials=c).calendarList().list(maxResults=1).execute()
            cal = "OK"
        except Exception as e:
            cal = "403" if "403" in str(e) else "ERR:" + type(e).__name__
        try:
            build("tasks", "v1", credentials=c).tasklists().list(maxResults=1).execute()
            tsk = "OK"
        except Exception as e:
            tsk = "403" if "403" in str(e) else "ERR:" + type(e).__name__
        print(f"{f:22} | cal_scope={has_cal} task_scope={has_task} | CAL_API={cal} TASKS_API={tsk}")
    except Exception as e:
        print(f"{f:22} | PARSE_ERR {type(e).__name__} {str(e)[:60]}")
