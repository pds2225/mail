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
_REGION_LIST = rf"(?:{_REGION})(?:\s*[·ㆍ,/및]+\s*(?:{_REGION}))*"
_NOT_NEGATED = r"(?!\s*(?:하지|되지|안\s|아니|아님|대상(?:이)?\s*아))"
_EXCLUSION_SUBJECT = (
    rf"(?<![가-힣])(?P<regions>{_REGION_LIST})"
    r"\s*(?:지역\s*)?(?:소재\s*)?(?:(?:중소)?기업\s*)?(?:은|는|을|를)?\s*"
    r"(?:지원\s*대상에서\s*)?"
)
_EXCLUSION = re.compile(_EXCLUSION_SUBJECT + rf"제외{_NOT_NEGATED}(?:한)?")
_NEGATED_EXCLUSION = re.compile(
    _EXCLUSION_SUBJECT + r"제외\s*(?:(?:하지|되지)\s*않(?:음|는|습니다|는다)?|안\s*함|대상(?:이)?\s*아님)"
)
_EXCLUDED_LABEL = re.compile(rf"제외\s*지역\s*[:：]\s*(?P<regions>{_REGION_LIST})")
_ISLAND_EXCLUSION = re.compile(rf"도서\s*(?:지역\s*)?(?:을|를|은|는)?\s*제외{_NOT_NEGATED}(?:한)?")
_TARGET_LABEL = r"(?:지원\s*대상|신청\s*(?:대상|자격)|참여\s*대상|지원\s*지역)\s*[:：]"
_CONTACT = re.compile(
    r"(?:기관\s*(?:주소|소재지)|주소\s*[:：]|(?:^|[\n;/])\s*주소(?=\s)|소재지\s*[:：]|문의(?:처)?|연락처|담당(?:부서|자)|"
    r"주관\s*기관|공고\s*기관|운영\s*기관|접수처|사무국|전화|이메일|☎|tel|fax)"
    rf"\s*[:：]?[^\n;]*?(?=(?:{_TARGET_LABEL})|[\n;]|$)", re.IGNORECASE,
)
_AGENCY = re.compile(
    rf"(?:{_REGION})\s*(?:시청|도청|테크노파크|경제진흥원|산업진흥원|창조경제혁신센터)"
)
_REGION_BASIS = re.compile(
    r"(?P<basis>본사|사업장|공장)\s*(?:주소|소재지|소재|기준|위치)"
    r"|(?:소재지|소재)\s*(?:가\s*)?(?P<reverse>본사|사업장|공장)"
)
_RELOCATION_REQUIRED = re.compile(
    r"(?:이전\s*(?:예정|조건|완료|후)|이전할\s*예정|이전하여\s*신청|이전\s*시\s*지원)"
)
_PARTICIPANT_SPAN = re.compile(r"(?:참여\s*기관|참여기관|참여\s*기업|공동수행기관)[^.!?;\n]*")


def short_region(value: str) -> str:
    return _ALIASES.get(value, value)


def agency_region_hints(text: str) -> list[str]:
    """기관 메타데이터의 약한 단서. 신청자 부적격 판정에는 사용하지 않는다."""
    return sorted({short_region(token) for token in _REGION_MATCHER.findall(text or "")})


def strip_agency_context(text: str) -> str:
    """줄바꿈·지원대상 라벨을 보존해 같은 줄의 신청자격까지 지우지 않는다."""
    source = text or ""
    target = re.search(_TARGET_LABEL, source)
    if target:
        # 지원대상 라벨 뒤에서도 담당부서·문의처는 제거하되, '주관기관 소재지 기준'은
        # 신청자격 문맥일 수 있으므로 연락처 제거 패턴에 잡히지 않게 잠시 보호한다.
        prefix = _CONTACT.sub(" ", source[:target.start()])
        suffix = source[target.start():]
        lead_org = "__LEAD_APPLICANT_ORG__"
        suffix = re.sub(r"주관\s*기관(?=\s*(?:소재|기준|은|이|의|으로))", lead_org, suffix)
        suffix = _CONTACT.sub(" ", suffix).replace(lead_org, "주관기관")
        source = prefix + suffix
    else:
        source = _CONTACT.sub(" ", source)
    return _AGENCY.sub(" ", source)


def notice_region_metadata(text: str) -> dict:
    """공고의 지역 판정 기준과 조건을 지원대상 문구에서 추출한다."""
    source = text or ""
    basis_match = _REGION_BASIS.search(source)
    basis_token = (basis_match.group("basis") or basis_match.group("reverse")) if basis_match else ""
    basis = {"본사": "headquarters", "사업장": "business_site", "공장": "factory"}.get(
        basis_token, "unspecified"
    )
    participant_regions = {
        _ALIASES.get(token, token)
        for span in _PARTICIPANT_SPAN.findall(source)
        for token in _REGION_MATCHER.findall(span)
    }
    return {
        "region_basis": basis,
        "relocation_required": bool(_RELOCATION_REQUIRED.search(source)),
        "participating_regions": sorted(participant_regions),
    }


def region_exclusions(text: str) -> dict:
    text = strip_agency_context(text)
    excluded = {
        _ALIASES.get(token, token)
        for pattern in (_EXCLUSION, _EXCLUDED_LABEL)
        for match in pattern.finditer(text)
        for token in _REGION_MATCHER.findall(match.group("regions"))
    }
    return {"excluded_regions": sorted(excluded),
            "island_excluded": bool(_ISLAND_EXCLUSION.search(text))}


def applicant_region_text(text: str) -> str:
    """제외된 지역명도 긍정적인 지역 근거에서 제거한다."""
    # 공동사업에서는 참여기관의 소재지가 신청자격 지역처럼 누출되지 않도록 한다.
    text = _PARTICIPANT_SPAN.sub(" ", text or "")
    text = _NEGATED_EXCLUSION.sub(" ", strip_agency_context(text))
    return _ISLAND_EXCLUSION.sub(" ", _EXCLUSION.sub(" ", _EXCLUDED_LABEL.sub(" ", text)))
