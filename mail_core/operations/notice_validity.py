"""notice_validity — MAIL-P1A-01(TASK-031): 로그인/오류/CAPTCHA 등 정상 공고가 아닌
입력을 excluded(비즈니스 규칙 제외)와 분리해 quarantine/parse_error로 보낸다.

"제외"(EXCLUSION_RULES, evaluate_notice()의 exclude_reason_codes)는 실제 공고이지만
우리 그룹 기준에 안 맞는 경우다. 이 모듈이 다루는 quarantine/parse_error는 애초에
정상적으로 수집된 "공고"가 아닌 입력이며, 반드시 그 둘과 분리해서 기록한다
(FORBIDDEN: 수집실패를 정상 제외로 기록하지 않는다).

recall 최우선 정책 준수를 위해 의도적으로 보수적이다 — 상세보강 실패
(detail_extraction.status)는 여기서 다루지 않는다. 목록 페이지 데이터만으로도
정상 판정이 가능한 공고가 대부분이라, 상세보강 실패를 이유로 후보에서 빼면
정상 공고 누락(recall 저하)으로 이어질 수 있다(기존 동작 유지: 상세보강 실패
시에도 목록 데이터로 계속 진행). 이 모듈은 "HTTP 200으로 응답은 왔지만 내용이
로그인/오류/캡차 화면"인 경우와 "제목·링크가 아예 없는" 경우만 다룬다.
"""
from __future__ import annotations

VALID = "valid"
QUARANTINE = "quarantine"
PARSE_ERROR = "parse_error"

REASON_ERROR_PAGE_SIGNAL = "ERROR_PAGE_SIGNAL"
REASON_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"

# monitor.py 의 _COVERAGE_ERROR_CONTENT_HINTS(소스 전체 집계용, coverage_alert 리포트)와
# 같은 신호를 공고 1건 단위로도 적용한다. 두 상수를 하나로 합치는 리팩터는 하지 않는다
# (이미 테스트가 걸린 집계 경로를 건드리는 리스크 대비 이득이 작음) — 신호 목록만 그대로
# 복제해 둔다. 신호를 추가/변경할 때는 두 곳을 함께 갱신할 것.
ERROR_PAGE_HINTS = (
    "captcha", "access denied", "forbidden", "login required", "log in required",
    "service unavailable", "under maintenance", "temporarily unavailable",
    "로그인 후", "로그인이 필요", "자동입력방지", "보안문자",
    "접근 권한", "접근이 제한", "서비스 점검", "시스템 점검",
    "오류가 발생", "페이지를 찾을 수 없",
)


def classify_notice_validity(item: dict) -> tuple[str, str, str]:
    """공고 1건의 유효성을 판정한다.

    반환: (validity, reason_code, evidence). valid면 reason_code·evidence는 빈 문자열.
    evidence는 판정 근거가 된 짧은 힌트 문구만 담고 원문 전체는 절대 포함하지 않는다.
    """
    title = str(item.get("title") or "").strip()
    link = str(item.get("link") or "").strip()

    if not title and not link:
        return PARSE_ERROR, REASON_MISSING_REQUIRED_FIELD, ""

    description = str(item.get("description") or "")
    text = f"{title} {description}".casefold()
    hit = next((h for h in ERROR_PAGE_HINTS if h in text), "")
    if hit:
        return QUARANTINE, REASON_ERROR_PAGE_SIGNAL, hit

    return VALID, "", ""


def quarantine_invalid_notices(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """공고 목록을 (유효, quarantine/parse_error) 두 목록으로 나눈다.

    분리된 항목에는 validity_status/validity_reason_code/validity_evidence 필드를
    부착해 반환한다(진단용, 원문 전체 아님 — 발송되지 않으므로 개인정보 우려 없음).
    유효 목록은 기존 항목 그대로(필드 부착 없음) 반환해 하위 파이프라인에 영향이
    없도록 한다.
    """
    valid: list[dict] = []
    quarantined: list[dict] = []
    for item in items:
        validity, reason, evidence = classify_notice_validity(item)
        if validity == VALID:
            valid.append(item)
        else:
            quarantined.append({
                **item,
                "validity_status": validity,
                "validity_reason_code": reason,
                "validity_evidence": evidence,
            })
    return valid, quarantined
