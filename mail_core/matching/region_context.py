"""지원대상 문맥과 명시적 제외지역 추출. 그룹·기업 경로가 함께 사용한다."""
from __future__ import annotations

import re

_ALIASES = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}
_SHORT = "서울 부산 대구 인천 광주 대전 울산 세종 경기 강원 충북 충남 전북 전남 경북 경남 제주".split()
_REGION = "|".join(sorted([*_ALIASES, *_SHORT], key=len, reverse=True))
_REGION_MATCHER = re.compile(_REGION)
_EXCLUSION = re.compile(
    rf"(?<![가-힣])(?P<regions>(?:{_REGION})(?:\s*[·ㆍ,/및]+\s*(?:{_REGION}))*)"
    r"\s*(?:지역\s*)?(?:소재\s*)?(?:(?:중소)?기업\s*)?(?:은|는|을|를)?\s*제외(?:한)?"
)
_ISLAND_EXCLUSION = re.compile(r"도서\s*(?:지역\s*)?(?:을|를|은|는)?\s*제외(?:한)?")
_TARGET_LABEL = r"(?:지원\s*대상|신청\s*(?:대상|자격)|참여\s*대상|지원\s*지역)\s*[:：]"
_CONTACT = re.compile(
    r"(?:기관\s*(?:주소|소재지)|주소\s*[:：]|소재지\s*[:：]|문의(?:처)?|연락처|담당(?:부서|자)|"
    r"주관\s*기관|공고\s*기관|운영\s*기관|접수처|사무국|전화|이메일|☎|tel|fax)"
    rf"\s*[:：]?[^\n;]*?(?=(?:{_TARGET_LABEL})|[\n;]|$)", re.IGNORECASE,
)
_AGENCY = re.compile(
    rf"(?:{_REGION})\s*(?:시청|도청|테크노파크|경제진흥원|산업진흥원|창조경제혁신센터)"
)


def short_region(value: str) -> str:
    return _ALIASES.get(value, value)


def agency_region_hints(text: str) -> list[str]:
    """기관 메타데이터의 약한 단서. 신청자 부적격 판정에는 사용하지 않는다."""
    return sorted({short_region(token) for token in _REGION_MATCHER.findall(text or "")})


def strip_agency_context(text: str) -> str:
    """줄바꿈·지원대상 라벨을 보존해 같은 줄의 신청자격까지 지우지 않는다."""
    return _AGENCY.sub(" ", _CONTACT.sub(" ", text or ""))


def region_exclusions(text: str) -> dict:
    text = strip_agency_context(text)
    excluded = {
        _ALIASES.get(token, token)
        for match in _EXCLUSION.finditer(text)
        for token in _REGION_MATCHER.findall(match.group("regions"))
    }
    return {"excluded_regions": sorted(excluded),
            "island_excluded": bool(_ISLAND_EXCLUSION.search(text))}


def applicant_region_text(text: str) -> str:
    """제외된 지역명도 긍정적인 지역 근거에서 제거한다."""
    return _ISLAND_EXCLUSION.sub(" ", _EXCLUSION.sub(" ", strip_agency_context(text)))
