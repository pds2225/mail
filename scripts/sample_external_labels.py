"""THE VC + 벤처스퀘어에서 외부라벨 후보 추출 — 사용자 품질 판단용 샘플."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

KST = timezone(timedelta(hours=9))
OUT_JSON = Path(__file__).resolve().parent.parent / "var" / "logs" / "external_label_samples.json"
OUT_MD = Path(__file__).resolve().parent.parent / "var" / "logs" / "external_label_samples.md"
MAX_EACH = 12

# monitor.py SUPPORT_TYPE_RULES 축소 매핑 (표시용)
SUPPORT_KW = {
    "지원금/바우처": ["바우처", "지원금", "보조금", "사업화", "자금", "grant", "R&D", "연구개발", "기술개발"],
    "컨설팅·교육·상담": ["멘토링", "컨설팅", "교육", "세미나", "설명회", "워크숍", "상담", "클리닉"],
    "투자": ["투자", "vc", "엔젤", "ir", "액셀러", "스케일업"],
    "그외": [],
}
TARGET_KW = {
    "예비창업": ["예비창업", "예비 창업"],
    "초기창업": ["초기창업", "스타트업", "창업기업", "창업"],
    "중소기업": ["중소기업", "중소·", "중소 "],
    "제조": ["제조", "공장", "스마트공장"],
}
REGION_KW = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "전국",
]
RECRUIT_KW = {
    "모집": ["모집", "참여기업", "참가기업", "교육생", "멘티", "공모"],
    "행사": ["행사", "포럼", "네트워킹", "설명회", "세미나"],
    "포상": ["포상", "시상"],
}


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip()


def _match_labels(text: str, rules: dict[str, list[str]]) -> list[str]:
    t = text.lower()
    out: list[str] = []
    for label, kws in rules.items():
        if label == "그외":
            continue
        if any(k.lower() in t for k in kws):
            out.append(label)
    return out or ["그외"]


def _regions(text: str) -> list[str]:
    if "전국" in text:
        return ["전국"]
    found = [r for r in REGION_KW if r != "전국" and r in text]
    return found or (["전국"] if not found else found)


def _confidence(category: str | None, tags: list[str], title: str) -> str:
    cat_labels = _match_labels(category or "", SUPPORT_KW) if category else []
    tag_labels = _match_labels(" ".join(tags), SUPPORT_KW) if tags else []
    title_labels = _match_labels(title, SUPPORT_KW)
    if cat_labels and tag_labels and cat_labels[0] == tag_labels[0] and cat_labels[0] != "그외":
        return "0.85"
    if category and cat_labels[0] != "그외":
        return "0.75"
    if title_labels[0] != "그외":
        return "0.65"
    if _regions(title) != ["전국"]:
        return "0.60"
    return "REVIEW"


def _label_record(
    *,
    source: str,
    title: str,
    external_url: str,
    agency: str | None,
    external_category: str | None,
    external_tags: list[str],
    target_text: str | None,
    region_text: str | None,
    deadline: str | None,
    official_url: str | None,
) -> dict:
    blob = " ".join(
        x for x in [title, external_category, " ".join(external_tags), target_text or "", region_text or "", agency or ""] if x
    )
    return {
        "source": source,
        "title": title,
        "external_url": external_url,
        "raw": {
            "agency": agency,
            "external_category": external_category,
            "external_tags": external_tags,
            "target_text": target_text,
            "region_text": region_text,
            "deadline": deadline,
            "official_url": official_url,
        },
        "derived_labels": {
            "support_type": _match_labels(blob, SUPPORT_KW),
            "target_stage": _match_labels(blob, TARGET_KW),
            "region": _regions(blob),
            "recruit_type": _match_labels(blob, RECRUIT_KW),
        },
        "confidence": _confidence(external_category, external_tags, title),
    }


def _parse_thevc_row_text(raw_title: str) -> dict:
    """THE VC 목록: 제목·마감·카테고리·기관이 한 줄에 붙는 패턴 분리 시도."""
    t = _norm(raw_title)
    agency = None
    category = None
    deadline = None
    tags: list[str] = []

    m = re.search(r"접수\s*마감일\s*(\d{4}-\d{2}-\d{2})", t)
    if m:
        deadline = m.group(1)

    # 카테고리: D-숫자 뒤 ~ 기관명 앞 (휴리스틱)
    m = re.search(
        r"D-\d+(?:[^·]*·([^·]+))?(?:([^·]+?)(?:액셀러|교육기관|정부|협회|재단|테크|진흥|TP|원))?$",
        t,
    )
    if m:
        chunk = m.group(1) or ""
        parts = [p.strip() for p in chunk.split("·") if p.strip()]
        if parts:
            category = parts[0]
            tags = parts[1:]

    for suffix in ("액셀러레이터", "교육기관", "정부", "협회/재단", "금융회사"):
        if t.endswith(suffix) or suffix in t[-40:]:
            idx = t.rfind(suffix)
            if idx > 20:
                agency = _norm(t[idx - 30 : idx + len(suffix)])
                agency = re.sub(r"^.*?(?=[가-힣(])", "", agency) or agency
            break

    title = t
    title = re.split(r"\s*NEW\s*|\s*공고\s*등록일", title)[0].strip()
    title = re.sub(r"접수\s*마감일.*$", "", title).strip()

    return {
        "title": title[:120],
        "agency": agency,
        "external_category": category,
        "external_tags": tags,
        "deadline": deadline,
    }


def collect_thevc(page, max_items: int) -> list[dict]:
    url = "https://thevc.kr/grants"
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)
    soup = BeautifulSoup(page.content(), "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in soup.select("a[href*='grants?id=']"):
        href = a.get("href", "")
        link = urljoin(url, href)
        if link in seen:
            continue
        seen.add(link)
        parsed = _parse_thevc_row_text(a.get_text())
        if not parsed["title"]:
            continue
        items.append(
            _label_record(
                source="THEVC",
                title=parsed["title"],
                external_url=link,
                agency=parsed["agency"],
                external_category=parsed["external_category"],
                external_tags=parsed["external_tags"],
                target_text=None,
                region_text=None,
                deadline=parsed["deadline"],
                official_url=None,
            )
        )
        if len(items) >= max_items:
            break

    # 상세 4건 official_url + 본문 힌트
    for rec in items[:4]:
        try:
            page.goto(rec["external_url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            dsoup = BeautifulSoup(page.content(), "html.parser")
            text = _norm(dsoup.get_text(" ")[:3000])
            hosts = ("bizinfo.go.kr", "k-startup.go.kr", "go.kr", "or.kr")
            for a in dsoup.select("a[href^='http']"):
                h = a.get("href", "")
                if any(x in h for x in hosts) and "fileDownload" not in h:
                    rec["raw"]["official_url"] = h
                    break
            if not rec["raw"]["official_url"]:
                for a in dsoup.select("a[href^='http']"):
                    h = a.get("href", "")
                    if any(x in h for x in hosts):
                        rec["raw"]["official_url"] = h
                        break
            if "전국" in text:
                rec["raw"]["region_text"] = "전국"
            for r in REGION_KW:
                if r in text and r != "전국":
                    rec["raw"]["region_text"] = r
                    break
        except Exception:
            pass
    return items


def collect_venturesquare(page, max_items: int) -> list[dict]:
    url = "https://www.venturesquare.net/announcement/"
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3500)
    soup = BeautifulSoup(page.content(), "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    # 카드: h5 제목 + 주변 메타
    for h5 in soup.select("h5"):
        title = _norm(h5.get_text())
        if len(title) < 8:
            continue
        a = h5.find_parent("a") or h5.select_one("a")
        if not a:
            parent = h5.parent
            a = parent.select_one("a[href]") if parent else None
        if not a:
            continue
        link = urljoin(url, a.get("href", ""))
        if link in seen:
            continue
        seen.add(link)

        card = h5
        for _ in range(6):
            if card.parent and card.name not in ("article", "div", "li"):
                card = card.parent
            else:
                break
        card_text = _norm(card.get_text(" "))

        deadline = None
        m = re.search(r"마감\s*(\d+)\s*일\s*전", card_text)
        if m:
            deadline = f"D-{m.group(1)}"

        category = None
        region = None
        agency = None
        tags: list[str] = []

        cat_candidates = [
            "글로벌", "기술개발(R&D)", "멘토링ㆍ컨설팅ㆍ교육", "사업화",
            "시설ㆍ공간ㆍ보육", "융자", "융자ㆍ보증", "인력", "정책자금",
            "창업교육", "판로ㆍ해외진출", "행사ㆍ네트워크",
        ]
        for c in cat_candidates:
            if c in card_text:
                category = c
                break

        if "전국" in card_text:
            region = "전국"
        else:
            for r in REGION_KW:
                if r in card_text and r != "전국":
                    region = r + ("광역시" if r in ("서울", "부산", "대구", "인천", "광주", "대전", "울산") else "")
                    break

        # 기관: 카테고리·지역 뒤 마지막 토큰 (휴리스틱)
        tail = card_text.replace(title, "").strip()
        parts = [p.strip() for p in re.split(r"\s{2,}|\n", tail) if p.strip()]
        if parts:
            agency = parts[-1][:80]

        items.append(
            _label_record(
                source="VENTURESQUARE",
                title=title,
                external_url=link,
                agency=agency,
                external_category=category,
                external_tags=tags,
                target_text=None,
                region_text=region,
                deadline=deadline,
                official_url=None,
            )
        )
        if len(items) >= max_items:
            break

    for rec in items[:4]:
        try:
            page.goto(rec["external_url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            dsoup = BeautifulSoup(page.content(), "html.parser")
            for a in dsoup.select("a[href^='http']"):
                h = a.get("href", "")
                if any(x in h for x in ("bizinfo.go.kr", "k-startup.go.kr", "go.kr")) and "venturesquare" not in h:
                    rec["raw"]["official_url"] = h
                    break
        except Exception:
            pass
    return items


def _to_md(payload: dict) -> str:
    lines = [
        f"# 외부라벨 샘플 — {payload['generated_at']}",
        "",
        "사용자 품질 판단용. `derived_labels`가 자동 추정 정답 후보입니다.",
        "",
    ]
    for source in ("THEVC", "VENTURESQUARE"):
        block = payload["sources"].get(source, [])
        lines.append(f"## {source} ({len(block)}건)")
        lines.append("")
        for i, rec in enumerate(block, 1):
            d = rec["derived_labels"]
            r = rec["raw"]
            lines.append(f"### {i}. {rec['title'][:80]}")
            lines.append(f"- URL: {rec['external_url']}")
            lines.append(f"- 원본 카테고리: `{r.get('external_category')}`")
            lines.append(f"- 원본 기관: `{r.get('agency')}`")
            lines.append(f"- 원본 지역: `{r.get('region_text')}`")
            lines.append(f"- 마감: `{r.get('deadline')}`")
            lines.append(f"- 공식 URL: `{r.get('official_url')}`")
            lines.append(
                f"- **추정 라벨** | support: `{d['support_type']}` | target: `{d['target_stage']}` "
                f"| region: `{d['region']}` | recruit: `{d['recruit_type']}` | confidence: `{rec['confidence']}`"
            )
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    payload: dict = {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "sources": {},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        try:
            payload["sources"]["THEVC"] = collect_thevc(page, MAX_EACH)
            payload["sources"]["VENTURESQUARE"] = collect_venturesquare(page, MAX_EACH)
        finally:
            browser.close()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_to_md(payload), encoding="utf-8")
    print(json.dumps({
        "thevc": len(payload["sources"]["THEVC"]),
        "venturesquare": len(payload["sources"]["VENTURESQUARE"]),
        "json": str(OUT_JSON),
        "md": str(OUT_MD),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
