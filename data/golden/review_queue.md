# region_labels 리뷰 큐 (판정기 != 약라벨 의심후보 -> 사람확인 -> Tier C 승격)

<!-- 사용법: human_region 칸에 실제 정답 지역(예: 서울/경기/전국)을 적고 status 를 confirmed 로 바꾸면,
     다음 사이클에서 tier=C 로 승격됩니다. 비우거나 pending 이면 승격 안 함(추측 금지).
     scorer_signal 은 사람이 어디를 볼지 돕는 힌트일 뿐, 절대 라벨이 되지 않습니다. -->

| id | scorer_signal | weak_label | city | title | human_region | status |
|----|---------------|------------|------|-------|--------------|--------|
| kstartup_178262 | fn_weaklabel_own | 서울특별시 | 서울 | 2026년 서울시 소셜벤처 IR 데모데이(도약단계) 참여기업 모집 새로운게시글 |  | pending |
| kstartup_178265 | fn_weaklabel_own | 서울특별시 | 서울 | 인베스트서울 2026년도 하반기 Core기업 모집 공고 새로운게시글 |  | pending |
