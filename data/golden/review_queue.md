# region_labels 리뷰 큐 (판정기 != 약라벨 의심후보 -> 사람확인 -> Tier C 승격)

<!-- 사용법: human_region 칸에 실제 정답 지역(예: 서울/경기/전국)을 적고 status 를 confirmed 로 바꾸면,
     다음 사이클에서 tier=C 로 승격됩니다. 비우거나 pending 이면 승격 안 함(추측 금지).
     scorer_signal 은 사람이 어디를 볼지 돕는 힌트일 뿐, 절대 라벨이 되지 않습니다. -->

| id | scorer_signal | weak_label | city | title | human_region | status |
|----|---------------|------------|------|-------|--------------|--------|
| kstartup_178262 | fn_weaklabel_own | 서울특별시 | 서울 | 2026년 서울시 소셜벤처 IR 데모데이(도약단계) 참여기업 모집 새로운게시글 |  | pending |
| kstartup_178265 | fn_weaklabel_own | 서울특별시 | 서울 | 인베스트서울 2026년도 하반기 Core기업 모집 공고 새로운게시글 |  | pending |
| PBLN_000000000118556 | queue:ambiguous_region_name |  |  | 2026년 디지털커머스 전문기관(소담스퀘어 in 광주) 모집 공고 |  | pending |
| PBLN_000000000119584 | queue:ambiguous_region_name |  |  | 2026년 광주테크노파크 공동활용 연구시설ㆍ장비 사용 안내 공고 |  | pending |
| PBLN_000000000119817 | queue:ambiguous_region_name |  |  | 2026년 광주 창업BuS 프로그램 창업기업 모집 공고 |  | pending |
| PBLN_000000000123643 | queue:region_conflict |  |  | 2026년 울산시ㆍ경주시ㆍ포항시 2차 해오름동맹 첨단이차전지 연대협력사업 기업지원 수혜기업 모집 공고 |  | pending |
| PBLN_000000000124143 | queue:ambiguous_region_name |  |  | 2026년 광주콘텐츠코리아랩 지역 연계 미드폼 콘텐츠 제작지원 모집 공고 |  | pending |
| PBLN_000000000124308 | queue:region_conflict |  |  | 2026년 울산시ㆍ경주시ㆍ포항시 해오름동맹 첨단이차전지 연대협력사업 기업지원 수혜기업 상시 모집 공고 |  | pending |
| imp_05ecda5b_d807e148d7ab4168c463 | queue:region_conflict |  |  | 2026년 소셜 벤더 운영 사업(성장 지원형 – 서울·인천 권역) 참여 기업 모집 |  | pending |
| imp_2b5aeab3_4f4bb6fd7c606874e868 | queue:ambiguous_region_name |  |  | 「2025년 중소벤처기업부 광주 지역 주력산업개편」 산업별 육성품목 사전 수요조사 공고 |  | pending |
| imp_2b5aeab3_d6402047fa95ebdc2fd3 | queue:ambiguous_region_name |  |  | 2026년 광주 지역혁신클러스터육성 비R&D 기업지원 수요조사 공고 |  | pending |
| imp_3ca8e0e6_1587d7006dce0e83ca02 | queue:ambiguous_region_name |  |  | 새글 광주정보문화산업진흥원(GICON) 제3기 시민자문위원 위원 선정결과 공고 |  | pending |
| imp_3ca8e0e6_1b7234d6f80f70470362 | queue:ambiguous_region_name |  |  | 새글 [광주글로벌게임센터]게임사운드 크리에이터 지원사업 게임 개발사 추가모집 공고 |  | pending |
| imp_3ca8e0e6_3498b1ceb23b712c4b98 | queue:ambiguous_region_name |  |  | 「2026 광주 지역특화콘텐츠개발지원사업」 콘텐츠 IP 지역특화 상품개발지원 참가기업 모집공고 |  | pending |
| imp_3ca8e0e6_469dffa18e4e4565fb53 | queue:ambiguous_region_name |  |  | 새글 「2026 광주콘텐츠코리아랩」지역 연계 미드폼 콘텐츠 제작지원 모집 공고 |  | pending |
| imp_3ca8e0e6_928df45a7f05387db2c2 | queue:ambiguous_region_name |  |  | 새글 「2026 광주 지역특화콘텐츠개발지원사업」캐릭터 라이선싱 페어 2026 공동관 참가기업 추가모집 선정평가 .. |  | pending |
| imp_3ca8e0e6_95c072c7ba636ca27655 | queue:ambiguous_region_name |  |  | 「2026 광주콘텐츠코리아랩」지역 연계 미드폼 콘텐츠 제작지원 모집 공고 |  | pending |
| imp_3ca8e0e6_a802fdbcda4dda0c044a | queue:ambiguous_region_name |  |  | 새글 [광주글로벌게임센터] 신규 입주기업 선정 결과 |  | pending |
| imp_3ca8e0e6_b28fa490d4dd96574a80 | queue:ambiguous_region_name |  |  | 「2026 광주 지역특화콘텐츠개발지원사업」 콘텐츠 IP 지역특화 상품개발지원 참가기업 모집공고 |  | pending |
| imp_60bf007e_ab3893ea8c14f31a61db | queue:region_conflict |  |  | 2026년 스마트제조 전문인력 육성사업 참여기업(수도권 - 서울, 경기, 인천) 모집 |  | pending |
| imp_7505182c_8ab6e95fb84dda28494c | queue:region_conflict |  |  | 모집중(2026-140호) 강원 바이오-헬스케어 AI 대전환 실증기업 모집 공고 |  | pending |
| imp_7505182c_ee20eaedb694fb2d8f72 | queue:region_conflict |  |  | 모집중(2026-141호) 강원 바이오-헬스케어 AI 대전환 수요기업 모집 공고 |  | pending |
| imp_761f4e5f_0b9fe5a76adffc601fc4 | queue:ambiguous_region_name |  |  | 2026 광주 사회적경제 고도화 및 업종 다각화 지원사업 선정결과 공고 |  | pending |
| imp_761f4e5f_11fad023488f736f9f6e | queue:ambiguous_region_name |  |  | 2026년 광주사회적경제지원센터 신규직원 채용 서류전형 합격자 공고 |  | pending |
| imp_761f4e5f_1bd740e28121ce7c92f5 | queue:ambiguous_region_name |  |  | 광주사회적경제지원센터 신규직원 채용 최종합격자 공고 |  | pending |
| imp_761f4e5f_37743f2e2a530d63b51b | queue:ambiguous_region_name |  |  | 광주사회적경제 온라인 교육플랫폼 '가치스쿨' 이용 안내 |  | pending |
| imp_761f4e5f_3bee242d94c526a38396 | queue:ambiguous_region_name |  |  | 2026 사회적경제 지역연계장터 “하이, 푸릇 마켓! in 광주시립수목원” 행사 안내 |  | pending |
| imp_761f4e5f_5a816dfda0574df4c62c | queue:ambiguous_region_name |  |  | 2026년 광주사회적경제지원센터 신규직원 채용 최종합격자 공고 |  | pending |
| imp_761f4e5f_6ddb6535f9c324122ab9 | queue:ambiguous_region_name |  |  | 광주사회적경제지원센터 신규직원 채용 연장 공고(~2026.4.21.) |  | pending |
| imp_761f4e5f_948dc5c00dcde6645df2 | queue:ambiguous_region_name |  |  | 2026 광주 사회적경제 가치소비 책자, 함께할 기업을 찾습니다! |  | pending |
| imp_761f4e5f_9c9534a943a6f047c70d | queue:ambiguous_region_name |  |  | 2026년 광주사회적경제지원센터 신규직원 채용 서류전형 합격자 공고 |  | pending |
| imp_761f4e5f_9e9f030d0b9d56b212d8 | queue:ambiguous_region_name |  |  | 2026년 광주사회적경제지원센터 신규직원 채용 최종합격자 공고 |  | pending |
| imp_761f4e5f_ab374ac6ba45f268d4ed | queue:ambiguous_region_name |  |  | 2026 광주 사회연대경제 주간 |  | pending |
| imp_761f4e5f_b0cf62f0feb147dfe088 | queue:ambiguous_region_name |  |  | 광주 사회적경제기업들을 위한 <광주 SE 최신 정보방> 오픈채팅방 OPEN! |  | pending |
| imp_761f4e5f_e13eebd2b1c2aace6567 | queue:ambiguous_region_name |  |  | 광주사회적경제지원센터 신규직원 채용 공고(~2026. 6. 19.) |  | pending |
| imp_761f4e5f_ec54280285bd788e6217 | queue:ambiguous_region_name |  |  | 5·18 나눔과 연대의 정신으로, 오월광주 사회적경제 가치마켓 개최 |  | pending |
| imp_761f4e5f_fdb780e36f4f63747284 | queue:ambiguous_region_name |  |  | 2026 광주 사회연대경제 주간 |  | pending |
| imp_803b04b9_4494f4a59ea9888d6f62 | queue:ambiguous_region_name |  |  | 2026년도 지역주력산업육성(지역특화 프로젝트 "레전드 50+") 지원모집 2차 공고 (광주 2.0, 스마트홈·생체의료소재부품산업) |  | pending |
| imp_803b04b9_9b20e2706ef0c90489ca | queue:ambiguous_region_name |  |  | 2026년도 지역주력산업육성(지역특화 프로젝트 "레전드 50+") 지원모집 2차 공고 (광주 1.0, 지역대표산업) |  | pending |
| imp_803b04b9_9cc8514d5b21f892fc5c | queue:ambiguous_region_name |  |  | 「광주첨단 스마트그린 AX실증산단 구축사업」 제조경쟁력 강화를 위한 기업AX 실증지원 |  | pending |
| imp_803b04b9_a081b276f3eb3234ded6 | queue:ambiguous_region_name |  |  | 광주청년창업지원센터 입주스타트업(20기) 모집 공고 |  | pending |
| imp_803b04b9_a7ab504f3caeac8bcf0a | queue:ambiguous_region_name |  |  | 2026년 광주 북구 4차 산업 융합 미니클러스터 운영사업 융합 프로젝트 기획 및 사업화 지원 공고 |  | pending |
| imp_803b04b9_a96297bd528b9d5960b5 | queue:ambiguous_region_name |  |  | 2026년 광주형 스마트공장 전담멘토단 운영 사업 신청 안내 공고 |  | pending |
| imp_803b04b9_ab4ebbfff042435d0d8d | queue:ambiguous_region_name |  |  | 광주 AI 의료생태계 구축「AI의료 전주기적 지원서비스」사업 수행기업 모집공고(4차) |  | pending |
| imp_803b04b9_e142aef63a0774261845 | queue:ambiguous_region_name |  |  | 광주첨단 AX실증산단구축사업(2차년도) 제조 AX 멘토링 수혜기업 모집 공고 |  | pending |
| imp_803b04b9_ec7dcbc93735ab065a82 | queue:ambiguous_region_name |  |  | 2026년도 지역주력산업육성(지역특화 프로젝트 "레전드 50+") 지원모집 2차 공고 (광주 1.0, 미래차 전환) |  | pending |
| imp_8998eef2_4714f6fc199eb6606b81 | queue:ambiguous_region_name |  |  | 광주주거복지협동조합-지역 강소기업-광주광역자활센터, 자재 공동구매 업무협약 체결 |  | pending |
| imp_a11ba09c_26fa0bd6a80620baf258 | queue:region_conflict |  |  | 충남농업6차산업센터, 대전 세이백화점에 안테나숍 신규 입점 |  | pending |
| imp_a11ba09c_329084ccc69439108106 | queue:region_conflict |  |  | 충남농업6차산업센터, 대전 세이백화점에 안테나숍 신규 입점 |  | pending |
| imp_a11ba09c_7c4632779932aae4ba20 | queue:region_conflict |  |  | 충남농업6차산업센터, 대전 세이백화점에 안테나숍 신규 입점 |  | pending |
| imp_a11ba09c_eadfb65eb1ce9a3991fb | queue:region_conflict |  |  | 충남농업6차산업센터, 대전 세이백화점에 안테나숍 신규 입점 |  | pending |
| imp_a11ba09c_f8696049658c0abdda1b | queue:region_conflict |  |  | 충남농업6차산업센터, 대전 세이백화점에 안테나숍 신규 입점 |  | pending |
| imp_a11ba09c_fbacaf23866144fe0b20 | queue:region_conflict |  |  | 충남농업6차산업센터, 대전 세이백화점에 안테나숍 신규 입점 |  | pending |
| imp_c5c8a218_2c195df6b0834127c6de | queue:ambiguous_region_name |  |  | 광주회생법원 개원 안내 |  | pending |
| imp_c5c8a218_4af402d610acc29a3c5c | queue:ambiguous_region_name |  |  | 광주경영자총협회 공고 제2025-2호 서류 전형 합격자 통보 |  | pending |
| imp_c5c8a218_557b058636a4416ba78f | queue:ambiguous_region_name |  |  | 광주경영자총협회 채용 합격자 발표 |  | pending |
| imp_c5c8a218_785bf59a07e9e0ef6fd7 | queue:ambiguous_region_name |  |  | 광주경영자총협회 공고 제2025 - 3호 일자리 사업 채용 최종 합격자 안내 |  | pending |
| imp_c5c8a218_e2a082f280c659e808e4 | queue:ambiguous_region_name |  |  | 광주경총 회원사 홍보 서비스 안내 |  | pending |
| imp_c5c8a218_e855abf67098ec43c231 | queue:ambiguous_region_name |  |  | 광주경영자총협회 직원 채용 공고 |  | pending |
| imp_cdcaa04f_3eb87e17f92ee1db8a33 | queue:ambiguous_region_name |  |  | 2026년 제3차 범부처 중소기업 기술보호 교육 설명회 개최 안내(7.2, 광주) |  | pending |
| imp_cdcaa04f_6e48c3afed7cb076e26c | queue:ambiguous_region_name |  |  | 2026년 제3차 범부처 중소기업 기술보호 교육 설명회 개최 안내(7.2, 광주) |  | pending |
| imp_cdcaa04f_747ccb86ee0599c975f2 | queue:ambiguous_region_name |  |  | 2026년 제3차 범부처 중소기업 기술보호 교육 설명회 개최 안내(7.2, 광주) |  | pending |
| imp_cdcaa04f_ccc4deca84d422f1123f | queue:ambiguous_region_name |  |  | 2026년 제3차 범부처 중소기업 기술보호 교육 설명회 개최 안내(7.2, 광주) |  | pending |
| imp_cdcaa04f_e97d4175a3f567aa53a7 | queue:ambiguous_region_name |  |  | 2026년 제3차 범부처 중소기업 기술보호 교육 설명회 개최 안내(7.2, 광주) |  | pending |
| imp_cdcaa04f_fbfebb43b61fbcad1ab6 | queue:ambiguous_region_name |  |  | 2026년 제3차 범부처 중소기업 기술보호 교육 설명회 개최 안내(7.2, 광주) |  | pending |
| imp_d6c628c3_ddbdf4e9f8cb324a817f | queue:ambiguous_region_name |  |  | 광주상공회의소 해외 산업‧역사 탐방 대행여행사 위탁용역 입찰공고 |  | pending |
| incheon_city_DOM_0000000015154052 | queue:region_conflict |  |  | 인천·제주, 항공우주 인재양성 협력 본격화…'A2CL 대학-기업협의체' 출범 인천광역시(시장 박찬대)는 7월 15일 인천 항공우주산학융합원에서 |  | pending |
| incheon_city_DOM_0000000015154171 | queue:region_conflict |  |  | 이미지 없음 인천시, 서울7호선 청라연장 건설사업‘시민감시단’전격 구성…주민간담회 요구 신속 반영 인천광역시 도시철도건설본부는 서울도시철도 7호 |  | pending |
| semas_announce_1046c430189f3f526859 | queue:region_conflict |  |  | 『2026년도 소상공인 디지털 특성화대학』사업 서울강원권 운영기관 선정 결과 안내 |  | pending |
| imp_826782fd_42e931d7d3984d67a170 | queue:org_or_ambiguous |  |  | [울산대학교] 2026년도 지역 중소∙중견기업 제조 AI∙DX 컨설팅 지원 안내(기한연장) |  | pending |
| imp_826782fd_b9adcff877dfd1dc52c3 | queue:org_or_ambiguous |  |  | [울산대학교] UbiCam 2026학년도 여름학기 교육 안내 |  | pending |
| imp_826782fd_fd00462dc61fc27dd4a7 | queue:org_or_ambiguous |  |  | [울산대학교] 2026년도 지역 중소∙중견기업 제조 AI∙DX 컨설팅 지원 안내 |  | pending |
| ripc_pms_notice_4756 | queue:org_or_ambiguous |  |  | [광주] 2026년 북구 지식재산 긴급지원(지식재산권리화 지원) 사업 공고문(3차) |  | pending |
| ripc_pms_notice_4757 | queue:org_or_ambiguous |  |  | [광주] 2026년 서구 지식재산 긴급지원(지식재산권리화 지원) 사업 공고문(3차) |  | pending |
| imp_ed9e0571_4aa5ef6bc5d3ee425800 | queue:sub_region |  |  | (광주시)2027년 뿌리산업 경쟁력 강화 지원사업 참여 수요조사 |  | pending |
| imp_ed9e0571_709b2d4486525d43b5de | queue:sub_region |  |  | (광주시)「2026년 광주시 미국 해외시장개척단」 참가기업 모집 안내 |  | pending |
| PBLN_000000000123653 | queue:org_or_ambiguous |  |  | [전남광주] 전남광주통합특별시 광주권역 사회연대경제 청년 일경험 시범사업 참여기업 2차 모집 공고 |  | pending |
| PBLN_000000000124327 | queue:org_or_ambiguous |  |  | [전남광주] 제4회 전남광주통합특별시 북구청장배 청년창업 아이디어 경진대회 참가자 모집 공고 |  | pending |
| imp_3ca8e0e6_047e7b82cb13308f00ac | queue:org_or_ambiguous |  |  | [2026 광주음악창작소]뮤지션 제작지원 최종 선정대상자 결과발표 |  | pending |
| imp_e02ba1cb_61442a4073947407120d | queue:org_or_ambiguous |  |  | [경기과학기술대학교] 신산업분야(수소 등) 재직자 직무교육(무료) 참여희망기업 모집 안내 |  | pending |
| imp_47dc766c_1e36ec8bc2b551dd18a3 | queue:org_or_ambiguous |  |  | [경기대학교] 중소벤처기업부가 지원하는 "중소기업 계약학과" 석사과정 2026-2학기 신입생 모집 안내(기한: ~26.8....N |  | pending |
| PBLN_000000000121099 | queue:org_or_ambiguous |  |  | [경남ㆍ부산ㆍ울산ㆍ전남] 2026년 중소조선 함정MRO 글로벌 경쟁력 강화지원사업 함정MRO 전문인력양성 참여기업 모집 공고 |  | pending |
| imp_b3d682a9_b312fd01cb44651a25be | queue:org_or_ambiguous |  |  | [경북대창업지원단] 의료바이오 특화분야 창업패키지 창업기업(2차) 모집 안내 |  | pending |
| imp_2b5aeab3_d69360da04b5f7dcfb4b | queue:org_or_ambiguous |  |  | [광주 인공지능사관학교 AI 도약과정 위탁운영] 제안서 평가위원(후보자) 공개 모집 공고 |  | pending |
| PBLN_000000000121214 | queue:org_or_ambiguous |  |  | [광주ㆍ전북ㆍ전남] 2026년 광주ㆍ호남권 거점기업 육성 금융지원 공고 |  | pending |
| imp_c5c8a218_a3dff55258b7acf681d3 | queue:org_or_ambiguous |  |  | (광주경영자총협회 공고 제 2026-2호) 사무국(재무/회계) 담당자 서류전형 합격자 공고 |  | pending |
| imp_d6c628c3_a969ae85408c32e0826e | queue:org_or_ambiguous |  |  | (광주경제진흥상생일자리재단) 해외 전시박람회 업체 모집공고 |  | pending |
| imp_3ca8e0e6_fb6d60d7559b06071a67 | queue:org_or_ambiguous |  |  | [광주글로벌게임센터]게임사운드 크리에이터 지원사업 게임 개발사 추가모집 공고 |  | pending |
| PBLN_000000000117698 | queue:org_or_ambiguous |  |  | [대구ㆍ경북ㆍ전북] 2026년 지역상생협력관 지역 상품 발굴 코칭ㆍ상담 사업 공고 |  | pending |
| PBLN_000000000123935 | queue:org_or_ambiguous |  |  | [대전ㆍ경북] 2026년 지역 첨단제조 스타트업 스케일업 지원사업 창업기업 모집 공고 |  | pending |
| PBLN_000000000123536 | queue:org_or_ambiguous |  |  | [대전ㆍ세종ㆍ충북ㆍ충남] 2026년 충청권 지역특화산업 취ㆍ창업 CDP지원 프로그램 참여기업 모집 공고 |  | pending |
| imp_d6c628c3_67a411e3481d29069769 | queue:ambiguous_region_name |  |  | (마감)광주상공회의소 사무국 계약직원(정부 지자체 수임사업) 채용 공고 |  | pending |
| imp_d6c628c3_30623df0cc210f0b2a43 | queue:ambiguous_region_name |  |  | (서류합격발표) 광주상공회의소 사무국 계약직원(정부 지자체 수임사업) 채용 |  | pending |
| PBLN_000000000123596 | queue:org_or_ambiguous |  |  | [서울ㆍ경기ㆍ인천ㆍ강원] 2026년 중소기업 AI활용 도입을 위한 AI훈련 참여기업 모집 공고 |  | pending |
| PBLN_000000000123983 | queue:org_or_ambiguous |  |  | [서울ㆍ인천ㆍ강원] 2026년 상시 디자인 컨설팅 지원 공고 |  | pending |
| PBLN_000000000123108 | queue:org_or_ambiguous |  |  | [서울ㆍ인천ㆍ경기ㆍ강원] 2026년 중소기업 AI훈련확산센터 참여기업 모집 공고 |  | pending |
| kstartup_178562 | queue:org_or_ambiguous |  |  | [서울과학기술대학교] SLA 3D프린터 새로운게시글 |  | pending |
| imp_234a9f58_227da094a88769f4c776 | queue:ambiguous_region_name |  |  | [인자위 공고 2025-22호] 2025년도 광주지역 인적자원개발위원회 신규 직원 채용 공고 |  | pending |
| imp_234a9f58_29940f1549cc4e625544 | queue:ambiguous_region_name |  |  | [인자위 공고 제2025-23호] 2025년도 광주지역 인적자원개발위원회 신규 직원(일자리창출 선임) 채용… |  | pending |
| imp_234a9f58_cd17c9393751dbba274a | queue:ambiguous_region_name |  |  | [인자위 공고 제2026-01호] 2026년도「산업구조변화대응 등 특화훈련」제1차 광주지역 훈련공급기관 선정… |  | pending |
| imp_234a9f58_3aed034175be4dee4af4 | queue:ambiguous_region_name |  |  | [인자위 공고 제2026-03호] 2026년 광주인자위 지역공모형 훈련 수요조사 공모 |  | pending |
| imp_234a9f58_f203f04010bdee71c5cd | queue:ambiguous_region_name |  |  | [인자위 공고 제2026-04호] 2026년도 광주지역 인적자원개발위원회 신규 직원(일자리창출 선임) 채용 … |  | pending |
| imp_234a9f58_a70376d2c107b97d3919 | queue:ambiguous_region_name |  |  | [인자위 공고 제2026-05호] 2026년도「산업구조변화대응 등 특화훈련」제2차 광주지역 훈련공급기관 선정… |  | pending |
| imp_234a9f58_098b59cf20e988856258 | queue:ambiguous_region_name |  |  | [인자위 공고 제2026-06호] 2026년도 광주지역인적자원개발위원회 신규 직원(일자리창출 선임) 채용 재… |  | pending |
| imp_234a9f58_776072f80f476a2ff86c | queue:ambiguous_region_name |  |  | [인자위 공고 제2026-08호] 2026년도「산업구조변화대응 등 특화훈련」제3차 광주지역 훈련공급기관 선정… |  | pending |
| imp_d6c628c3_4852cb935fdcd698891c | queue:ambiguous_region_name |  |  | [인자위 공고 제2026-09호] 2026년도 광주지역인적자원개발위원회 전담자(인력양성팀 주임) 채용 공고 |  | pending |
| PBLN_000000000123924 | queue:org_or_ambiguous |  |  | [전북ㆍ전남광주] 2026년 서남권 가상융합산업 허브센터 운영사업 AI-MEC 가상융합 콘텐츠 기술 고도화 지원사업 모집 공고 |  | pending |
| imp_234a9f58_c13670093014a15d1fef | queue:ambiguous_region_name |  |  | (지역산업맞춤형 일자리 지원사업_버팀이음프로젝트) 광주 고용이음 위기 극복 프로젝트 수정공고 |  | pending |
| PBLN_000000000124328 | queue:org_or_ambiguous |  |  | [충청권ㆍ호남권] 2026년 4차 충청호남권 상생소공인특화지원센터 지원사업 통합 공고 |  | pending |
