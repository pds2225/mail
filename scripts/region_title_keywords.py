r"""region_title_keywords — 공고 '제목'에서 지원대상 지역을 읽어내는 키워드 규칙 (Tier B 약라벨 전용).

기존 규칙은 제목 선두 대괄호 태그가 **통째로 광역 지역명**일 때만 라벨했다([경북] 등).
그 결과 `[미추홀구]`·`[인천테크노파크]`·`[전남광주]` 처럼 지역이 분명한데도 라벨을 못 만들고
보류되는 공고가 많았다(실측 221건 보류). 이 모듈은 **제목 전체**에서 아래 신호를 읽어
지역을 판정한다.

  1) 광역 지역명(정식·축약·변형)            예) 인천광역시 / 인천 / 인천테크노파크
  2) 시군구명(접미어 시·군·구 포함 형태만)  예) 미추홀구 → 인천, 김포시 → 경기
  3) 권역 표기                              예) 전남광주 → 전남+광주, 대구ㆍ경북 → 대구+경북
  4) 전국 표기(명시적일 때만)               예) 전국단위 / 지역무관

설계 근거(실측): 공고 제목 4,551건 코퍼스를 채굴해 만든 표다. 채굴에서 확인된 실제 오탐
위험은 코드에 부정패턴으로 박아 두었다.
  · "수산부산물·공정부산물" → '부산' 오탐        · "세종대왕/세종문화" → '세종' 오탐
  · "경북대학교"=대구, "충남대"=대전, "전남대"=광주 → **대학명은 지역신호에서 제외**
  · "광주"는 광주광역시/경기 광주시 모호 → 단독이면 라벨 금지(권역·광역 힌트 있을 때만)
  · "인천시, 전국 최대 규모…" → '전국' 단독 등장은 신호 아님(명시 표현만 인정)

안전 원칙
  · 판정기(monitor·company_match·region_clusters)의 코드·표를 **일절 import 하지 않는다**
    — 정답지가 판정기를 재생산하면 채점이 무의미해지기 때문(순환 자기채점 방지).
  · 애매하면 라벨을 만들지 않는다(라벨 오염 < 빈칸). 애매 사유는 리뷰 큐로 넘긴다.
  · 여기서 나오는 라벨은 항상 **Tier B(약라벨)** 다. Tier A(소스 제공)·Tier C(사람확인)를
    덮어쓰지 않는다(호출 측 책임).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 광역 17개 정식명칭 (골든 라벨 값 형식) ────────────────────────────────
SIDO_CANON: dict[str, str] = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}
_SIDO_ORDER = list(SIDO_CANON)  # 다중 라벨 정렬 기준(행정 표준 순서)

# 광역 표기 변형 → 키. 긴 것부터 매칭한다.
SIDO_ALIASES: dict[str, str] = {
    "서울특별시": "서울", "서울시": "서울", "서울": "서울",
    "부산광역시": "부산", "부산시": "부산", "부산": "부산",
    "대구광역시": "대구", "대구시": "대구", "대구": "대구",
    "인천광역시": "인천", "인천시": "인천", "인천": "인천",
    "광주광역시": "광주",                      # '광주'·'광주시' 단독은 모호 → 아래서 따로 처리
    "대전광역시": "대전", "대전시": "대전", "대전": "대전",
    "울산광역시": "울산", "울산시": "울산", "울산": "울산",
    "세종특별자치시": "세종", "세종시": "세종", "세종": "세종",
    "경기도": "경기", "경기": "경기",
    "강원특별자치도": "강원", "강원도": "강원", "강원": "강원",
    "충청북도": "충북", "충북": "충북",
    "충청남도": "충남", "충남": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전북": "전북",
    "전라남도": "전남", "전남": "전남",
    "경상북도": "경북", "경북": "경북",
    "경상남도": "경남", "경남": "경남",
    "제주특별자치도": "제주", "제주도": "제주", "제주": "제주",
}

# ── 시군구 → 광역 (접미어 시·군·구 포함 형태로만 매칭) ────────────────────
# 여러 광역에 같은 이름이 있는 것(중구·서구·동구·남구·북구·강서구·광주시·고성군)은
# AMBIGUOUS_SGG 로 빼서 라벨을 만들지 않는다.
SGG_TO_SIDO: dict[str, str] = {}


def _reg(sido: str, names: str) -> None:
    for n in names.split():
        SGG_TO_SIDO[n] = sido


_reg("서울", "종로구 용산구 성동구 광진구 동대문구 중랑구 성북구 강북구 도봉구 노원구 은평구 "
             "서대문구 마포구 양천구 구로구 금천구 영등포구 동작구 관악구 서초구 강남구 송파구 강동구")
_reg("부산", "영도구 부산진구 동래구 해운대구 사하구 금정구 연제구 수영구 사상구 기장군")
_reg("대구", "수성구 달서구 달성군 군위군")
_reg("인천", "미추홀구 연수구 남동구 부평구 계양구 강화군 옹진군")
_reg("광주", "광산구")
_reg("대전", "유성구 대덕구")
_reg("울산", "울주군")
_reg("경기", "수원시 성남시 의정부시 안양시 부천시 광명시 평택시 동두천시 안산시 고양시 과천시 "
             "구리시 남양주시 오산시 시흥시 군포시 의왕시 하남시 용인시 파주시 이천시 안성시 "
             "김포시 화성시 양주시 포천시 여주시 연천군 가평군 양평군")
_reg("강원", "춘천시 원주시 강릉시 동해시 태백시 속초시 삼척시 홍천군 횡성군 영월군 평창군 정선군 "
             "철원군 화천군 양구군 인제군 양양군")
_reg("충북", "청주시 충주시 제천시 보은군 옥천군 영동군 증평군 진천군 괴산군 음성군 단양군")
_reg("충남", "천안시 공주시 보령시 아산시 서산시 논산시 계룡시 당진시 금산군 부여군 서천군 청양군 "
             "홍성군 예산군 태안군")
_reg("전북", "전주시 군산시 익산시 정읍시 남원시 김제시 완주군 진안군 무주군 장수군 임실군 순창군 "
             "고창군 부안군")
_reg("전남", "목포시 여수시 순천시 나주시 광양시 담양군 곡성군 구례군 고흥군 보성군 화순군 장흥군 "
             "강진군 해남군 영암군 무안군 함평군 영광군 장성군 완도군 진도군 신안군")
_reg("경북", "포항시 경주시 김천시 안동시 구미시 영주시 영천시 상주시 문경시 경산시 의성군 청송군 "
             "영양군 영덕군 청도군 고령군 성주군 칠곡군 예천군 봉화군 울진군 울릉군")
_reg("경남", "창원시 진주시 통영시 사천시 김해시 밀양시 거제시 양산시 의령군 함안군 창녕군 남해군 "
             "하동군 산청군 함양군 거창군 합천군")
_reg("제주", "제주시 서귀포시")

# 여러 광역에 중복 존재 → 단독으로는 지역 확정 불가
AMBIGUOUS_SGG: set[str] = {"중구", "서구", "동구", "남구", "북구", "강서구", "광주시", "고성군"}

# ── 권역(복수 광역) 표기 ─────────────────────────────────────────────────
# 공백 제거한 제목에서 매칭한다(예: "대구 ㆍ 경북" → "대구ㆍ경북").
AREA_PATTERNS: list[tuple[str, list[str]]] = [
    (r"전남광주|광주전남|광주[ㆍ·,/]전남|전남[ㆍ·,/]광주", ["전남", "광주"]),
    (r"대구경북|경북대구|대구[ㆍ·,/]경북|경북[ㆍ·,/]대구", ["대구", "경북"]),
    (r"대전세종충남충북|충남충북대전세종|대전세종충남|대전[ㆍ·,/]세종[ㆍ·,/]충남|"
     r"충남[ㆍ·,/]충북[ㆍ·,/]대전[ㆍ·,/]세종", ["대전", "세종", "충남", "충북"]),
    (r"부산울산경남|부울경|부산[ㆍ·,/]울산[ㆍ·,/]경남", ["부산", "울산", "경남"]),
    (r"서울인천경기|서울[ㆍ·,/]인천[ㆍ·,/]경기", ["서울", "인천", "경기"]),
    (r"대전충남|대전[ㆍ·,/]충남", ["대전", "충남"]),
]
# 광역 하위 권역 표기(경남서부·경기북부 등) → 해당 광역 1개
SUB_AREA_RX = re.compile(
    r"(서울|부산|대구|인천|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
    r"\s*(북부|남부|동부|서부|중부|권)")

# ── 전국(지역무관) 표기 — 명시적일 때만 인정 ──────────────────────────────
NATIONWIDE_RX = re.compile(
    r"전국\s*단위|전국\s*8도|전국\s*대상|전국\s*(?:공모|모집|접수|일원)|지역\s*무관|전국\s*어디"
)
# 수도권 표기(전국급 취급은 하지 않고 별도 라벨)
METRO_RX = re.compile(r"수도권")

# ── 오탐 방지: 지역명이 다른 뜻으로 쓰인 문자열은 매칭 전에 지운다 ─────────
NEGATIVE_PATTERNS: list[str] = [
    r"[가-힣A-Za-z]*부산물",                       # 수산부산물·공정부산물
    r"경기\s*(?:침체|불황|부양|변동|전망|동향|지표|회복|활성화)", r"[호불]경기",
    r"세종\s*(?:대왕|문화회관|로)", r"세종사이버",
    r"(?<=[가-힣])대전(?![가-힣])",                # 혁신대전·반도체대전·에너지대전(大展) = 지역 아님
    r"[가-힣A-Za-z]{1,10}대학교", r"[가-힣]{1,8}대학원", r"[가-힣]{1,6}대학(?![가-힣])",
    r"[가-힣]{1,4}대\s*(?:산학|창업지원단|LINC)",  # 경북대 산학협력단 등 축약 대학명
]
_NEG_RX = re.compile("|".join(NEGATIVE_PATTERNS))

# 선두 대괄호 태그
TAG_RX = re.compile(r"^\s*[\[\(【]\s*([^\]\)】]{1,30})\s*[\]\)】]")
# 지역 힌트 단어 — 태그가 지역 비슷한데 확정 못 했을 때만 리뷰 큐로 보내기 위한 필터
# (예: [울산대학교] 는 큐, [모집공고] 는 큐에도 올리지 않음)
_REGION_HINT_RX = re.compile(
    "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|"
    "충청|전라|경상|수도권")

# 광역 축약/변형 매칭용 정규식(긴 표기 우선)
_ALIAS_RX = re.compile("|".join(sorted((re.escape(a) for a in SIDO_ALIASES), key=len, reverse=True)))
# 시군구 매칭용 정규식(뒤에 한글이 이어지면 다른 단어 — 예: '연수구성' 방지)
_SGG_RX = re.compile(
    "(" + "|".join(sorted((re.escape(s) for s in list(SGG_TO_SIDO) + list(AMBIGUOUS_SGG)),
                          key=len, reverse=True)) + r")(?![가-힣])")
# 모호 지명(광주 단독)
_GWANGJU_RX = re.compile(r"광주(?!광역시|과학기술원)")


@dataclass
class RegionVerdict:
    """제목 1건에 대한 지역 판정 결과."""
    region_field: str | None = None       # 라벨(정식명칭, 다중이면 콤마)
    reason: str | None = None             # 라벨 없음 사유(리뷰 큐 사유). None=신호 자체가 없음
    labeled_by: str | None = None         # title_tag_region / title_region / title_area / title_nationwide
    tag: str = ""                         # 선두 대괄호 태그 원문
    evidence: list[str] = field(default_factory=list)


def _mask_negative(text: str) -> str:
    """지역명이 다른 뜻으로 쓰인 부분을 공백으로 지운다(대학명 포함)."""
    return _NEG_RX.sub(" ", text or "")


def _scan(text: str) -> tuple[set[str], list[str], set[str], bool]:
    """텍스트에서 지역 신호 수집 → (광역키 집합, 근거, 권역표기로 설명되는 집합, 모호신호여부)."""
    hits: set[str] = set()
    ev: list[str] = []
    area_hits: set[str] = set()
    ambiguous = False

    compact = re.sub(r"\s+", "", text)
    for pat, sidos in AREA_PATTERNS:
        m = re.search(pat, compact)
        if m:
            hits.update(sidos)
            area_hits.update(sidos)
            ev.append(f"권역:{m.group(0)}")
    for m in SUB_AREA_RX.finditer(text):
        hits.add(m.group(1))
        area_hits.add(m.group(1))
        ev.append(f"권역:{m.group(0)}")

    for m in _ALIAS_RX.finditer(text):
        key = SIDO_ALIASES[m.group(0)]
        hits.add(key)
        ev.append(m.group(0))

    for m in _SGG_RX.finditer(text):
        name = m.group(1)
        if name in AMBIGUOUS_SGG:
            ambiguous = True
            ev.append(f"모호:{name}")
            continue
        hits.add(SGG_TO_SIDO[name])
        ev.append(name)

    if "광주" not in hits and _GWANGJU_RX.search(text):
        ambiguous = True
        ev.append("모호:광주")
    return hits, ev, area_hits, ambiguous


def _canon(hits: set[str]) -> str:
    return ",".join(SIDO_CANON[k] for k in _SIDO_ORDER if k in hits)


def resolve_title_region(title: str) -> RegionVerdict:
    """공고 제목 → 지역 판정. 애매하면 라벨을 만들지 않고 사유만 남긴다."""
    raw = (title or "").strip()
    if not raw:
        return RegionVerdict()

    m = TAG_RX.match(raw)
    tag = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    body = raw[m.end():] if m else raw

    tag_txt = _mask_negative(tag)
    body_txt = _mask_negative(body)

    tag_hits, tag_ev, tag_area, tag_amb = _scan(tag_txt) if tag else (set(), [], set(), False)
    body_hits, body_ev, body_area, body_amb = _scan(body_txt)

    nationwide = bool(NATIONWIDE_RX.search(_mask_negative(raw)))
    metro = bool(METRO_RX.search(raw))

    # 태그에 지역이 있으면 태그가 기준(게시기관이 붙인 분류라 신뢰도 높음).
    # 본문 신호가 그 안을 좁혀주면(권역 → 특정 광역) 좁힌다.
    if tag_hits:
        hits, ev, area_hits = set(tag_hits), list(tag_ev), set(tag_area)
        narrowed = tag_hits & body_hits
        if len(tag_hits) > 1 and narrowed:
            hits, area_hits = set(narrowed), set()
            ev.append(f"본문좁힘:{','.join(sorted(narrowed))}")
        base_by = "title_tag_region"
    else:
        hits, ev, area_hits = set(body_hits), list(body_ev), set(body_area)
        base_by = "title_region"

    if hits and nationwide:
        # '[부산] 전국행사(부산한정)' 류 — 전국인지 지역한정인지 제목만으론 못 가른다
        return RegionVerdict(None, "nationwide_conflict", None, tag, ev + ["전국표기"])

    if len(hits) == 1:
        return RegionVerdict(_canon(hits), None, base_by, tag, ev)

    if len(hits) > 1:
        # 권역 표기(전남광주 등)가 '전부' 설명할 때만 복수 라벨. 권역 밖 지역이 섞였으면 충돌.
        if area_hits and hits <= area_hits:
            return RegionVerdict(_canon(hits), None, "title_area", tag, ev)
        return RegionVerdict(None, "region_conflict", None, tag, ev)

    if nationwide:
        return RegionVerdict("전국", None, "title_nationwide", tag, ev + ["전국표기"])
    if metro:
        return RegionVerdict("수도권", None, "title_metro", tag, ev + ["수도권"])

    if tag_amb or body_amb:
        return RegionVerdict(None, "ambiguous_region_name", None, tag, ev)
    if tag and _REGION_HINT_RX.search(tag):
        # 태그에 지역 비슷한 말이 있는데 확정 못 함(예: [울산대학교]) → 사람확인 큐
        return RegionVerdict(None, "org_or_unknown_tag", None, tag, ev)
    return RegionVerdict(None, None, None, tag, ev)
