"""공고 안내 메일 본문 (표시 전용) — 지원유형별 섹션 + 공고별 3줄 카드.

2026-10 개편(모바일 가독성):
  - 상태·적합 열 삭제, 다열 표 → 공고별 블록(1줄: 제목 링크, 2줄: 💰 지원내용(있을 때만), 3줄: 기관 · 대상 · 지역 · 마감)
  - 지원유형(바우처/지원금/…)별 섹션, 번호 없음(제목으로 바로 시작)
  - '지원' 값은 섹션 제목으로만 쓰고 행에는 출력하지 않는다.
수집·매칭·발송 정책은 변경하지 않는다. 추천이유/바로가기/사이트명은 만들지 않는다.

plain 형식(파싱 가능한 고정 문법):
    📋 지원사업 공고 목록
    ■ 바우처 (2건)
    제목
       💰 최대 3,000만원 · 지원내용 요약
       기관 · 대상 · 지역 · 10/20 (D-8)
       https://...
"""
from __future__ import annotations

import html
import re
from typing import Callable

# 행 데이터 키(표시는 블록). '지원'은 섹션 분류용.
COLUMNS: tuple[str, ...] = ("공고", "지원", "대상", "기관", "지역", "마감")
META_COLUMNS: tuple[str, ...] = ("기관", "대상", "지역", "마감")
HEADER_LINE = "📋 지원사업 공고 목록"
EMPTY_DIGEST = "현재 조건에 맞는 신규 공고가 없습니다."
_TITLE_URL_RE = re.compile(r"^(?P<title>.*?)(?:\s*«(?P<url>https?://[^»]+)»)?\s*$", re.DOTALL)
_MISSING = "확인필요"
_PARSE_FAIL = "추출실패"
_META_SEP = " · "
_SUPPORT_PREFIX = "💰 "
_INDENT = "   "
_SECTION_RE = re.compile(r"^■ (?P<name>.+?) \((?P<n>\d+)건\)$")
_DATE_RE = re.compile(r"^\d{1,4}/\d{1,2}")

# 지원 셀 값 → 섹션 이름. 순서 = 메일 섹션 순서.
SECTION_ORDER: tuple[str, ...] = ("바우처", "지원금", "비용지원", "시설·입주", "판로·실증", "기타")
_SECTION_ALIAS = {
    "바우처": "바우처",
    "지원금/사업비": "지원금",
    "지원금": "지원금",
    "비용지원": "비용지원",
    "시설/입주": "시설·입주",
    "판로/실증": "판로·실증",
}


def section_of(support: object) -> str:
    # 섹션명 자체(parse_plain_table 이 '지원'에 넣는 값: '판로·실증'·'시설·입주')도 그대로 인정.
    # 없으면 HTML 재렌더 때 전부 '기타'로 합쳐져 plain(판로·실증 1 + 기타 3)과 HTML(기타 6)이 어긋났다.
    key = str(support or "").strip()
    if key in SECTION_ORDER:
        return key
    return _SECTION_ALIAS.get(key, "기타")


def group_rows(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """섹션별로 묶는다(입력 순서 유지, 섹션은 SECTION_ORDER 순)."""
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(section_of(row.get("지원")), []).append(row)
    order = list(SECTION_ORDER) + [k for k in buckets if k not in SECTION_ORDER]
    return [(name, buckets[name]) for name in order if buckets.get(name)]


def notice_url(item: dict) -> str:
    for key in ("source_url", "link"):
        raw = str(item.get(key) or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
    return ""


def encode_notice_cell(title: str, url: str) -> str:
    title = (title or "(제목없음)").replace("|", "/").strip() or "(제목없음)"
    url = (url or "").strip()
    if url:
        return f"{title} «{url}»"
    return title


def decode_notice_cell(cell: str) -> tuple[str, str]:
    text = str(cell or "").strip()
    m = _TITLE_URL_RE.match(text)
    if not m:
        return text or "(제목없음)", ""
    title = (m.group("title") or "").strip() or "(제목없음)"
    url = (m.group("url") or "").strip()
    return title, url


def _clean(value: object) -> str:
    text = str(value if value is not None else _MISSING)
    text = " ".join(text.replace("·", ",").split())
    return text or _MISSING


_PROVINCE_SHORT = {"충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남",
                   "경상북도": "경북", "경상남도": "경남"}
_REGION_SUFFIX_RE = re.compile(r"(특별자치시|특별자치도|특별시|광역시|도)$")
ORG_MAX = 10
PLAIN_SUPPORT_MAX = 40


def _plain_support(text: str, limit: int = PLAIN_SUPPORT_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def short_region(value: str) -> str:
    """'서울특별시 전체'→'서울', '경기도 전체'→'경기', '전국' 유지 (카드 3줄 표시용)."""
    text = (value or "").strip()
    if text.endswith(" 전체"):
        text = text[:-3].strip()
    out = []
    for tok in text.split(" "):
        tok = _PROVINCE_SHORT.get(tok, tok)
        short = _REGION_SUFFIX_RE.sub("", tok)
        out.append(short if len(short) >= 2 else tok)
    return " ".join(out) or value


def short_org(value: str, limit: int = ORG_MAX) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _meta_values(row: dict) -> list[str]:
    org, target, region, deadline = [_clean(row.get(col)) for col in META_COLUMNS]
    return [short_org(org), target, short_region(region), deadline]


_HIDDEN_META = {_MISSING, _PARSE_FAIL, "전체"}


def _known_meta(row: dict) -> list[str]:
    """메타 줄: 확인필요·추출실패 칸은 숨기고 아는 값만. 마감은 항상 마지막에 표시."""
    if row.get("_meta") is not None:      # parse_plain_table 로 읽은 행: 이미 걸러진 값
        return list(row["_meta"])
    org, target, region, deadline = _meta_values(row)
    known = [v for v in (org, target, region) if v and v not in _HIDDEN_META]
    if deadline in (_MISSING, _PARSE_FAIL, "", "마감일 확인"):
        deadline = _MISSING                # 마감 불명: 회색 '확인필요'(D-day 없음)
    return known + [deadline]


_DEADLINE_PART_RE = re.compile(r"^(?:\d{1,2}/\d{1,2}(?: \(D[-+]\d+\))?|상시|확인필요)$")


def _is_deadline_part(text: str) -> bool:
    return bool(_DEADLINE_PART_RE.match((text or "").strip()))


def _meta_text(row: dict) -> str:
    return _META_SEP.join(_known_meta(row))


def render_plain(rows: list[dict], *, preamble: str = "") -> str:
    if not rows:
        return EMPTY_DIGEST
    lines: list[str] = []
    pre = (preamble or "").rstrip()
    if pre:
        lines.append(pre)
        lines.append("")
    lines.append(HEADER_LINE)
    for name, sec_rows in group_rows(rows):
        lines.append("")
        lines.append(f"■ {name} ({len(sec_rows)}건)")
        for no, row in enumerate(sec_rows, 1):
            title = " ".join(str(row.get("공고") or "(제목없음)").split()) or "(제목없음)"
            lines.append(title)
            support = " ".join(str(row.get("지원내용") or "").split())
            if support:
                lines.append(_INDENT + _SUPPORT_PREFIX + _plain_support(support))
            meta_line = _meta_text(row)
            if meta_line:
                lines.append(_INDENT + meta_line)
            url = str(row.get("url") or "").strip()
            if url:
                lines.append(_INDENT + url)
    return "\n".join(lines)


_FOOTER_RE = re.compile(r"^\s*(?:[─━—=_\-]{5,}|🙋|ⓘ|AI 한줄 메모)")


def _is_footer_line(line: str) -> bool:
    return bool(_FOOTER_RE.match(line or ""))


def parse_plain_table(body: str) -> tuple[str, list[dict] | None, str]:
    """본문에서 공고 목록을 분리한다. 목록이 없으면 rows=None.

    rows 각 항목: 공고/url/지원(섹션명)/기관/대상/지역/마감/_no
    """
    text = body or ""
    idx = text.find(HEADER_LINE)
    if idx < 0:
        return text, None, ""
    before = text[:idx].rstrip()
    rest_lines = text[idx + len(HEADER_LINE):].split("\n")
    if rest_lines and rest_lines[0].strip() == "":
        rest_lines = rest_lines[1:]
    rows: list[dict] = []
    section = ""
    cur: dict | None = None
    consumed = 0
    pending_blank = 0
    for i, line in enumerate(rest_lines):
        if not line.strip():
            pending_blank += 1
            continue
        if _is_footer_line(line):
            # 꼬리말(구분선·피드백 안내)에서 카드 파싱 중단 — 카드로 오인하면 '확인필요 ×4' 카드가 생긴다.
            break
        sm = _SECTION_RE.match(line)
        # 2026-10: 번호 없이 제목으로 시작. 섹션 안의 들여쓰기 없는 줄 = 새 공고
        # (빈 줄 뒤에 오는 줄은 섹션 헤더 직후가 아니면 꼬리말로 보고 중단)
        im = bool(section) and not line.startswith(" ") and (pending_blank == 0 or cur is None)
        if sm:
            section = sm.group("name")
            cur = None
            pending_blank = 0
            consumed = i + 1
            continue
        elif im:
            sec_no = 1 + sum(1 for r in rows if r["지원"] == section)
            cur = {"공고": line.strip() or "(제목없음)", "url": "", "지원": section, "_no": sec_no}
            for col in META_COLUMNS:
                cur[col] = _MISSING
            cur["지원내용"] = ""
            rows.append(cur)
        elif cur is not None and line.startswith(_INDENT) and not line.startswith(_INDENT + " "):
            content = line[len(_INDENT):].strip()
            if content.startswith("http://") or content.startswith("https://"):
                cur["url"] = content
            elif content.startswith(_SUPPORT_PREFIX):
                cur["지원내용"] = content[len(_SUPPORT_PREFIX):].strip()
            else:
                parts = [p for p in content.split(_META_SEP) if p.strip()]
                if not parts or cur.get("_meta") is not None:
                    break
                # 확인필요 칸은 숨겨 출력하므로 칸 수가 1~4로 가변. 마지막 = 마감.
                cur["마감"] = parts[-1] if _is_deadline_part(parts[-1]) else ""
                if len(parts) == 4:
                    cur["기관"], cur["대상"], cur["지역"] = parts[0], parts[1], parts[2]
                cur["_meta"] = parts
        else:
            break
        consumed = i + 1
        pending_blank = 0
    after = "\n".join(rest_lines[consumed:]).strip("\n")
    return before, rows, after


_FONT = "font-family:'Noto Sans CJK KR','Apple SD Gothic Neo','Malgun Gothic',sans-serif"


def render_html_blocks(rows: list[dict]) -> str:
    """Gmail 모바일용 블록(인라인 스타일만 — Gmail 은 <style> 제거)."""
    out: list[str] = [
        f"<div style=\"max-width:640px;{_FONT};word-break:keep-all;overflow-wrap:break-word\">"
    ]
    for name, sec_rows in group_rows(rows):
        out.append(
            "<div style='margin:14px 0 0;background:#eef2ff;border-left:4px solid #4f46e5;"
            "padding:8px;font-weight:700'>"
            f"{html.escape(name)} ({len(sec_rows)}건)</div>"
        )
        for no, row in enumerate(sec_rows, 1):
            title = html.escape(str(row.get("공고") or "(제목없음)"))
            url = str(row.get("url") or "").strip()
            if url:
                title = (f'<a href="{html.escape(url, quote=True)}" '
                         "style='color:#1a5fd6;text-decoration:none'>"
                         f"<span style='color:#1a5fd6'>{title}</span></a>")
            known = _known_meta(row)
            deadline = known[-1] if known and _is_deadline_part(known[-1]) else ""
            others = known[:-1] if deadline else known
            meta = html.escape(_META_SEP.join(others) + (_META_SEP if others and deadline else ""))
            dl = (f"<span style='color:#d93025;font-weight:700;white-space:nowrap'>{html.escape(deadline)}</span>"
                  if _DATE_RE.match(deadline) else (f"<span style='white-space:nowrap'>{html.escape(deadline)}</span>" if deadline else ""))
            support = " ".join(str(row.get("지원내용") or "").split())
            support_html = (
                "<div style='font-size:14px;font-weight:700;margin-top:4px;display:block;"
                "white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                f"{html.escape(_SUPPORT_PREFIX + support)}</div>" if support else ""
            )
            meta_html = (f"<div style='font-size:13px;color:#777;margin-top:3px'>{meta}{dl}</div>"
                         if (meta or dl) else "")
            out.append(
                "<div style='padding:12px 0;border-bottom:1px solid #eee'>"
                f"<div style='font-size:16px'>{title}</div>"
                f"{support_html}"
                f"{meta_html}"
                "</div>"
            )
    out.append("</div>")
    return "".join(out)


# 하위호환 이름(외부 호출부 보호)
render_html_table = render_html_blocks


def html_email_inner(body: str, linkify: Callable[[str], str]) -> str:
    """Gmail용 HTML. 공고 목록이 있으면 섹션 블록, 나머지는 기존 링크화."""
    before, rows, after = parse_plain_table(body)
    if rows is None:
        stripped = (body or "").strip()
        if stripped == EMPTY_DIGEST:
            return f"<p>{html.escape(EMPTY_DIGEST)}</p>"
        return f"<pre style='white-space:pre-wrap;font-family:inherit'>{linkify(body or '')}</pre>"

    parts: list[str] = []
    if before.strip():
        parts.append(f"<div style='max-width:640px'>{linkify(before)}</div>")
    if not rows:
        parts.append(f"<p>{html.escape(EMPTY_DIGEST)}</p>")
    else:
        parts.append(render_html_blocks(rows))
    if after.strip():
        parts.append(f"<div style='max-width:640px'>{linkify(after)}</div>")
    return "".join(parts)


def cell_or_fallback(value: object, *, parse_error: bool = False) -> str:
    if parse_error:
        return _PARSE_FAIL
    text = str(value or "").strip()
    return text if text else _MISSING
