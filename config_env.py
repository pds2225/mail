"""config_env — 설정 파일(groups.json·companies.json 등)을 환경변수로 주입 가능하게 하는 로더.

목적: 수신자 이메일 등 **PII 가 든 설정을 레포에 커밋하지 않고**, 배포 환경
(GitHub Actions·Vercel·Streamlit Cloud)의 시크릿/환경변수로 주입한다.
환경변수가 없거나 파싱에 실패하면 기존 파일로 폴백하여 로컬/기존 동작을 그대로
유지한다(하위호환).

환경변수 값 형식 (둘 다 지원 — .env.example 의 GOOGLE_SERVICE_ACCOUNT_JSON 관례와 동일):
  - 인라인 JSON: 공백 제거 후 '[' 또는 '{' 로 시작하면 그 문자열을 직접 파싱.
  - 파일 경로:  그 외에는 파일 경로로 보고 해당 파일을 읽어 파싱.

self-contained: 표준 라이브러리만 사용(os·json·pathlib) — company_match 의
self-contained 규칙(네트워크/필수 환경변수 없이 단위 테스트 통과)을 유지한다.

보안: 환경변수의 원문(수신자 이메일 등 PII)은 절대 로그에 남기지 않는다.
파싱 실패 시에도 on_error 콜백에는 예외 객체만 전달한다(원문 미노출).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

__all__ = ["load_config"]


def _parse_env_value(value: str) -> Any:
    """환경변수 문자열을 파싱.

    - 공백 제거 후 '[' 또는 '{' 로 시작하면 인라인 JSON 으로 직접 파싱.
    - 그 외에는 파일 경로로 간주해 해당 파일을 읽어 파싱.

    파싱 불가 시 예외(json.JSONDecodeError / OSError)를 올린다 — 호출부(load_config)가
    파일 폴백 여부를 결정한다.
    """
    stripped = value.strip()
    if stripped[:1] in ("[", "{"):
        return json.loads(stripped)
    return json.loads(Path(stripped).read_text(encoding="utf-8"))


def load_config(
    env_var: str,
    file_path: str | Path,
    default: Any = None,
    *,
    on_error: Callable[[Exception], None] | None = None,
) -> Any:
    """env_var(인라인 JSON 또는 파일경로) 우선 → 실패/미설정 시 file_path → 없으면 default.

    반환값은 **파싱된 JSON 값 그대로**(list/dict 등)이다. active 필터·정규화 등은
    호출부가 각자 적용한다(load_groups/load_companies 의 기존 로직 재사용).

    동작:
      1. env_var 가 설정(비어있지 않음)되고 파싱에 성공 → 그 값 반환(파일 무시).
      2. env_var 파싱 실패 → on_error(예외) 호출 후 파일 폴백으로 진행.
      3. env_var 미설정 → 곧장 파일 폴백.
      4. 파일이 없거나 파일 파싱 실패 → on_error(예외, 파일 실패 시) 후 default 반환.
    """
    raw = os.environ.get(env_var, "").strip()
    if raw:
        try:
            return _parse_env_value(raw)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            if on_error is not None:
                on_error(e)
            # 파일 폴백으로 진행

    p = Path(file_path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        if on_error is not None:
            on_error(e)
        return default
