# Auto Dev — L2 빈틈 인박스 (G1 게이트)

> FP/FN·정확도 헌터가 찾은 결함을 여기 적는다.
> `approved: yes` 로 바꾼 뒤 `python3 scripts/decompose_defects.py --approve` 하면
> `docs/project/TASKS.md` PENDING에 `loop:coding-fix` TASK가 추가된다.
> **승인 전 자동 코딩 금지** (`auto_dev/human_gates.md` G1).

## DEFECT-001

title: (예시) 권역 일반화 빈틈 — 경상/호남
approved: no
summary: company_match 권역 미처리로 타지역 누출 가설. 라벨 확인 후 최소수정.
loop: coding-fix

## DEFECT-002

title: (예시) 경로 불일치 그룹 PASS / 기업 BLOCK
approved: no
summary: monitor vs company_match 대칭 깨짐. matrix 재현 후 FIX.
loop: coding-fix
