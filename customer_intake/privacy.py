"""개인정보·사업자번호 로그 마스킹."""

from __future__ import annotations

import re


def mask_business_number(value: str) -> str:
    """사업자등록번호: 123-45-67890 → 123-**-***90."""
    if not value or value == "확인필요":
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) != 10:
        return "***"
    return f"{digits[:3]}-**-***{digits[-2:]}"


def mask_person_name(value: str) -> str:
    """대표자명: 홍길동 → 홍*동, 외자·2자 처리."""
    if not value or value == "확인필요":
        return value
    name = value.strip()
    if len(name) <= 1:
        return "*"
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def mask_company_name(value: str) -> str:
    """고객사명: 앞 2자만 노출."""
    if not value or value == "확인필요":
        return value
    name = value.strip()
    if len(name) <= 2:
        return name[0] + "*" * max(0, len(name) - 1)
    return name[:2] + "*" * (len(name) - 2)


def mask_corp_number(value: str) -> str:
    """법인등록번호: 110111-1234567 → 110111-*******."""
    if not value or value == "확인필요":
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) != 13:
        return "***"
    return f"{digits[:6]}-*******"


def mask_address(value: str) -> str:
    """주소: 시·도·구군까지만."""
    if not value or value == "확인필요":
        return value
    parts = value.split()
    if len(parts) <= 2:
        return parts[0] + " ***" if parts else "***"
    return " ".join(parts[:2]) + " ***"
