import subprocess
out=[]
runs=[
 ("30316187761","728"),
 ("30409775617","729"),
 ("30501454927","730am_cancel"),
 ("30538573504","730pm"),
 ("30590919733","731am_cancel"),
 ("30627655178","731pm"),
 ("30673138769","801am"),
]
ascii_keys=("already_delivered","skipped_fetch","mail_sent","new_items","filtered_items","skip_gate","already delivered")
ko_keys=("수집 완료","발송 완료","대상일","발송 멱등","스킵","공고")
for rid,label in runs:
    p=subprocess.run(["gh","run","view",rid,"--log"],capture_output=True,text=True,encoding="utf-8",errors="replace")
    lines=p.stdout.splitlines()
    hits=[]; info=[]
    for ln in lines:
        low=ln.lower()
        if "collecting " in low or "downloading " in low:
            continue
        if any(k in low for k in ascii_keys) or any(k in ln for k in ko_keys):
            s=ln.split("Z ",1)[-1] if "Z " in ln else ln
            hits.append(s[:260])
        if " INFO " in ln and any(x in ln for x in ["수집","발송","스킵","완료","공고","필터","대상","already","skip","digest","메일","기업마당"]):
            s=ln.split("Z ",1)[-1] if "Z " in ln else ln
            info.append(s[:260])
    out.append(f"==== {label} {rid} key_hits={len(hits)} info={len(info)} ====")
    out.extend(hits[:25] or ["(no key hits)"])
    out.append("-- info sample --")
    out.extend(info[:35] or ["(no info)"])
path=r"C:\Users\ekth3\.cursor\projects\d-mail\agent-tools\gha-keywords.txt"
open(path,"w",encoding="utf-8").write("\n".join(out))
print("wrote", path, "lines", len(out))
