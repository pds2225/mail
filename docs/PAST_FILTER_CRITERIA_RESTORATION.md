# 과거 공고 필터 기준 복원 조사표

## 조사 범위와 결론

작업 기준점은 `feat/mail-015-history-restore`의 최신 `origin/main`인 `d247d333`이다. 현재 파일만으로 새 정책을 만들지 않기 위해 다음 범위를 대조했다.

- `git log --all`, 관련 파일별 `git log --all -- <path>`, `git blame`
- 로컬·원격 branch 전체와 기존 linked worktree, stash 목록
- `monitor.py`, `mail_core/`, `config/*.json`, `tests/`, `README.md`, `AGENTS.md`, `TASK.md`, `docs/project/{TASKS,DONE,RULES}.md`, `CHANGELOG.md`
- 삭제·이동 이력: 루트 설정/테스트의 `config/`, `mail_core/`, `tests/` 이동과 `test_goyang_precision.py`, `docs/MATCHING_ARCHITECTURE.md`, `var/tmp_unique_tests/*` 삭제 이력

확인 결과, 사용자가 지정한 기본 키워드·예비창업자·지역 세부 제한·공장 조건·특별 우선어·서비스성 공고 제외·날짜/버전/중복 처리는 대부분 현재 코드와 회귀 테스트에 살아 있다. 따라서 근거 없이 기존 정책을 갈아엎지 않고, 사라진 것이 아니라 현재 구조로 대체된 항목은 유지한다. 단독 입주공간은 과거 요구와 현재 주석에 의도는 남아 있으나 독립적인 `TENANT_ONLY` 사유코드는 없으므로, 별도 회귀 검증 후 최소 보강 대상으로 분리한다.

## 과거 기준 복원표

| 기준 | 과거 코드/문서 위치 | 과거 동작 | 현재 구현 | 판정 |
| --- | --- | --- | --- | --- |
| 예비창업자·창업예정자 | `c29d3276`, `cbd5c2fe`, `08a18e7d`, `d03273ab`; `config/groups.json:205-399`; `tests/test_prestartup_ai_digest_regression.py`, `tests/test_scoring.py` | `grp_prestartup_ai`가 예비창업/창업예정과 AI·창업·사업화 결합을 AND/OR로 판정하고 기창업 전용·솔루션 도입은 제외했다. 띄어쓴 `예비 창업`도 보존했다. | `config/groups.json:205-399`, `monitor.py:5586-6000`, `mail_core/matching/scoring.py` 및 관련 테스트에 존재 | 유지 |
| AI 사업화·AI+창업·데이터+창업 | `3942977e`, `a616c17d`, `cbd5c2fe`, `3bda7763`; `config/groups.json:211-348` | 단순 AI 문자열이 아니라 창업·사업화·지원금·실증 등 문맥 결합을 사용하고, AI 사업화지원금 변형을 추가했다. | `config/groups.json:211-348`, `monitor.py:4777-4780`, `tests/test_ai_commercialization_grant_recall.py` | 유지 |
| 베트남 | `3942977e`의 일반 포함어, `08d84dc3`의 Bnco 그룹; `config/groups.json:77-124` | 베트남을 해외·수출·판로 관심 공고의 포함 신호로 사용했다. | `monitor.py:314-340`, Bnco OR 키워드 | 유지 |
| 동남아 | `3942977e`, `08d84dc3`; `config/groups.json:77-124` | 동남아를 해외진출 관심 공고로 포함했다. | `monitor.py:314-340`, Bnco OR 키워드 | 유지 |
| 해외·글로벌 | `3942977e`, `08d84dc3`; `CHANGELOG.md` 2026-05-27 | 해외·글로벌 공고를 포함하고 수출 관련 신호는 지원 유형에도 반영했다. | `monitor.py:314-340`, `monitor.py:150-173`, `config/groups.json:77-124` | 유지 |
| 박람회·전시회 | `3942977e`, `08d84dc3`; `config/groups.json:77-124` | 국내외 박람회·전시회·해외전시회를 관심 공고로 포함했다. | `monitor.py:314-340`, `monitor.py:390-398`, Bnco priority/OR | 유지 |
| 소상공인 | `3942977e`, `08d84dc3`; `README.md` 지원금·바우처 설명 | 소상공인 대상 지원사업을 포함했다. | `monitor.py:314-340`, `config/groups.json:77-124` | 유지 |
| 지원금 | `3942977e`, `f27f93d1`, `3bda7763`; `monitor.py` blame | 지원금·사업화자금·직접지원 신호를 우선 정렬하고 AI 사업화지원금 변형도 회수했다. | `monitor.py:342-363`, `monitor.py:4721-4780`, `tests/test_ai_commercialization_grant_recall.py` | 유지 |
| 혁신바우처 | `3942977e`, `08d84dc3`, `3bda7763`; `config/watchlist.json` `_keywords_보존` | 일반 포함어이면서 priority/watchlist 대상이었다. 단, 자격·지역·마감 게이트는 우회하지 않았다. | `monitor.py:342-363`, `config/groups.json:173-203`, `config/watchlist.json` | 유지 |
| 수출바우처 | `3942977e`, `08d84dc3`, `3bda7763`; `config/watchlist.json` `_keywords_보존` | 수출·해외전시회와 함께 priority/watchlist 대상이었다. | `monitor.py:342-363`, `config/groups.json:77-203`, `tests/test_5field_casematrix.py` | 유지 |
| 공장 | `3942977e`, `a7ec9580`; `tests/test_digest_fp_hardening.py` | 공장 관련 공고는 수집·분류 대상으로 남기고, 명백한 공장 보유 조건은 신청 확인 조건으로 표시했다. | `monitor.py:365-388`, 결과의 `factory_condition`·`required_conditions` | 유지 |
| 스마트·스마트공장 | `3942977e`, `f27f93d1`; `CHANGELOG.md` 2026-05-27 | 스마트공장·제조DX·공정개선은 관심/priority 신호로 사용했다. 정보성 교육·설명회는 별도 제외했다. | `monitor.py:314-388`, `monitor.py:5790-5810`, 관련 5-field 테스트 | 유지 |
| 설명회 제외 | `3942977e`, `f27f93d1`, `fd506102`; `tests/test_p1_context_exclusions.py` | 단순 설명회는 제외하되 모집 본체와 결합된 설명회는 soft/review로 분리했다. | `monitor.py:400`, `monitor.py:459-520`, `monitor.py:5607-5665` | 유지·문맥 판정 |
| 컨설팅지원 제외 | `3942977e`, `4dc50a85`, `fd506102`; `tests/test_filter_accuracy_r2.py`, `tests/test_consultant_notices.py` | 컨설팅 단독 공고는 제외하되 지원금·바우처가 함께 있으면 본문 단어만으로 제외하지 않았다. | `monitor.py:400`, `monitor.py:5790-5810`, `CONSULTING_ONLY` | 유지·문맥 판정 |
| 멘토링 제외 | `3942977e`, `4dc50a85`, `71d61c54`; `tests/test_monitor.py:919-938` | 멘토링 단독은 `CONSULTING_ONLY`, 재정지원+멘토링은 포함했다. 2026-08-08에 전역 단순 제외에서 문맥형 판정으로 바뀌었다. | `monitor.py:150-161`, `monitor.py:5790-5810`, 현재 테스트 | 유지·과거 방식 대체 |
| 공급기업·수행기관 | `3942977e`, `597297eb`, `7329ad17`; `monitor.py` exclusion rules | 공급/수행 역할만 있는 공고는 제외하고 수요기업과 혼합된 경우는 문맥에 따라 보존했다. | `monitor.py:459-520`, `monitor.py:5760-5780`, `extract_target_roles` | 유지 |
| 선정기업 전용·결과발표·채용·지침 | `90ae5ff3`, `3942977e`, `fd506102`; `CHANGELOG.md`, current tests | 결과·지침·매뉴얼·채용·이미 선정된 기업 대상은 발송 후보에서 제외했다. | `monitor.py:440-520`, `monitor.py:5607-5650` | 유지 |
| 전국·수도권·서울·경기·인천 전체 | `37db10d1`, `597297eb`, `8614c1b6`; `tests/test_5field_casematrix.py` | 공고기관 소재지와 실제 신청대상 지역을 분리하고, 전국/수도권은 적격 범위로 처리했다. 예비창업 AI 그룹의 서울 외 수도권 허용은 `c29d3276` 설정에서 확인된다. | `monitor.py:1478-1590`, `monitor.py:5519-5550`, `config/groups.json:205-399` | 유지; 역사적 설정 명시 |
| 인천 특정 구 | `37db10d1`, `597297eb`, `d1822e14`; `tests/test_region_*`, `tests/test_5field_casematrix.py` | 인천 공고라도 신청자가 아닌 특정 구 전용이면 제외하고, 인천 전체는 통과시켰다. | `monitor.py:1478-1590`, `monitor.py:5519-5550`, `REGION_NOT_ELIGIBLE`/`DISTRICT_NOT_ELIGIBLE` | 유지 |
| 본사·사업장·공장 소재 조건 | `37db10d1`, `597297eb`, `a7ec9580`; `mail_core/matching/company_match.py` | 공고기관 지역이 아니라 신청자 대상 문장에서 소재 조건을 추출했다. 본사/사업장/공장 조건은 신청 확인 정보로 남겼다. | `monitor.py:1478-1590`, `mail_core/matching/company_match.py`, `required_conditions` | 유지 |
| 선정 후 이전 가능 | `tests/test_monitor.py:1000-1015`, 관련 지역 이력 | 선정 후 이전 조건은 현재 지역 불일치로 단정하지 않고 조건부 검토로 남겼다. | `monitor.py:1478-1590`, `region_unknown_review` | 유지 |
| 공장 보유 필수 | `3942977e`, `a7ec9580`; `tests/test_digest_fp_hardening.py:152-166`, `tests/test_5field_casematrix.py` | 공고 자체는 수집·분류하고 공장 조건을 별도 표시한다. `입주기업`만으로 공장 보유를 요구하지 않는다. | `monitor.py:365-388`, `factory_required`, `required_conditions` | 유지; 자동 적격 판정 아님 |
| 단독 입주공간 | `4dc50a85`의 P0-4 설명·테스트 `test_p0_space_only_is_excluded`; `tests/test_monitor.py:952-970` | 과거 의도는 단독 교육·멘토링·컨설팅·투자·입주공간을 제외하고, 입주공간+사업화자금은 포함하는 것이었다. | 현재 P0-4에는 금융/컨설팅/투자 분리와 입주 관련 지역 판정은 있으나 독립 `TENANT_ONLY` reason code는 없음 | 보강 후보; 회귀 재현 후 최소 추가 |
| 수정·연장·재공고 | `b78485d4`, `eae23d2e`, `71e45889`, `8d1b88aa`, `3bceb69c`; `tests/test_notice_version_recovery.py`, `tests/test_version_delivery_integration.py` | 연장/재공고/중요 수정은 최근 게시일 범위를 넘어 재판정하고, 닫힌 수정은 제외했다. | `monitor.py:1053-...`, `monitor.py:4963-...`, `monitor.py:7282-...` | 유지 |
| 최근 공고·날짜불명 | `eae23d2e`, `71e45889`, `8d1b88aa`; `config/settings.json`; date tests | 최근 영업일 재조회, 날짜불명 recall 정책, 본문 날짜의 오래된 공고 제한을 함께 사용했다. | `config/settings.json`, `monitor.py:8420-8475`, `tests/test_date_unknown_policy.py` | 유지 |
| 중복 추천 방지 | `3942977e`, `f029b668`, `eb973565`, `d7f19b86`; `tests/test_notice_version_recovery.py`, `tests/test_outbox_seen_ids_multigroup.py` | 동일 공고 canonical ID/유사도와 발송 상태를 분리해 중복을 막고, 부분 그룹 실행이 전역 seen을 오염시키지 않게 했다. | `monitor.py:4333-...`, `monitor.py:7282-7890`, delivery/version tests | 유지 |
| 카테고리의 위치 | `af448f10`, `f2f34c7f`, `fd506102`; `mail_core/matching/core_sources.py` | 지원분야/카테고리는 표시·지원유형 보강용이며, 공고 적격성 하드 게이트를 대체하지 않는다. | `evaluate_notice`가 먼저 hard gate·키워드·점수 판정, 이후 메일 표시에서 유형/카테고리 사용 | 유지; 표시값 |

## 현재도 살아있는 기준

- 기본 관심: 베트남, 동남아, 해외, 글로벌, 박람회, 전시회, 소상공인, 지원금, 공장, 스마트/스마트공장.
- AI/예비창업: 예비창업자·창업예정자와 AI·창업·사업화·지원금·실증 결합 규칙, 기창업 전용·솔루션 도입 제외.
- 우선: 혁신바우처·수출바우처 및 직접지원/사업화자금 priority. 우선어도 신청자격·지역·마감 hard gate를 우회하지 않음.
- 제외: 설명회·컨설팅지원·멘토링·교육·지침·결과·채용·공급기업·수행기관·선정기업 전용. 본문 우연 언급은 모집 본체와 함께일 때 soft/review로 보존.
- 지역: 공고기관 지역과 신청대상 지역 분리, 전국/수도권 허용, 인천 특정 구 배타, 지역 미상은 `region_unknown_review`로 surface.
- 공장: 공고 수집/분류와 기업별 공장 적격성 확인 분리. `입주기업` 단독은 공장 신호가 아님.
- 날짜/중복: 최근 재조회, 날짜불명 recall, 연장·재공고·중요 수정 재판정, canonical/delivery 상태 기반 중복 방지.

## 사라졌거나 현재 구조로 대체된 기준

| 항목 | 증거 | 처리 |
| --- | --- | --- |
| 과거 Goyang 전용 그룹·업력 버킷 | `c29d3276`에서 `test_goyang_precision.py` 삭제 및 `grp_goyang`을 `grp_prestartup_ai`로 교체 | 현재 기본 프로필은 예비창업 AI이며, Goyang 전용 업력 기준은 활성 사용자 기준으로 복원하지 않음. 삭제 이력을 보고만 남김. |
| 전역 단순 `멘토링` 제외 | `4dc50a85`에서 `GENERAL_SERVICE_EXCLUDE_KEYWORDS`에서 제거하고 P0-4 문맥형 `CONSULTING_ONLY`로 전환 | 현재 문맥형 로직을 유지. |
| 단순 카테고리 기반 발송 | `fd506102`, `4dc50a85` 이후 evaluator/diagnostics 구조 | 카테고리는 마지막 표시값이고 적격성은 evaluator hard gate가 먼저 처리. |
| 루트 설정·테스트 경로 | `45dff95b`, `5a94b1bd` 등의 rename | `config/`, `mail_core/`, `tests/`의 현재 경로를 사용. |
| `var/tmp_unique_tests/*`와 `docs/MATCHING_ARCHITECTURE.md` | 삭제 이력 `a3fbeea0` 및 관련 rename/delete 이력 | 내용은 살아 있는 회귀 테스트·현재 코드 주석과 대조했으며, 원문 복사나 복구 파일 생성은 하지 않음. |

## 충돌·주의 기준

| 충돌 | 비교 | 적용 결론 |
| --- | --- | --- |
| 예비창업 AI 그룹의 지역 범위 | 사용자 표현은 서울 예비창업자였으나 `c29d3276` 과거 설정과 현재 테스트는 서울 외 인천·경기·수도권도 허용 | 최신 저장소의 명시 설정을 유지하고, 이번 조사에서 임의로 서울 단일 범위로 좁히지 않음. |
| 멘토링·컨설팅 | 초기 그룹 설정은 단순 제외였으나 `4dc50a85` 이후 재정지원과 병행 시 포함하도록 변경 | 최신 문맥형 `CONSULTING_ONLY`를 적용. |
| 입주기업과 공장 | 초기 공장 키워드에 입주 관련 표현이 있었으나 `a7ec9580`에서 `입주기업`을 공장 필수 신호에서 분리 | `입주기업`만으로 공장 필수 판정하지 않음. 단독 입주공간의 적격성은 별도 후보로 테스트한다. |
| 날짜 최근 3일과 중요 변경 | 단순 게시일 창은 오래된 연장/수정공고를 놓칠 수 있었음 | 현재 버전 분류가 중요 변경을 날짜 필터보다 앞에서 재판정하는 최신 구조를 유지. |

## 판정 순서 확인

현재 `execute_monitor`는 수집·중복제거·버전 후보/상세 보강·날짜 필터를 거친 뒤 `filter_for_group_with_diagnostics`에서 `evaluate_notice`를 호출한다(`monitor.py:7282-7890`, `monitor.py:6006-6030`). evaluator 안에서는 신청/공고성, 마감, 신청자 지역, 그룹 제외, 그룹 키워드, 지원유형, 단독 서비스성 공고, 점수/상세 검토를 판정한다(`monitor.py:5586-6000`). 메일의 지원유형·카테고리 표시와 기업별 2차 정밀 점수는 그 뒤에 적용된다. 즉 카테고리만 보고 먼저 발송하는 순서는 현재 코드에 없다.

## 다음 최소 작업

1. 현재 P0-4의 단독 입주공간 케이스를 `AI + 입주공간 + 금융지원 없음`으로 재현한다.
2. 과거 18개 최소 사례와 중복/버전 사례를 하나의 MAIL-015 회귀 테스트로 고정한다. 재현 결과 독립 `TENANT_ONLY` 사유코드가 실제 누락이면 evaluator에만 최소 보강한다.

실제 메일 발송·라벨 변경·삭제는 이 조사에서 수행하지 않았다.
