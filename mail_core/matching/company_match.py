"""company_match — 기업 맞춤 정확 매칭 레이어.

목적: 기존 monitor.py(그룹 단위 키워드 필터)를 건드리지 않고, **기업(회사)별 프로필**에
정확히 적합한 공고만 선별·랭킹하여 발송 초안을 만든다.

핵심 차이 (기업 맞춤):
- 그룹이 아니라 개별 기업의 프로필(지역/산업/관심사/공장보유/수출지향/지원유형 선호)에 맞춰 점수화.
- 동일 공고라도 기업 프로필이 다르면 다른 결과를 받는다.
- evaluate_notice(monitor.py) 판정 결과가 item에 있으면 하드 제외 규칙을 재사용한다(있을 때만).

안전 규칙 (RULES.md):
- 이 모듈은 smtplib 을 import/호출하지 않는다 — 실제 발송 경로 없음. 초안(draft)만 생성.
- 초안/로그의 수신자 이메일은 마스킹한다.
- Secret/API Key 를 출력하지 않는다.

self-contained: monitor 를 top-level import 하지 않으므로 네트워크/환경변수 없이 단위 테스트가 통과한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mail_core.paths import CONFIG_DIR
from mail_core.security import private_config

COMPANIES_PATH = CONFIG_DIR / "companies.json"

# 전국 17개 광역 지자체 (다른 지역 한정 공고 감지용)
KNOWN_REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

# 공고가 공장/제조시설 보유를 요구함을 나타내는 표현
FACTORY_REQUIRED_TERMS = [
    "공장등록증", "공장 보유", "공장보유", "제조시설", "제조업 영위",
    "공장 임차", "공장임차", "임대공장", "입주기업",
]
# 수출/해외 지향 신호
EXPORT_TERMS = [
    "수출", "해외", "글로벌", "바이어", "무역", "해외전시", "해외마케팅",
    "해외진출", "박람회", "전시회", "베트남", "동남아",
]

# 점수에서 하드 제외로 간주할 evaluate_notice exclude_reason_codes
HARD_EXCLUDE_CODES = {
    "REGION_NOT_ELIGIBLE",
    "DISTRICT_NOT_ELIGIBLE",
    "CLOSED_DEADLINE",
}

DEFAULT_WEIGHTS: dict[str, int] = {
    "industry_match": 12,      # 산업 키워드 1히트당
    "interest_match": 8,       # 관심 키워드 1히트당
    "region_district": 30,     # 기업 소재 구(區) 일치
    "region_city": 22,         # 기업 소재 시(市) 일치
    "region_nationwide": 14,   # 전국 대상
    "factory_bonus": 10,       # 공장보유 기업 + 공장조건 공고
    "export_bonus": 10,        # 수출지향 기업 + 수출 공고
    "support_type_bonus": 8,   # 선호 지원유형 일치
    "exclude_penalty": -60,    # 제외 키워드 1히트당
    "region_mismatch_penalty": -40,  # 명백히 다른 지역 한정
}
DEFAULT_THRESHOLD = 60

TEST_RECIPIENT = "test-recipient@example.test"


# ── 기업 프로필 로딩 ──────────────────────────────────────────────────────────

def _normalize_company(raw: dict[str, Any]) -> dict[str, Any]:
    """누락 필드를 안전한 기본값으로 보정한 기업 프로필을 반환."""
    region = raw.get("region") or {}
    if not isinstance(region, dict):
        region = {}
    return {
        "id": str(raw.get("id") or raw.get("email") or "company"),
        "name": str(raw.get("name") or "이름없는 기업"),
        "email": str(raw.get("email") or ""),
        "tenant_id": private_config.normalize_tenant_id(raw.get("tenant_id")),
        "active": bool(raw.get("active", True)),
        "region": {
            "city": str(region.get("city") or ""),
            "district": str(region.get("district") or ""),
        },
        "industry_keywords": list(raw.get("industry_keywords") or []),
        "interest_keywords": list(raw.get("interest_keywords") or []),
        "exclude_keywords": list(raw.get("exclude_keywords") or []),
        "has_factory": bool(raw.get("has_factory", False)),
        "export_focus": bool(raw.get("export_focus", False)),
        "support_type_prefs": list(raw.get("support_type_prefs") or []),
        "match_threshold": int(raw.get("match_threshold", DEFAULT_THRESHOLD)),
        "weights": dict(raw.get("weights") or {}),
    }


def load_companies(path: str | Path | None = None) -> list[dict[str, Any]]:
    """companies.json 에서 active=true 기업 프로필을 로드. 파일 없으면 빈 리스트(예외 없음)."""
    p = Path(path) if path else COMPANIES_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if path is None:
        raw = private_config.merge_companies(raw)
    if isinstance(raw, dict):
        raw = raw.get("companies", [])
    if not isinstance(raw, list):
        return []
    companies = [_normalize_company(c) for c in raw if isinstance(c, dict)]
    return [c for c in companies if c["active"]]


# ── 텍스트 유틸 ───────────────────────────────────────────────────────────────

def _haystack(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title", "")),
        str(item.get("summary", "")),
        str(item.get("description", "")),
        str(item.get("content", "")),
        str(item.get("category", "")),
        str(item.get("raw_text", "")),
    ]
    return " ".join(parts)


_ASCII_KW_RE = re.compile(r"^[a-zA-Z0-9.+#&-]+$")


def _count_hits(text_lower: str, keywords: list[str]) -> tuple[int, list[str]]:
    # 영어/숫자 약어(AI·SaaS·DX·ERP)는 단어경계로 매칭(email·training 등 substring 오매칭 차단),
    # 한글 등 키워드는 substring 유지. scoring.py 와 동일한 영어약어 경계 기준.
    hits: list[str] = []
    for kw in keywords:
        if not kw:
            continue
        k = kw.lower()
        if _ASCII_KW_RE.match(kw):
            if re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", text_lower):
                hits.append(kw)
        elif k in text_lower:
            hits.append(kw)
    return len(hits), hits


# 수도권 family — '수도권' 공고는 이 광역 기업 모두에게 적격
_METRO_FAMILY = {"서울", "인천", "경기", "수도권"}

# 권역(클러스터) → 소속 광역. 단일 정본 region_clusters 모듈 공유(monitor 와 drift 방지).
from .region_clusters import REGION_CLUSTER as _REGION_CLUSTER


def _region_cluster_verdict(atext: str, city: str) -> tuple[bool, bool]:
    """공고의 '○○권' 권역 한정 신호로 (적격, 차단) 판정.

    - '○○권' + 우리 시가 그 권역 멤버 → 적격 / 멤버 아님 → 차단
    - '비○○권'(예: 비수도권) + 우리 시가 그 권역 멤버 → 차단 / 아니면 적격
    매핑 없는 모호 광역은 건드리지 않는다(누출보다 누락이 더 큰 위반 → 차단을 좁게).
    """
    if not city:
        return False, False
    elig = blk = False
    for kwon, members in _REGION_CLUSTER.items():
        if ("비" + kwon) in atext:
            if city in members:
                blk = True
            else:
                elig = True
        elif kwon in atext:
            if city in members:
                elig = True
            else:
                blk = True
    return elig, blk


def _region_signals(item: dict[str, Any]):
    """monitor 의 검증된 '지원대상 지역' 판정을 재사용한다(지연 import — self-contained 유지).

    반환 (restricted, regions, nationwide, atext) 또는 None(monitor 사용 불가 → 호출측 fallback).
    - restricted: '{광역} 소재 기업만' 같은 신청자격 강신호 광역 약칭 집합(보일러플레이트/개최지 제거됨)
    - regions:    지원대상 본문에서 감지된 광역 약칭 집합(개최지 언급 포함, 보조)
    - nationwide: 전국 대상 여부
    - atext:      주관기관(author) 제외한 지원대상 판정용 텍스트
    monitor 는 top-level import 하지 않으므로(단위테스트 self-contained), 함수 내부에서만 import.
    """
    try:
        from monitor import (
            _applicant_restricted_regions as _arr,
            _applicant_target_text as _att,
            _resolve_applicant_region_scope as _scope,
            _short_region as _sr,
        )
    except Exception:
        return None
    try:
        atext = _att(item)
        restricted = {_sr(r) for r in _arr(atext)}
        sc = _scope(item)
        regions = {_sr(r) for r in (sc.get("regions") or [])}
        nationwide = bool(sc.get("nationwide"))
        return restricted, regions, nationwide, atext
    except Exception:
        return None


# ── 기업별 점수 계산 ──────────────────────────────────────────────────────────

def compute_match_score(item: dict[str, Any], company: dict[str, Any]) -> dict[str, Any]:
    """기업 프로필 기준 공고 적합도 점수.

    Returns {'score': int(0~100), 'breakdown': dict, 'reasons': list[str], 'mismatches': list[str]}
    """
    company = _normalize_company(company)  # 멱등 — 입력이 raw/정규화 어느 쪽이든 안전
    weights = {**DEFAULT_WEIGHTS, **(company.get("weights") or {})}
    text = _haystack(item)
    text_lower = text.lower()

    reasons: list[str] = []
    mismatches: list[str] = []
    score = 0

    # 산업 / 관심 키워드
    industry_hits, industry_kw = _count_hits(text_lower, company.get("industry_keywords") or [])
    interest_hits, interest_kw = _count_hits(text_lower, company.get("interest_keywords") or [])
    score += industry_hits * weights["industry_match"]
    score += interest_hits * weights["interest_match"]
    if industry_hits:
        reasons.append(f"산업적합 {industry_hits}건({', '.join(industry_kw[:3])})")
    if interest_hits:
        reasons.append(f"관심사 {interest_hits}건({', '.join(interest_kw[:3])})")

    # 지역 — monitor 의 검증된 '지원대상 지역' 판정을 재사용(보일러플레이트 제거·단어경계·
    # 신청자격 강신호·수도권 family·region_field). own 은 정확히 우리 시(市)로만 본다.
    # monitor 불가 시 자족 단어경계 fallback.
    region = company.get("region") or {}
    city = (region.get("city") or "").strip()
    district = (region.get("district") or "").strip()
    region_score = 0
    region_status = "unknown"
    own = {city} if city else set()

    sig = _region_signals(item)
    if sig is not None:
        restricted, regions, nationwide, atext = sig
        dist_in = bool(district) and bool(
            re.search(rf"(?<![가-힣]){re.escape(district)}(?![가-힣])", atext))
        own_restricted = bool(restricted & own)
        other_restricted = sorted(restricted - own)
        own_region_in = bool(regions & own)
        other_regions = sorted(regions - own)
        # 권역(수도권·충청권·호남권·경상권·강원권·제주권) 한정 신호 — own 이 그 권역 멤버면 적격, 아니면 차단
        kwon_elig, kwon_blk = _region_cluster_verdict(atext, city)

        if restricted and not own_restricted:
            # 신청 자격이 타지역으로만 한정됨(강신호) — 운영사/개최지의 우리 시 언급은 무시
            region_score = weights["region_mismatch_penalty"]
            region_status = "other_only"
            mismatches.append(f"타지역 한정({', '.join(other_restricted[:3])})")
        elif own_restricted or own_region_in or dist_in or kwon_elig:
            # own 적격 신호(소재 일치 / 권역 멤버) — 권역 차단보다 우선(recall 보존)
            if dist_in:
                region_score = weights["region_district"]
                region_status = "district"
                reasons.append(f"소재 구 일치({district})")
            else:
                region_score = weights["region_city"]
                region_status = "city"
                reasons.append(
                    f"소재 시 일치({city})" if (own_restricted or own_region_in) else "권역 대상")
        elif kwon_blk:
            # 권역 한정인데 우리 지역이 그 권역에 속하지 않음 → 차단
            region_score = weights["region_mismatch_penalty"]
            region_status = "other_only"
            mismatches.append("권역 한정(우리 지역 제외)")
        elif other_regions:
            # 우리 지역 단서 없이 타지역만 언급(개최지 등)
            if nationwide:
                # '전국' + 타지역 동시 → 모호: 전국 보너스 없이 약하게 감점 + 확인 필요로 surface
                region_score = weights["region_mismatch_penalty"] // 2
                region_status = "nationwide_other_region"
                mismatches.append(
                    f"전국 표기 있으나 타지역({', '.join(other_regions[:3])}) 명시 — 확인 필요")
            else:
                region_score = weights["region_mismatch_penalty"]
                region_status = "other_only"
                mismatches.append(f"타지역 한정({', '.join(other_regions[:3])})")
        elif nationwide:
            region_score = weights["region_nationwide"]
            region_status = "nationwide"
            reasons.append("전국 대상")
    else:
        # ── fallback: monitor 사용 불가 시 자족 단어경계 판정 ──
        company_region_mentioned = bool((city and city in text) or (district and district in text))
        other_regions = [r for r in KNOWN_REGIONS if r and r in text and r != city]
        has_nationwide = "전국" in text
        if district and district in text:
            region_score = weights["region_district"]
            region_status = "district"
            reasons.append(f"소재 구 일치({district})")
        elif city and city in text:
            region_score = weights["region_city"]
            region_status = "city"
            reasons.append(f"소재 시 일치({city})")
        elif other_regions and not company_region_mentioned:
            if has_nationwide:
                region_score = weights["region_mismatch_penalty"] // 2
                region_status = "nationwide_other_region"
                mismatches.append(
                    f"전국 표기 있으나 타지역({', '.join(other_regions[:3])}) 명시 — 확인 필요")
            else:
                region_score = weights["region_mismatch_penalty"]
                region_status = "other_only"
                mismatches.append(f"타지역 한정({', '.join(other_regions[:3])})")
        elif has_nationwide:
            region_score = weights["region_nationwide"]
            region_status = "nationwide"
            reasons.append("전국 대상")
    score += region_score

    # 공장 조건
    factory_required = any(t in text for t in FACTORY_REQUIRED_TERMS)
    if factory_required:
        if company.get("has_factory"):
            score += weights["factory_bonus"]
            reasons.append("공장보유 조건 충족")
        else:
            mismatches.append("공장보유 조건 미충족")
            score += weights["region_mismatch_penalty"] // 2

    # 수출 지향
    export_signal = any(t in text for t in EXPORT_TERMS)
    if company.get("export_focus") and export_signal:
        score += weights["export_bonus"]
        reasons.append("수출지향 적합")

    # 지원유형 선호 (item._types 또는 support_types 필드)
    item_types = item.get("_types") or item.get("support_types") or []
    if isinstance(item_types, str):
        item_types = [item_types]
    prefs = company.get("support_type_prefs") or []
    if prefs and item_types and set(prefs) & set(item_types):
        score += weights["support_type_bonus"]
        reasons.append("선호 지원유형 일치")

    # 제외 키워드
    exclude_hits, exclude_kw = _count_hits(text_lower, company.get("exclude_keywords") or [])
    if exclude_hits:
        score += exclude_hits * weights["exclude_penalty"]
        mismatches.append(f"제외 키워드({', '.join(exclude_kw[:3])})")

    score = max(0, min(100, score))

    return {
        "score": int(score),
        "breakdown": {
            "industry_hits": industry_hits,
            "interest_hits": interest_hits,
            "region_status": region_status,
            "region_score": region_score,
            "factory_required": factory_required,
            "export_signal": export_signal,
            "exclude_hits": exclude_hits,
        },
        "reasons": reasons,
        "mismatches": mismatches,
    }


# ── 하드 제외 (evaluate_notice 재사용) ────────────────────────────────────────

def _hard_excluded(item: dict[str, Any]) -> str | None:
    """item 에 monitor.evaluate_notice 결과가 있으면 그 판정으로 하드 제외 사유를 반환.

    evaluate_notice 미적용 item(필드 없음)은 None(점수 판정에 위임).
    """
    if item.get("deadline_status") == "closed":
        return "마감 경과"
    codes = item.get("exclude_reason_codes")
    if codes and (set(codes) & HARD_EXCLUDE_CODES):
        hit = sorted(set(codes) & HARD_EXCLUDE_CODES)
        return f"하드제외({', '.join(hit)})"
    # evaluate_notice 가 명시적으로 is_relevant=False 로 표시했고 review 대상도 아니면 제외
    if item.get("is_relevant") is False and item.get("review_needed") is False:
        return "evaluate_notice 부적합"
    return None


# ── 기업별 매칭 ───────────────────────────────────────────────────────────────

def match_for_company(items: list[dict[str, Any]], company: dict[str, Any]) -> dict[str, Any]:
    """기업 프로필 기준으로 공고를 matched / rejected 로 분류하고 score 내림차순 정렬.

    Returns {'matched': [...], 'rejected': [...], 'audit': [...]}
    """
    company = _normalize_company(company)  # 멱등
    threshold = int(company.get("match_threshold", DEFAULT_THRESHOLD))

    matched: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    for item in items:
        record: dict[str, Any] = {
            "title": str(item.get("title", ""))[:90],
        }
        hard = _hard_excluded(item)
        if hard:
            record["decision"] = "rejected_hard"
            record["score"] = 0
            record["reason"] = hard
            audit.append(record)
            rejected.append({**item, "_match_score": 0, "_match_reason": hard})
            continue

        s = compute_match_score(item, company)
        score = s["score"]
        enriched = {
            **item,
            "_match_score": score,
            "_match_reasons": s["reasons"],
            "_match_mismatches": s["mismatches"],
            "_match_breakdown": s["breakdown"],
        }
        record.update({
            "score": score,
            "reasons": s["reasons"],
            "mismatches": s["mismatches"],
        })
        if score >= threshold:
            record["decision"] = "matched"
            matched.append(enriched)
        else:
            record["decision"] = "rejected_score"
            rejected.append(enriched)
        audit.append(record)

    matched.sort(key=lambda it: -int(it.get("_match_score", 0)))
    return {"matched": matched, "rejected": rejected, "audit": audit}


# ── 안전 / 마스킹 ─────────────────────────────────────────────────────────────

def mask_email(email: str) -> str:
    local, sep, domain = (email or "").partition("@")
    if not sep:
        return "***"
    if len(local) <= 2:
        masked = local[:1] + "*"
    else:
        masked = local[:2] + "*" * (len(local) - 2)
    return f"{masked}@{domain}"


def assert_test_recipient_only(companies: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """테스트 단계 안전장치: test-recipient@example.test 외 수신자가 있으면 (False, 위반목록).

    실제 발송 경로가 없으므로 예외를 던지지 않고 결과만 반환(호출 측에서 차단/경고).
    """
    violations = [
        c.get("email", "")
        for c in companies
        if c.get("email") and c.get("email") != TEST_RECIPIENT
    ]
    return (len(violations) == 0, violations)


# ── 발송 초안 (draft only, 발송 금지) ─────────────────────────────────────────

SAFETY_BANNER = (
    "================================================================\n"
    "⚠️  발송 금지 — 이 파일은 기업 맞춤 공고 초안입니다. 검수 후 별도 발송.\n"
    "================================================================"
)


def build_company_digest(company: dict[str, Any], matched: list[dict[str, Any]]) -> str:
    """기업 맞춤 공고 발송 초안 텍스트. 실제 발송 없음. 수신자 이메일 마스킹."""
    company = _normalize_company(company)  # 멱등
    region = company.get("region") or {}
    region_label = " ".join(x for x in [region.get("city"), region.get("district")] if x) or "전국"

    lines: list[str] = [
        SAFETY_BANNER,
        "",
        f"기업: {company.get('name')}  (수신: {mask_email(company.get('email', ''))})",
        f"소재지: {region_label}",
        f"맞춤 공고: {len(matched)}건",
        "",
        "안녕하세요, 귀사 프로필에 맞춰 선별한 지원사업 공고를 안내드립니다.",
        "",
    ]
    if matched:
        for i, it in enumerate(matched, 1):
            reasons = ", ".join(it.get("_match_reasons", [])) or "키워드 적합"
            lines.extend([
                f"[{i}] {it.get('title') or '(제목없음)'}  (적합도 {it.get('_match_score', 0)})",
                f"  기관: {it.get('author') or it.get('agency') or '미기재'}",
                f"  마감: {it.get('deadline') or it.get('end_date') or '미기재'}",
                f"  매칭 사유: {reasons}",
                f"  링크: {it.get('link') or it.get('url') or '미기재'}",
                "",
            ])
    else:
        lines.extend(["(귀사 프로필에 맞는 신규 공고가 없습니다.)", ""])

    lines.extend([
        "────────────────────────────────────────────────",
        "본 메일은 자동 선별 초안이며, 신청 전 공고 원문을 확인하세요.",
        SAFETY_BANNER,
    ])
    return "\n".join(lines)
