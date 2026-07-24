r"""feedback — 실제 나간 메일에 대한 사용자 ⭕/❌ 피드백 루프 (Tier C 골든 축적).

왜 필요한가:
  그동안 정확도는 '저장된 공고 스냅샷'으로만 쟀다. 진짜 정답은 "내가 실제로 받은 메일이
  맞았나"다. 이 모듈은 그 O/X 를 모아 골든(Tier C = 사람확인)으로 쌓고, 측정
  (scripts/accuracy_matrix.py)이 사람 정답과 우리 판정을 대조하게 만든다.

흐름(무인):
  1) monitor digest 하단에 공고별 ⭕/❌ mailto 링크 첨부      → render_feedback_block()
  2) 사용자가 링크 클릭 → 제목 `[MAIL-FB] X <notice_id>` 메일이 자기 메일함으로 전송
  3) scripts/collect_feedback.py 가 IMAP **읽기전용**으로 수집 → parse_feedback_subject()
  4) data/golden/feedback_labels.jsonl(tier C) 누적          → merge_feedback_labels()
  5) accuracy_matrix 가 사람 정답 대비 불일치(feedback_fp/fn) 산출 → 하네스가 고침

안전(불변):
  - 이 모듈은 메일을 **보내지 않는다**(링크 문자열만 만든다). 수집은 읽기전용 IMAP.
  - 판정 로직 무수정 — 표시(링크)와 측정만. 발송 대상·게이트에 영향 없음.
  - 라벨은 append-only 파일에 누적(사람 라벨을 자동라벨이 덮지 않도록 tier="C" 고정).

키(id): monitor 아이템의 `id` = raw_store meta 의 `notice_id` = accuracy_matrix `_notice_key`
        (실측 2,952건 전부 `[A-Za-z0-9_.-]{1,64}` = URL 안전).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

from mail_core.paths import DATA_DIR
from mail_core.storage.state_store import atomic_write_bytes_while_locked, locked_path

from . import feedback_token  # O/X 토큰 HMAC 서명·검증(#132, opt-in: MAIL_FEEDBACK_SECRET)

LABELS_PATH = DATA_DIR / "golden" / "feedback_labels.jsonl"

SUBJECT_TAG = "[MAIL-FB]"
# 메일 클라이언트가 제목 앞에 Re:/전달: 등을 붙여도 잡히게 search 사용.
# nid(공백 없음) 뒤에 선택적 16-hex 서명 토큰이 올 수 있다(#132).
_SUBJECT_RE = re.compile(
    r"\[\s*MAIL-FB\s*\]\s*([OX])\s+([A-Za-z0-9_.:\-%]{1,120})(?:\s+([0-9a-fA-F]{16}))?",
    re.IGNORECASE,
)

# digest 하단 피드백 목록 상한(표시 전용 — 게이트·발송량과 무관)
MAX_FEEDBACK_ITEMS = 40


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_verdict(value: str) -> str:
    """'O'/'o'/'ok'/'맞음' → 'O', 'X'/'x'/'아님' → 'X'. 그 외 ''."""
    v = str(value or "").strip().upper()
    if not v:
        return ""
    if v[0] == "O" or v.startswith("맞"):
        return "O"
    if v[0] == "X" or v.startswith("아"):
        return "X"
    return ""


def feedback_mailto(to_addr: str, verdict: str, notice_id: str) -> str:
    """클릭하면 '제목이 채워진 메일 작성창'이 열리는 mailto 링크(발송은 사용자가 직접).

    MAIL_FEEDBACK_SECRET 이 설정되면 제목 끝에 HMAC 서명 토큰을 붙여 위조를 막는다(#132).
    """
    v = normalize_verdict(verdict) or "O"
    nid = str(notice_id).strip()
    subject = f"{SUBJECT_TAG} {v} {nid}"
    sig = feedback_token.sign(v, nid)
    if sig:
        subject += f" {sig}"
    return f"mailto:{quote(str(to_addr).strip())}?subject={quote(subject, safe='')}"


def feedback_link_label(url: str) -> str:
    """mailto 피드백 링크의 사람이 읽는 라벨(HTML 앵커 텍스트용). 피드백 링크가 아니면 ''."""
    if not str(url or "").lower().startswith("mailto:"):
        return ""
    parsed = parse_feedback_subject(unquote(str(url)))
    if not parsed:
        return ""
    return "⭕ 맞아요" if parsed["verdict"] == "O" else "❌ 아니에요"


def render_feedback_block(items: list, to_addr: str, *, limit: int = MAX_FEEDBACK_ITEMS) -> str:
    """digest 하단 '이 추천 맞았나요?' 섹션(plain text).

    plain 파트에는 mailto URL 이 그대로 보이고, HTML 파트에서 '⭕ 맞아요 / ❌ 아니에요'
    앵커로 바뀐다(monitor._linkify_html). 항목이 없거나 주소가 없으면 빈 문자열.
    """
    rows = [it for it in (items or []) if str((it or {}).get("id") or "").strip()]
    if not rows or not str(to_addr or "").strip():
        return ""
    lines = [
        "",
        "────────────────────────────────",
        "🙋 이 추천, 맞았나요? — 아래 링크를 누르면 메일 작성창이 자동으로 열립니다.",
        "   그대로 '전송'만 누르면 정답으로 기록돼 다음부터 더 정확해집니다. (한 건만 눌러도 도움돼요)",
        "",
    ]
    for n, it in enumerate(rows[:limit], 1):
        title = str(it.get("title") or "(제목없음)").strip()[:60]
        nid = str(it["id"]).strip()
        lines.append(f"{n}. {title}")
        lines.append(
            f"   {feedback_mailto(to_addr, 'O', nid)}   {feedback_mailto(to_addr, 'X', nid)}"
        )
    if len(rows) > limit:
        lines.append(f"…외 {len(rows) - limit}건 (피드백 링크는 상위 {limit}건만 표시)")
    return "\n".join(lines) + "\n"


def parse_feedback_subject(subject: str) -> dict | None:
    """`[MAIL-FB] X PBLN_0000...` 제목에서 {'verdict','id'} 추출. 형식 아니면 None."""
    if not subject:
        return None
    s = str(subject).replace("\r", " ").replace("\n", " ")
    m = _SUBJECT_RE.search(s)
    if not m:
        # 메일 클라이언트가 제목을 통째로 퍼센트 인코딩해 보내는 경우 대비
        m = _SUBJECT_RE.search(unquote(s))
        if not m:
            return None
    nid = unquote(m.group(2)).strip().rstrip(".,;)")
    if not nid:
        return None
    verdict = m.group(1).upper()
    # HMAC 검증(#132): MAIL_FEEDBACK_SECRET 설정 시 서명 없거나 틀리면 위조로 간주해 버린다.
    # 키 미설정이면 verify 는 항상 True(하위호환 — 서명 없던 기존 피드백도 그대로 수집).
    if not feedback_token.verify(verdict, nid, m.group(3)):
        return None
    return {"verdict": verdict, "id": nid}


def load_feedback_labels(path: Path | None = None) -> dict[str, dict]:
    """feedback_labels.jsonl → {id: record}. 같은 id 는 마지막(최신) 줄이 이긴다."""
    p = Path(path) if path else LABELS_PATH
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                i = str(d.get("id") or "").strip()
                v = normalize_verdict(d.get("verdict"))
                if not i or not v:
                    continue
                d["id"], d["verdict"] = i, v
                out[i] = d
    except OSError:
        return out
    return out


def feedback_verdicts(path: Path | None = None) -> dict[str, str]:
    """{id: 'O'|'X'} — 측정(accuracy_matrix)이 쓰는 사람 정답 맵."""
    return {i: r["verdict"] for i, r in load_feedback_labels(path).items()}


def merge_feedback_labels(records: list[dict], path: Path | None = None) -> dict:
    """수집한 피드백을 골든 파일에 누적(append-only). 같은 id 재피드백은 최신 verdict 반영.

    반환: {"added","updated","unchanged","invalid","total"}
    """
    p = Path(path) if path else LABELS_PATH
    stats = {"added": 0, "updated": 0, "unchanged": 0, "invalid": 0}
    # 읽기→병합→교체 전체를 한 잠금에 넣어 IMAP 수집/수동 실행이 겹쳐도 사람 라벨을 잃지 않는다.
    with locked_path(p):
        existing = load_feedback_labels(p)
        changed = False
        for rec in records or []:
            nid = str((rec or {}).get("id") or "").strip()
            verdict = normalize_verdict((rec or {}).get("verdict"))
            if not nid or not verdict:
                stats["invalid"] += 1
                continue
            prev = existing.get(nid)
            now = str(rec.get("received") or _now_iso())
            if prev is None:
                existing[nid] = {
                    "id": nid,
                    "verdict": verdict,
                    "tier": "C",
                    "source": str(rec.get("source") or "mail-feedback"),
                    "title": str(rec.get("title") or "")[:110],
                    "first_seen": now,
                    "last_seen": now,
                }
                stats["added"] += 1
                changed = True
            elif prev.get("verdict") != verdict:
                prev.update({"verdict": verdict, "tier": "C", "last_seen": now})
                if rec.get("title") and not prev.get("title"):
                    prev["title"] = str(rec["title"])[:110]
                stats["updated"] += 1
                changed = True
            else:
                stats["unchanged"] += 1
        if changed:
            p.parent.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(existing[i], ensure_ascii=False) for i in sorted(existing)]
            atomic_write_bytes_while_locked(
                p, ("\n".join(lines) + "\n").encode("utf-8"), backup=True,
            )
    stats["total"] = len(existing)
    return stats
