# 지역 판정 resolve_region

`evaluate_notice`가 쓰는 지역 적격 **단일 진입점**.

## API

```python
uses_incheon_region_engine(group) -> bool
resolve_region(item, group=None) -> dict  # region_status, district_status, ...
```

## 분기

| 조건 | 엔진 | 이유 |
|------|------|------|
| `group` 없음 또는 `applicant_region_city == 인천광역시` | `classify_region` | 남동구 기준 구 단위 배타 |
| 그 외 시·도 | `classify_region_for_group` | 임의 광역/시·군 |

## 타 구 전용 차단

신청자 구가 있을 때, 같은 광역(예: 인천 `INCHEON_DISTRICTS`)의 **다른 구만** 본문에 있고 우리 구가 없으면 `not_eligible`.

예: 남동구 신청자 ← 「인천 부평구 소재 기업 지원」 → 차단.

`classify_region_for_group`에도 `_metro_peer_districts`로 동일 정책 이식됨.

## region_ok

- 인천 엔진: `region_match(item, req_regions, region_info=...)` (required_conditions.regions 결합)
- 타광역: `region_status == "eligible"`

## 관련

- [[filter-pipeline]]
- `tests/test_filter_selector_fixes.py` — `test_resolve_region_*`, `test_for_group_peer_district_*`
