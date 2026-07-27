# 공고 수집 안 되는 사이트 정리 (전달용)

- 점검일: 2026-06-21
- enabled 사이트 219개 중 **27개**가 1페이지 수집 0건
- "진단"은 왜 0건인지 추정 원인 (메뉴페이지=URL부터 게시판 아님 / JS=동적 / 셀렉터=게시판은 있으나 수집규칙 불일치 / 접근불가=사이트 다운·차단)

| 사이트 | type | 진단 (왜 0건) | 현재 URL | sites.json 비고 |
|---|---|---|---|---|
| 인천신용보증재단 | html_table | 메뉴/홈 페이지 (실제 게시판 URL 아님) | https://www.icsinbo.or.kr/home/board/brdList.do?menu_cd=0000 | 소상공인/제조업 보증 공고 목록 [URL 오류 수정: icgf. |
| 인천 부평구청 | html_table | 메뉴/홈 페이지 (실제 게시판 URL 아님) | https://www.icbp.go.kr/main/eminwon/eminwonAnnounceList.do | 부평구 고시·공고/입법예고 [2026-06 도메인 정정: bpy |
| 중소벤처기업진흥공단(KOSME) | html_table | 구조 불일치 (table=2, a=530) | https://www.kosmes.or.kr/nsh/SH/NTS/SHNTS001M0.do | 정책자금/수출바우처 공지사항 목록 [홈페이지에서 공고 목록 UR |
| 한국무역보험공사(K-SURE) | html_table | 구조 불일치 (table=1, a=512) | https://www.ksure.or.kr/rh-kr/bbs/i-671/list.do | 수출보험/보증 공고 목록 [홈페이지에서 공고 목록 URL로 변경 |
| 한국여성벤처협회 | html_table | 구조 불일치 (table=1, a=395) | https://kovwa.or.kr/94 | 여성벤처 지원사업 [PC 실행 시 정상 접속] |
| 과학기술정보통신부 | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.msit.go.kr/bbs/list.do?sCode=user&mId=113&mPid=1 | 과기부 [PC 실행 시 정상 접속] |
| 문화체육관광부 | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.mcst.go.kr/kor/s_notice/press/pressView.jsp | 문체부 [PC 실행 시 정상 접속] |
| 기획재정부 | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.moef.go.kr/nw/nes/nesdta.do?searchBbsId1=MOSFBBS | 기재부 [PC 실행 시 정상 접속] |
| 한국산업기술진흥원(KIAT) | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.kiat.or.kr/front/board/boardContentsListPage.do? | KIAT 사업공고 [2026-06 URL 갱신: /front/u |
| KOTRA(대한무역투자진흥공사) | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.kotra.or.kr/kp/biz/notificationList.do | 해외진출/수출 [PC 실행 시 정상 접속] |
| 한국환경산업기술원(KEITI) | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.keiti.re.kr/site/keiti/ex/board/List.do?cbIdx=27 | 환경산업 공지/공고 목록 [홈페이지에서 공고 목록 URL로 변경 |
| 서울산업진흥원(SBA) | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.sba.seoul.kr/kr/sbcu31l1 | 서울시 중소기업 사업공고 목록 [구 URL에서 신 URL(/kr |
| 경기도경제과학진흥원(GBSA) | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://pms.gbsa.or.kr/info/pblanc/pblancList.do | 경기도 기업 지원 사업공고 목록 [홈페이지→G-PMS 사업공고  |
| 마이페어 | myfair_html | JS로 그리는 동적 페이지 (정적 수집 불가) | https://myfair.co/support-program-list | 통합포털 - 해외전시회 [PC 실행 시 정상] |
| 인천상공회의소 | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://incheon.korcham.net/front/board/boardContentsListPag | 수출상담회/바이어매칭 새소식 목록 [URL 오류 수정: inch |
| KOTRA 무역투자24 - 사업공고 | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.kotra.or.kr/bigList/20000020753 | 수출바우처/해외전시회/시장개척단 [PC 실행 시 정상 접속] |
| 소상공인시장진흥공단 - 사업공고 | html_table | JS로 그리는 동적 페이지 (정적 수집 불가) | https://www.semas.or.kr/web/SUP/supportAnnounce.kmdc | 소공인 지원사업 공고 [PC 실행 시 정상 접속] |
| 산업통상자원부 | html_table | 게시판 있음(행 10개) → 수집 셀렉터/날짜파싱 안 맞음 | https://www.motie.go.kr/kor/article/ATCL2826a2625 | 산업부 |
| 한국산업기술평가관리원(KEIT) | html_table | 게시판 있음(행 3개) → 수집 셀렉터/날짜파싱 안 맞음 | https://itech.keit.re.kr/bsnsancm/retrieveSprtBsnsAncmList.d | KEIT 지원사업공고 [2026-06 URL 갱신: www.ke |
| 신용보증기금(KODIT) | html_table | 게시판 있음(행 10개) → 수집 셀렉터/날짜파싱 안 맞음 | https://www.kodit.co.kr/kodit/na/ntt/selectNttList.do?mi=263 | 신용보증 공지사항 목록 [홈페이지에서 공지사항 목록 URL로 변 |
| 한국디자인진흥원(KIDP) | html_table | 게시판 있음(행 10개) → 수집 셀렉터/날짜파싱 안 맞음 | https://www.kidp.or.kr/?menuno=918&act=list | 디자인산업 공고 목록 [홈페이지에서 공고 목록 URL로 변경,  |
| 지역디자인통합플랫폼 | html_table | 게시판 있음(행 12개) → 수집 셀렉터/날짜파싱 안 맞음 | https://www.rdcdp.or.kr/index.do?menu_id=00000746 | 지역 디자인 지원 [PC 실행 시 정상 접속] |
| 서울TP | html_table | 게시판 있음(행 15개) → 수집 셀렉터/날짜파싱 안 맞음 | https://www.seoultp.or.kr/user/nd19746.do | 서울테크노파크 [PC 실행 시 정상 접속] |
| 혁신제품지정공고(나라장터) | html_table | 게시판 있음(행 10개) → 수집 셀렉터/날짜파싱 안 맞음 | https://ppi.g2b.go.kr:8914/cm/bbs/usr/00031/bbsList_usr.do | 혁신제품 지정/조달 [PC 실행 시 정상 접속] |
| 비즈오케이 - 인천 연간사업공고계획 | html_table | 게시판 있음(행 206개) → 수집 셀렉터/날짜파싱 안 맞음 | https://bizok.incheon.go.kr/open_content/support/plan/plan20 | 인천TP 연간 공고 일정표 [PC 실행 시 정상 접속] |
| 경남테크노파크 | html_table | 게시판 있음(행 10개) → 수집 셀렉터/날짜파싱 안 맞음 | https://www.gntp.or.kr/board/list | 새소식 / 주기:주 2~3회 / 우선순위:상 |
| 해양수산부 | html_table | 접근 불가 (연결실패/차단/타임아웃) | https://www.mof.go.kr/article/list.do?menuKey=971&boardKey=1 | 해수부 [PC 실행 시 정상 접속] |
