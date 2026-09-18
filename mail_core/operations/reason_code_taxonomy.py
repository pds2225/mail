"""reason_code_taxonomy — MAIL-P0D-02: evaluate_notice() reason_code 표준화.

evaluate_notice()가 방출하는 모든 reason_code를 사람이 읽을 수 있는 설명과 함께
한 곳에 등록해, "자동판정 reason_code 100%"(코드에서 실제 쓰이는 모든 코드가
이 목록에 등록돼 있는가)를 기계적으로 검증할 수 있게 한다.

이 모듈은 판정 로직을 바꾸지 않는다 — 읽기 전용 레지스트리·검증 헬퍼만 제공한다.
"""
from __future__ import annotations

# code -> 사람이 읽는 한 줄 설명. monitor.py evaluate_notice()의
# reason_codes.append("...")/_add_reason("...") 호출과 1:1로 맞춘다.
REASON_CODE_TAXONOMY: dict[str, str] = {
    # EXCLUSION_RULES 테이블 기반 제외(공고 유형별 하드 제외 규칙)
    "GUIDELINE_OR_MANUAL": "지침·매뉴얼·부정수급 안내 등 공고가 아닌 문서",
    "SUPPLIER_ONLY": "수행기관·공급기업 모집(신청기업 대상 아님)",
    "SELECTED_COMPANY_ONLY": "이미 선정된 기업 대상 후속 절차(신규 신청 아님)",
    "EDUCATION_ONLY": "교육·교육생 모집 등 교육 단독 공고",
    "REPORT_JUNK": "잡공고·불필요 리포트성 게시물",
    "ADMIN_NOISE": "행정 고지·공지성 게시물(지원사업 아님)",
    "NOT_GRANT_NOTICE": "제목 앵커 기준 비(非)지원사업 정적 페이지",
    "AMBIGUOUS_NOTICE": "애매한 비지원 공고 — 사람 확인 필요(review)",
    "COMMITTEE_RECRUITMENT": "위원(개인 전문가) 위촉·모집 — 기업 대상 아님",
    "INFO_SESSION": "설명회 단독 모집",
    "LOW_PRIORITY_SERVICE_KEYWORD": "서비스성 키워드 위주(신청형 공고 신호 약함)",
    "INFO_SESSION_REVIEW": "설명회가 모집 본체로 보이나 review로 분리",
    "SMART_FACTORY_INFO_ONLY": "스마트공장 관련 정보성 단독 공고",
    "CLOSED_DEADLINE": "마감 경과",
    "MISSING_APPLICATION_PERIOD": "신청기간 불명 + 모집형 신호 약함",
    "REGION_NOT_ELIGIBLE": "신청 자격 지역 불일치(확실한 타지역)",
    "DISTRICT_NOT_ELIGIBLE": "신청 자격 구(區) 단위 불일치",
    "LOW_CONFIDENCE": "지역/구 판정 신뢰도 낮음(unknown)",
    "ONLY_SPECIFIC_INDUSTRIAL_COMPLEX": "특정 산업단지 입주기업 한정(우리 지역 아님)",
    "REGION_UNKNOWN": "지역 단서 전무 — 확실한 타지역 아님(누락 방지용 표시)",
    "GROUP_EXCLUSION": "그룹별 제외 키워드에 매칭",
    "INDUSTRY_NOT_MATCHED": "그룹 키워드/지원유형 불일치",
    "TENANT_ONLY": "입주공간·사무공간 단독 지원(실질 지원 신호 없음)",
    "CONSULTING_ONLY": "교육·멘토링·컨설팅 단독 지원",
    "INVESTMENT_ONLY": "투자 단독 지원(재정 지원 신호 없음)",
    "NOT_APPLICATION_LIKE": "모집·신청 신호 전혀 없음",
    "BUSINESS_YEARS_NOT_ELIGIBLE": "그룹 신청자 업력 구간과 공고 업력 요건 불일치",
    "AMOUNT_TOO_LOW": "그룹 최소 지원금액 기준 미달(그룹에 enforce_amount_filter=true 일 때만)",
}

# 값이 조건부(예: TENANT_ONLY vs CONSULTING_ONLY 중 하나만)라 같은 실행에서
# 반드시 등장하지는 않는 코드들. 완전성 검사에서 "미사용"으로 오탐하지 않기 위한 주석용
# 목록(검증 로직 자체는 존재 유무만 본다 — 이 집합은 문서화 목적).
CONDITIONAL_CODES = frozenset({
    "CONSULTING_ONLY", "INVESTMENT_ONLY", "TENANT_ONLY",
    "AMOUNT_TOO_LOW", "REGION_UNKNOWN",
})


def known_reason_codes() -> frozenset[str]:
    return frozenset(REASON_CODE_TAXONOMY)


def missing_from_taxonomy(codes_in_use: set[str] | frozenset[str]) -> set[str]:
    """실제 코드에서 쓰이는데 taxonomy에 없는 코드(등록 누락)를 반환한다."""
    return set(codes_in_use) - known_reason_codes()


def describe(code: str) -> str:
    return REASON_CODE_TAXONOMY.get(code, "")
