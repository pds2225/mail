# 사이트별 수집 커버리지

- 생성: 2026-07-16 10:28 KST
- collector 파일: `monitor.py`

| 사이트 | collector | URL | 수집 | 건수 | 날짜파싱 | date_unknown | 오늘기준 | 누락위험 | 오류 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 기업마당(Bizinfo) | bizinfo_api | https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do | OK | 1483 | 54 | 0 | 54 | 낮음 |  |
| 한양대 창업지원단(신규사업공고) | hanyang_startup_api | https://startup.hanyang.ac.kr/board/startup_info/l | OK | 30 | 3 | 0 | 3 | 낮음 |  |
| K-Startup | kstartup_html | https://www.k-startup.go.kr/web/contents/bizpbanc- | OK | 30 | 3 | 0 | 3 | 낮음 |  |
| 중소벤처24(SMEs24) | html_table | https://www.smes.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 보조금24 | html_table | https://www.gov.kr/portal/subsidy | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| NTIS(과학기술지식정보) | html_table | https://www.ntis.go.kr/rndgate/eg/un/ra/mng.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| IRIS(범부처통합연구지원) | iris_api | https://www.iris.go.kr/contents/retrieveBsnsAncmBt | OK | 10 | 1 | 0 | 1 | 낮음 |  |
| 나라장터(G2B) | html_table | https://www.g2b.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소벤처기업부 | mss_html | https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbI | OK | 10 | 3 | 0 | 3 | 낮음 |  |
| 과학기술정보통신부 | html_table | https://www.msit.go.kr/bbs/list.do?sCode=user&mId= | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 산업통상자원부 | html_table | https://www.motie.go.kr/kor/article/ATCL2826a2625 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 고용노동부 | html_table | https://www.moel.go.kr/info/govsupport/govsupportc | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 농림축산식품부 | html_table | https://www.mafra.go.kr/bbs/mafra/68/artclList.do | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 해양수산부 | html_table | https://www.mof.go.kr/article/list.do?menuKey=971& | FAIL | 0 | 0 | 0 | 0 | 높음 | 해양수산부 접속 실패 (HTML 수집) |
| 문화체육관광부 | html_table | https://www.mcst.go.kr/kor/s_notice/press/pressVie | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 기획재정부 | html_table | https://www.moef.go.kr/nw/nes/nesdta.do?searchBbsI | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 국토교통부 | html_table | https://www.molit.go.kr/USR/BORD0201/m_69/lst.jsp | OK | 10 | 3 | 0 | 3 | 낮음 |  |
| 정보통신산업진흥원(NIPA) | nipa_html | https://www.nipa.kr/home/bsnsAll/0/nttList?bbsNo=4 | OK | 2073 | 0 | 2073 | 0 | 높음 |  |
| 한국산업기술진흥원(KIAT) | html_table | https://www.kiat.or.kr/front/board/boardContentsLi | OK | 15 | 1 | 0 | 1 | 낮음 |  |
| 한국산업기술평가관리원(KEIT) | html_table | https://itech.keit.re.kr/bsnsancm/retrieveSprtBsns | OK | 3 | 0 | 0 | 0 | 낮음 |  |
| KOTRA(대한무역투자진흥공사) | html_table | https://www.kotra.or.kr/kp/biz/notificationList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소벤처기업진흥공단(KOSME) | kosme_api | https://www.kosmes.or.kr/nsh/SH/NTS/SHNTS001M0.do | OK | 42 | 2 | 0 | 2 | 낮음 |  |
| 소상공인시장진흥공단(SEMAS) | html_table | https://www.semas.or.kr/web/board/webBoardList.kmd | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 소진공 정책자금 온라인신청 | semas_loan_ols | https://ols.semas.or.kr/ols/man/SMAN051M/page.do | OK | 30 | 0 | 0 | 0 | 낮음 |  |
| 창업진흥원(KISED) | html_table | https://www.kised.or.kr/menu.es?mid=a10201000000 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국콘텐츠진흥원(사업공고) | kocca_pims | https://www.kocca.kr/kocca/pims/list.do?menuNo=204 | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 한국콘텐츠진흥원(금융) | kocca_bbs | https://www.kocca.kr/kocca/bbs/list/B0158960.do?me | OK | 11 | 0 | 1 | 0 | 높음 |  |
| 한국무역보험공사(K-SURE) | html_table | https://www.ksure.or.kr/rh-kr/bbs/i-412/list.do | OK | 12 | 2 | 0 | 2 | 낮음 |  |
| 기술보증기금(KIBO) | html_table | https://www.kibo.or.kr/main/board/boardType38.do?m | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 신용보증기금(KODIT) | html_table | https://www.kodit.co.kr/kodit/na/ntt/selectNttList | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국벤처투자(KVIC) | html_table | https://www.kvic.or.kr/vcms/contents/view.do?conte | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국보건산업진흥원(KHIDI) | html_table | https://www.khidi.or.kr/board?menuId=MENU02096 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국환경산업기술원(KEITI) | html_table | https://www.keiti.re.kr/site/keiti/ex/board/List.d | OK | 10 | 9 | 0 | 9 | 낮음 |  |
| 한국에너지기술평가원(KETEP) | html_table | https://www.ketep.re.kr/businessAcment?menuId=MENU | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국식품산업클러스터진흥원 | html_table | https://www.foodpolis.kr/foodpolis/bbs/list.do?bbs | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국디자인진흥원(KIDP) | html_table | https://www.kidp.or.kr/?menuno=918&act=list | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 지역디자인통합플랫폼 | html_table | https://www.rdcdp.or.kr/index.do?menu_id=00000746 | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 서울산업진흥원(SBA) | html_table | https://www.sba.seoul.kr/Pages/BusinessApply/Posti | OK | 10 | 2 | 0 | 2 | 낮음 |  |
| 경기도경제과학진흥원(GBSA) | html_table | https://pms.gbsa.or.kr/info/pblanc/pblancList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천테크노파크 | itp_html | https://www.itp.or.kr/intro.asp?tmid=13 | OK | 30 | 2 | 0 | 2 | 낮음 |  |
| 부산경제진흥원(BEP) | html_table | https://www.bepa.kr/kor/view.do?no=1508 | OK | 12 | 0 | 0 | 0 | 낮음 |  |
| 대전테크노파크 | html_table | https://www.djtp.or.kr/board.es?mid=a20102000000&b | OK | 11 | 1 | 0 | 1 | 낮음 |  |
| 마이페어 | myfair_html | https://myfair.co/support-program-list | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 한국무역협회(KITA) | kita_html | https://www.kita.net/asocBiz/asocBiz/asocBizOngoin | OK | 10 | 2 | 0 | 2 | 낮음 |  |
| SMTECH(중소기업기술개발) | smtech_html | https://www.smtech.go.kr/front/ifg/no/notice02_lis | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 경기TP | gtp_html | https://pms.gtp.or.kr/web/business/webBusinessList | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 경기스타트업플랫폼 | gsp_html | https://www.gsp.or.kr/supportProject/UVSL0001.do | OK | 10 | 1 | 0 | 1 | 낮음 |  |
| 창조경제혁신센터(공고) | ccei_html | https://ccei.creativekorea.or.kr/service/business_ | OK | 2 | 0 | 2 | 0 | 높음 |  |
| 창조경제혁신센터(행사) | ccei_html | https://ccei.creativekorea.or.kr/service/event_lis | OK | 2 | 0 | 2 | 0 | 높음 |  |
| 서울TP | html_table | https://www.seoultp.or.kr/user/nd19746.do | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 한국여성벤처협회 | html_table | https://kovwa.or.kr/94 | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 혁신제품지정공고(나라장터) | html_table | https://ppi.g2b.go.kr:8914/cm/bbs/usr/00031/bbsLis | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 한국콘텐츠진흥원(일반공고) | kocca_bbs | https://www.kocca.kr/kocca/bbs/list/B0000138.do?me | OK | 1 | 0 | 1 | 0 | 높음 |  |
| 공공데이터포털 | html_table | https://www.data.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 정부24(Gov.kr) | html_table | https://www.gov.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 비즈오케이(BizOK) - 인천기업지원 | bizok_html | https://bizok.incheon.go.kr/open_content/support.d | OK | 12 | 0 | 12 | 0 | 높음 |  |
| 비즈오케이 - 인천 연간사업공고계획 | html_table | https://bizok.incheon.go.kr/open_content/support/p | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 인천광역시청 - 공고/고시 | incheon_city_html | https://www.incheon.go.kr/IC010205 | OK | 10 | 7 | 0 | 7 | 낮음 |  |
| 인천테크노파크(ITP) - 공지사항 | itp_html | https://www.itp.or.kr/intro.asp?tmid=15 | OK | 30 | 1 | 0 | 1 | 낮음 |  |
| 인천경제자유구역청(IFEZ) | html_table | https://www.ifez.go.kr/main/pst/list.do?pst_id=not | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 인천상공회의소 | html_table | https://incheon.korcham.net/front/board/boardConte | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 인천수출경영자협의회 | html_table | https://www.ema.or.kr/bbs/support | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 인천소상공인종합지원센터 | html_table | http://www.insupport.or.kr/sub/?mcode=0404010000 | OK | 15 | 2 | 0 | 2 | 낮음 |  |
| 인천신용보증재단 | html_table | https://www.icsinbo.or.kr/home/board/brdList.do?me | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 인천 중구청 | html_table | https://www.icjg.go.kr/krcm01b | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 인천 동구청 | html_table | https://www.icdonggu.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천 미추홀구청 | html_table | https://www.michuhol.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천 연수구청 | html_table | https://www.yeonsu.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천 남동구청 | html_table | https://www.namdong.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천 부평구청 | html_table | https://www.icbp.go.kr/main/eminwon/eminwonAnnounc | OK | 10 | 6 | 0 | 6 | 낮음 |  |
| 인천 계양구청 | html_table | https://www.gyeyang.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천 서구청 | html_table | https://www.seo.incheon.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천 강화군청 | html_table | https://www.ganghwa.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천 옹진군청 | html_table | https://www.ongjin.go.kr/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| KOTRA 무역투자24 - 사업공고 | kotra_biz_api | https://www.kotra.or.kr/subList/20000020753 | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 소상공인시장진흥공단 - 사업공고 | html_table | https://www.semas.or.kr/web/board/webBoardList.kmd | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국보건산업진흥원(K-뷰티공고) | html_table | https://www.khidi.or.kr/board?menuId=MENU01108 | OK | 18 | 1 | 0 | 1 | 낮음 |  |
| 커넥트웍스(인천TP공고) | html_card | https://works.connect24.kr/search_result.php?org=인 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 디써클(RnD Circle) - 지원사업 | html_table | https://app.rndcircle.io/gov-grant | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 더브이씨(THE VC) - 지원사업 | html_table | https://thevc.kr/grants | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 비즈큐브(BizCube) | html_table | https://bizcube-sol.com/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천TP 마케팅센터(뷰티산업육성) | itp_html | https://www.itp.or.kr/intro.asp?tmid=36 | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 수출바우처(수출지원기반활용) | exportvoucher_html | https://www.exportvoucher.com/portal/board/boardLi | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 중소기업 혁신바우처(MSSMIV) | mssmiv_html | https://www.mssmiv.com/portal/board/BoardList?bbsI | OK | 14 | 0 | 0 | 0 | 낮음 |  |
| 예술경영지원센터 | html_card | https://www.gokams.or.kr/01_news/notice_list.aspx | OK | 111 | 0 | 111 | 0 | 높음 |  |
| (재)헬스케어스파산업진흥원 | html_table | https://hespa.or.kr/main/index.php?m_cd=23 | OK | 1 | 0 | 1 | 0 | 높음 |  |
| AI·SW 마에스트로 서울 | html_table | https://www.swmaestro.ai/sw/bbs/B0000002/list.do?m | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| ALIO 공공기관 경영정보 공개시스템 | html_table | https://www.alio.go.kr/notice/noticeList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| K-Startup 창업지원포털 | html_table | https://www.k-startup.go.kr/web/contents/webNOTICE | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| KBIZ 중소기업중앙회 | html_table | https://www.kbiz.or.kr/ko/contents/bbs/list.do?mnS | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| KOTRA 무역투자24 | html_table | https://www.kotra.or.kr/subList/41000022001 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| KOTRA 무역투자24 | html_table | https://www.kotra.or.kr/subList/20000005958?tabid= | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| MainBiz 메인 / 경영혁신형 중소기업 | html_table | https://www.smes.go.kr/mainbiz/usr/board/comNotice | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| Wbiz 여성기업 종합정보 포털 | html_table | https://www.wbiz.or.kr/notice/notice.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| Wbiz 여성기업 종합정보 포털 | html_table | https://wbiz.or.kr/notice/bizNew.do?searchOp8=recr | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 가족친화지원사업 | html_table | https://www.ffsb.kr/ffsb/bs/boardList.do?boardSeq= | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 강남취·창업허브센터 | html_table | https://www.gangnam-jobnstartup.com/program/list | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 강릉과학산업진흥원 | html_table | https://gsipa.or.kr/board/bbs/board.php?bo_table=n | OK | 50 | 0 | 49 | 0 | 높음 |  |
| 강원경영자총협회 | html_table | http://www.gwef.or.kr/bbs/board.php?bo_table=notic | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 강원농촌융복합산업지원센터 | html_table | https://gangwon6.co.kr/information/notices | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 강원바이오통합솔루션센터 | html_table | https://sc.cbfo.kr/index.php?mp=2 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 강원신용보증재단 | html_table | https://www.gwsinbo.or.kr/board/board_list.php?boa | OK | 21 | 1 | 1 | 1 | 낮음 |  |
| 강원지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/gangwon/ex/bbs/List.do? | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 강원지속가능경제지원센터 | html_table | https://gwse.or.kr/bbs/board.php?bo_table=sub41 | OK | 20 | 0 | 0 | 0 | 낮음 |  |
| 강원지역인적자원개발위원회 | html_table | https://gwhrd.or.kr/bbs/board.php?bo_table=sub01_0 | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 강원창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gangwon/custom/no | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 강원테크노파크 | html_table | https://www.gwtp.or.kr/gwtp/bbsNew_list.php?code=s | OK | 21 | 0 | 1 | 0 | 높음 |  |
| 강원테크노파크 | html_table | https://www.gwtp.or.kr/gwtp/bbsNew_list.php?code=s | OK | 33 | 0 | 0 | 0 | 낮음 |  |
| 강원특별자치도경제진흥원 | html_table | https://www.gwep.or.kr/bbs/board.php?bo_table=gw_s | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 강원특별자치도경제진흥원 | html_table | https://www.gwep.or.kr/bbs/board.php?bo_table=gw_s | OK | 15 | 2 | 0 | 2 | 낮음 |  |
| 경기경영자총협회 | html_table | http://gyef.or.kr/bbs/board.php?bo_table=notice | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기농촌융복합산업 활성화 지원센터 | html_table | https://www.xn--6-v85el2bkz7b4zfiuk.com/board/?mod | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기대진테크노파크 | html_table | https://gdtp.or.kr/board/notice | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기대진테크노파크 | html_table | https://gdtp.or.kr/board/announcement | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기대진테크노파크 | html_table | https://gdtp.or.kr/document/experti | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기도경제과학진흥원 | html_table | https://www.gbsa.or.kr/board/notice.do | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 경기도시장상권진흥원 | html_table | https://www.gmr.or.kr/base/board/list?boardManagem | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 경기도여성가족재단 | html_table | https://www.gwff.kr/base/board/list?boardManagemen | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 경기도 일자리포털 잡아바 | html_table | https://apply.jobaba.net/bsns/bsnsListView.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기도청 | html_table | https://www.gg.go.kr/bbs/board.do?bsIdx=469&menuId | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기신용보증재단 | html_table | https://www.gcgf.or.kr/gcgf/pt/pst/selectPstList.d | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기신용보증재단 | html_table | https://www.gcgf.or.kr/gcgf/cm/conts/contsView.do? | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/gyeonggi/ex/bbs/List.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기지역인적자원개발위원회 | html_table | https://www.gghrd.or.kr/board/notice.php | OK | 21 | 0 | 0 | 0 | 낮음 |  |
| 경기창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gyeonggi/custom/n | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경기콘텐츠진흥원 | html_table | https://www.gcon.or.kr/gcon/bbs/B0000001/list.do?m | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 경기테크노파크 | html_table | https://www.gtp.or.kr/web/bbs/noticeList.jsp?gbun= | OK | 20 | 0 | 0 | 0 | 낮음 |  |
| 경기테크노파크 | html_table | https://www.gtp.or.kr/web/bbs/noticeList.jsp?gbun= | OK | 20 | 0 | 0 | 0 | 낮음 |  |
| 경남6차산업지원센터 | html_table | https://www.xn--6-v85ew7hc2v44fiuk.com/board/board | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 경남경영자총협회 | html_table | https://www.gef.or.kr/core_board2007/board/coreboa | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경남신용보증재단 | html_table | https://www.gnsinbo.or.kr/bbs/board.php?bo_table=0 | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 경남지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/gyeongnam/ex/bbs/List.d | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경남지역인적자원개발위원회 | html_table | https://gnhrd.or.kr/bbs/board.php?bo_table=notice | OK | 12 | 0 | 0 | 0 | 낮음 |  |
| 경남창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gyeongnam/allim/a | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경남창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gyeongnam/allim/a | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경남테크노파크 | html_table | https://www.gntp.or.kr/board/list | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 경남테크노파크 | html_table | https://www.gntp.or.kr/biz/apply | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경남투자경제진흥원 | html_table | https://giba.or.kr/fe/bbs/NR_list.do?bbsCd=30 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경남투자경제진흥원 | html_table | https://giba.or.kr/fe/bizinfo/bizannounce/NR_list. | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경북경영자총협회 | html_table | http://kbef.or.kr/zbxe/support1 | OK | 25 | 0 | 0 | 0 | 낮음 |  |
| 경북광역자활센터 | html_table | https://gbssc.or.kr/notice/ | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 경북농촌융복합산업지원센터 | html_table | https://www.xn--6-v85e375bg5c4riuk.com/community/0 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경북북부경영자협회 | html_table | http://www.geea.or.kr/bbs/notice | OK | 22 | 0 | 0 | 0 | 낮음 |  |
| 경북신용보증재단 | html_table | https://gbsinbo.co.kr/page/10052/10005.tc | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경북여성정책개발원 | html_table | https://forwoman.or.kr/main/contents.do?a_num=5946 | OK | 11 | 0 | 0 | 0 | 낮음 |  |
| 경북지역인적자원개발위원회 | html_table | http://gbhrd.or.kr/zbxe/?mid=support1 | OK | 23 | 0 | 0 | 0 | 낮음 |  |
| 경북창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gyeongbuk/allim/a | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경북창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gyeongbuk/custom/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경북테크노파크 | html_table | https://gbtp.or.kr/user/board.do?bbsId=BBSMSTR_000 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경북테크노파크 | html_table | https://gbtp.or.kr/user/board.do?bbsId=BBSMSTR_000 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경북테크노파크 | html_table | https://gbtp.or.kr/user/board.do?bbsId=BBSMSTR_000 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 경상북도 중소기업육성자금 GFund | html_table | https://www.gfund.kr/hp/info/M04_L01.do | OK | 5 | 0 | 0 | 0 | 낮음 |  |
| 경상북도경제진흥원 | html_table | https://www.gepa.kr/?page_id=51 | OK | 10 | 5 | 0 | 5 | 낮음 |  |
| 경상북도사회적경제지원센터 | html_table | http://gbse.or.kr/HOME/gbse/sub.htm?nav_code=gbs15 | OK | 13 | 0 | 0 | 0 | 낮음 |  |
| 고양산업진흥원 | html_table | https://www.gipa.or.kr/community/01_1.php | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 공공구매종합정보망 | html_table | https://www.smpp.go.kr/cst/notice/selectNoticeList | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 광주전남지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/gwangju/ex/bbs/List.do? | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 광주경영자총협회 | html_table | http://www.gjef.or.kr/ko/28 | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 광주경제진흥상생일자리재단 | html_table | https://www.gjep.or.kr/cms/bbs/cms.php?dk_cms=comm | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 광주광역자활센터 | html_table | http://www.gjjahwal.or.kr/ko/36 | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 광주사회적경제지원센터 | html_table | https://www.gjsec.kr/bbs/board.php?bo_table=noti&s | OK | 19 | 0 | 2 | 0 | 높음 |  |
| 광주상공회의소 | html_table | https://www.gjcci.or.kr/user/board/lists/board_cd/ | OK | 14 | 0 | 0 | 0 | 낮음 |  |
| 광주신용보증재단 | html_table | https://untact.koreg.or.kr/web/lay1/bbs/S1T19C20/J | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 광주여성가족재단 | html_table | https://www.gjwf.or.kr/open/01 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 광주정보문화산업진흥원 | html_table | https://www.gicon.or.kr/board.es?mid=a10204000000& | OK | 25 | 0 | 0 | 0 | 낮음 |  |
| 광주지역산업진흥원 | html_table | https://gj.riia.or.kr/board/businessAnnouncement | OK | 13 | 0 | 0 | 0 | 낮음 |  |
| 광주지역인적자원개발위원회 | html_table | https://www.gwangjuhrd.or.kr/user2/board/lists/boa | OK | 12 | 0 | 0 | 0 | 낮음 |  |
| 광주창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gwangju/custom/no | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 광주창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/gwangju/service/p | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 광주테크노파크 | html_table | https://www.gjtp.or.kr/home/business.cs?m=8 | OK | 30 | 0 | 0 | 0 | 낮음 |  |
| 광주테크노파크 | html_table | https://www.gjtp.or.kr/home/board/0008.cs?m=14 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 구미전자정보기술원 | html_table | https://geri.re.kr/html/board/list.asp?board_id=bu | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 구조혁신지원사업 통합 플랫폼 | html_table | https://www.kosmes.or.kr/s3/portal/board/BoardList | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 국가교육위원회 | html_table | https://www.ne.go.kr/user/bbs/BD_selectBbsList.do? | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 국가직무능력표준(NCS) | html_table | https://m.ncs.go.kr/th07/bbs_ntc_list.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 국가직무능력표준(NCS) | html_table | https://www.ncs.go.kr/company/ch07/bbs_lib_list.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 국토교통과학기술진흥원 | html_table | https://www.kaia.re.kr/portal/bbs/list/B0000006.do | OK | 10 | 1 | 0 | 1 | 낮음 |  |
| 군포산업진흥원 | html_table | https://gpipa.or.kr/sub05/sub05_01.html | OK | 29 | 0 | 5 | 0 | 높음 |  |
| 군포산업진흥원 | html_table | https://gpipa.or.kr/sub05/sub05_02.html | OK | 30 | 0 | 6 | 0 | 높음 |  |
| 기술보증기금(기보) | html_table | https://www.kibo.or.kr/main/board/boardType01.do | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 기업 SOS | html_table | https://www.giupsos.or.kr/portal/lay1/bbs/S122T158 | OK | 10 | 1 | 0 | 1 | 낮음 |  |
| 기업마당 | html_table | https://www.bizinfo.go.kr/sii/siia/selectSIIA200Vi | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 기업직업훈련지원시스템 | html_table | https://www.hrd4u.or.kr/hrddoctor/web/board/list.d | OK | 14 | 0 | 0 | 0 | 낮음 |  |
| 김포시청 | html_table | https://www.gimpo.go.kr/portal/ntfcPblancList.do?k | OK | 10 | 3 | 0 | 3 | 낮음 |  |
| 김포시청 | html_table | https://www.gimpo.go.kr/portal/selectBbsNttList.do | OK | 12 | 2 | 0 | 2 | 낮음 |  |
| 나라장터 | html_table | https://www.g2b.go.kr/ehelpdesk/R23AB00000134L_01/ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 남북하나재단 | html_table | https://www.koreahana.or.kr/home/kor/board.do?ptSi | OK | 33 | 0 | 33 | 0 | 높음 |  |
| 남양주시청 | html_table | https://www.nyj.go.kr/www/selectEminwonWebList.do? | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 노란우산 경영지원단 | html_table | https://9976.kbiz.or.kr/cnst/information.do?mnSeq= | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 노사발전재단 | html_table | https://www.nosa.or.kr/portal/nosa/FoundNews/bizNo | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 노사발전재단 | html_table | https://www.nosa.or.kr/portal | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 노사발전재단 일터혁신플랫폼 | html_table | https://www.kwpi.or.kr/home/sub?menukey=7311 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 농림수산업자신용보증기금(농신보) | html_table | https://nongshinbo.nonghyup.com/user/indexSub.do?c | OK | 16 | 0 | 0 | 0 | 낮음 |  |
| 농수산식품유통교육원 | html_table | https://edu.at.or.kr/cop/bbs/selectBoardList.do?bb | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 능력개발교육원 | html_table | https://hrdi.koreatech.ac.kr/?m1=page&menu_id=11 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대·중소기업·농어업협력재단 | html_table | https://www.win-win.or.kr/kr/board/notice/boardLis | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대·중소기업·농어업협력재단 | html_table | https://www.win-win.or.kr/kr/board/notice_enter/bo | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구·경북지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/daegu/ex/bbs/List.do?cb | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구경북경제자유구역청 | html_table | https://www.dgfez.go.kr/page.php?mnu_uid=319& | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 대구경북경제자유구역청 | html_table | https://www.dgfez.go.kr/page.php?mnu_uid=321& | OK | 11 | 0 | 11 | 0 | 높음 |  |
| 대구경영자총협회 | html_table | http://www.dgef.or.kr/Home/board/default.asp?v=1&s | OK | 20 | 0 | 20 | 0 | 높음 |  |
| 대구사회적경제지원센터 | html_table | https://dgse.kr/page/cop/bbs/articleList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구신용보증재단 | html_table | https://www.dgsinbo.or.kr/page/10065/10006.tc | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구신용보증재단 | html_table | https://www.dgsinbo.or.kr/page/10066/10160.tc | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구지역인적자원개발위원회 | html_table | https://www.dghrd.or.kr/homeBoard/hpBoardList?tn=h | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구창업허브 DASH | html_table | https://startup.daegu.go.kr/index.do?menu_id=00002 | OK | 7 | 0 | 7 | 0 | 높음 |  |
| 대구창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/daegu/custom/noti | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/daegu/allim/allim | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대구테크노파크 | html_table | https://ttp.org/bbs/BoardControl.do?bbsId=BBSMSTR_ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대전·세종지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/daejeon/ex/bbs/List.do? | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대전사회혁신센터 | html_table | https://www.commonz042.kr/bbs/board.php?bo_table=c | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대전신용보증재단 | html_table | https://www.sinbo.or.kr/sub04_01_01 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 대전일자리경제진흥원 | html_table | https://www.djbea.or.kr/board?menuId=MENU00310&sit | OK | 0 | 0 | 0 | 0 | 낮음 |  |
| 대전지방국세청 | html_table | https://d.nts.go.kr/daejeonnts/na/ntt/selectNttLis | OK | 22 | 0 | 22 | 0 | 높음 |  |
| 대전지역인적자원개발위원회 | html_table | https://djhrd.or.kr/sub0101 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 대전창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/daejeon/custom/no | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대전창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/daejeon/allim/all | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대전충남경영자총협회 | html_table | http://tjcnf.inctcokr.gethompy.com/bbs/board.php?b | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 대전테크노파크 | html_table | https://djtp.or.kr/board.es?mid=a20201000000&bid=0 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 대전테크노파크 | html_table | https://djtp.or.kr/pbanc?mid=a20101000000 | OK | 10 | 0 | 5 | 0 | 높음 |  |
| 데이터바우처 | html_table | https://kdata.or.kr/datavoucher/log/ntt/ptNoticeLi | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 범부처통합연구지원시스템(IRIS) | html_table | https://www.iris.go.kr/contents/retrieveNoticeList | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 부산경영자총협회 | html_table | http://www.bsef.or.kr/03_news/news01.php | OK | 18 | 0 | 1 | 0 | 높음 |  |
| 서울특별시 사회적경제지원센터 | html_table | https://sehub.net/archives/category/alarm/opencat | OK | 18 | 0 | 0 | 0 | 낮음 |  |
| 성남산업진흥원 성남기업지원포털 | html_table | https://portal.snip.or.kr:8443/portal/snip/MainMen | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 세종농촌융복합산업지원센터 | html_table | https://www.xn--6-el4fgqn4mr2dw1q.com/announcement | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 세종일자리경제진흥원 | html_table | https://www.sjepa.or.kr/news-announcement | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 세종창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/sejong/custom/not | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 세종테크노파크 | html_table | https://sjtp.or.kr/bbs/board.php?bo_table=notice01 | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 세종테크노파크 | html_table | https://sjtp.or.kr/bbs/board.php?bo_table=business | OK | 15 | 1 | 0 | 1 | 낮음 |  |
| 소상공인24 | html_table | https://www.sbiz24.kr/#/pbanc | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 소상공인365 | html_table | https://bigdata.sbiz.or.kr/#/sprtBiz | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 소상공인스마트상점 | html_table | https://www.sbiz.or.kr/smst/bbs/list.do?key=211130 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 소상공인시장진흥공단(소진공) | html_table | https://www.semas.or.kr/web/board/webBoardList.kmd | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 소상공인연합회 | html_table | https://www.kfme.or.kr/kf/board/notice.php | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 수원창업지원포털 | html_table | https://s-startup.or.kr/menu-1-1 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 수출지원기반활용사업 | html_table | https://www.exportvoucher.com/portal/board/boardLi | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 스마트공장 사업관리시스템 | smartfactory_api | https://www.smart-factory.kr/usr/bg/ba/ma/bsnsPban | OK | 39 | 5 | 0 | 5 | 낮음 |  |
| 시흥산업진흥원 | html_table | https://www.sida.kr/notification/news.html | OK | 20 | 1 | 0 | 1 | 낮음 |  |
| 신용보증재단중앙회 | html_table | https://www.koreg.or.kr/koreg/na/ntt/selectNttList | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 신용회복위원회 | html_table | https://www.ccrs.or.kr/cms/com/index.do?MENU_ID=84 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 안양산업진흥원 | html_table | https://www.aba.or.kr/bbs/board.do?id=382&menuId=8 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 안양시상권활성화센터 | html_table | https://www.anyang.go.kr/amrc/selectBbsNttList.do? | OK | 12 | 0 | 0 | 0 | 낮음 |  |
| 여성기업 일자리허브 | html_table | https://www.wljarihub.or.kr/wesc/bbs/B0000001/list | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 용인시산업진흥원 | html_table | https://ypa.or.kr/information/businessnotice/ | OK | 27 | 0 | 1 | 0 | 높음 |  |
| 울산신용보증재단 | html_table | https://www.ulsansinbo.co.kr/04_notice/?mcode=0404 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 울산양산경영자총협회 | html_table | http://www.uyef.or.kr/V1/bbs/board.php?bo_table=cu | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 울산일자리경제진흥원 | html_table | https://www.ubpi.or.kr/sub/?mcode=0403010000 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 울산지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/ulsan/ex/bbs/List.do?cb | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 울산지역인적자원개발위원회 | html_table | https://www.ulsanhrd.or.kr/bbs/list.php?board_id=n | OK | 18 | 0 | 0 | 0 | 낮음 |  |
| 울산창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/ulsan/custom/noti | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 울산테크노파크 | html_table | https://www.utp.or.kr/board/board.php?bo_table=sub | OK | 20 | 1 | 0 | 1 | 낮음 |  |
| 울산테크노파크 | html_table | https://platform.utp.or.kr/com/biz_gonggo_all.php | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 원주의료기기산업진흥원 | html_table | https://www.wmit.or.kr/bbs/board.do?bsIdx=710&menu | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 원주의료기기산업진흥원 | html_table | https://www.wmit.or.kr/announce/businessAnnounceLi | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 은평구청 | html_table | https://www.ep.go.kr/www/selectBbsNttList.do?bbsNo | OK | 10 | 1 | 0 | 1 | 낮음 |  |
| 이노비즈협회(사)중소기업기술혁신 | html_table | https://www.innobiz.net/company/company1_list.asp | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 인천경영자총협회 | html_table | https://www.inef.or.kr/news/notice.php | OK | 29 | 0 | 29 | 0 | 높음 |  |
| 인천광역시사회적경제지원센터 | html_table | https://www.insehub.or.kr/bbs/board.php?bo_table=b | OK | 28 | 0 | 12 | 0 | 높음 |  |
| 인천디자인지원센터 | html_table | https://idsc.kr/_NBoard/board.php?bo_table=busines | OK | 37 | 0 | 25 | 0 | 높음 |  |
| 인천디자인지원센터 | html_table | https://idsc.kr/_NBoard/board.php?bo_table=busines | OK | 25 | 0 | 14 | 0 | 높음 |  |
| 인천소상공인종합지원센터 | html_table | https://www.insupport.or.kr/sub/?mcode=0404010000 | OK | 15 | 2 | 0 | 2 | 낮음 |  |
| 인천신용보증재단 | html_table | https://www.icsinbo.or.kr/home/board/brdList.do?me | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/incheon/ex/bbs/List.do? | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천지역인적자원개발위원회 | html_table | https://www.incheonhrd.or.kr/community/notice.asp | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천창업플랫폼 | html_table | http://i-startup.or.kr/04_support/support_1_1 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 인천창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/incheon/custom/no | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 전북창조경제혁신센터 | html_table | https://event.jbci.or.kr/sub/s1_1.html | OK | 2 | 0 | 0 | 0 | 낮음 |  |
| 전북테크노파크 | html_table | https://www.jbtp.or.kr/board/list.jbtp?boardId=BBS | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 전북테크노파크 | html_table | https://www.jbtp.or.kr/board/list.jbtp?boardId=BBS | OK | 26 | 1 | 0 | 1 | 낮음 |  |
| 전북특별자치도 기업관리시스템 | html_table | https://jbcis.jbtp.or.kr/main/menu?qc=935MSRF | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 전북특별자치도 농촌융복합산업 지원 | html_table | https://www.xn--6-482fg5fy8gb6c1vi.com/board/notic | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 전북특별자치도경제통상진흥원 | html_table | https://www.jbba.kr/bbs/board.php?bo_table=sub01_0 | OK | 20 | 0 | 20 | 0 | 높음 |  |
| 전북특별자치도경제통상진흥원 | html_table | https://www.jbba.kr/bbs/board.php?bo_table=sub02_0 | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 전주정보문화산업진흥원 | html_table | https://www.jica.or.kr/2025/inner.php?sMenu=A1000 | OK | 9 | 1 | 0 | 1 | 낮음 |  |
| 전주정보문화산업진흥원 | html_table | https://www.jica.or.kr/2025/inner.php?sMenu=A2000 | OK | 9 | 0 | 0 | 0 | 낮음 |  |
| 전통시장육성재단 | html_table | https://tmdf.or.kr/sub/sub03_01.php | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 정보통신산업진흥원 | html_table | https://www.nipa.kr/home/2-1 | OK | 12 | 0 | 0 | 0 | 낮음 |  |
| 정보통신산업진흥원 | html_table | https://www.nipa.kr/home/2-2 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 정부24 | html_table | https://www.gov.kr/portal/locgovNews?Mcode=11182 | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 정부24 | html_table | https://www.gov.kr/portal/locgovNews?srchTxt=%EC%A | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 정부24 | html_table | https://www.gov.kr/portal/locgovNews?srchTxt=%EC%9 | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 정부24 | html_table | https://www.gov.kr/portal/locgovNews?srchTxt=%EB%A | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 정부24 | html_table | https://www.gov.kr/portal/locgovNews?srchTxt=%EA%B | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 정부24 | html_table | https://www.gov.kr/portal/locgovNews?srchTxt=%ED%8 | OK | 15 | 0 | 15 | 0 | 높음 |  |
| 제주경영자총협회 | html_table | http://jef.or.kr/bbs/board.php?bo_table=1_1_1_1 | OK | 21 | 0 | 21 | 0 | 높음 |  |
| 제주농촌융복합산업지원센터 | html_table | http://www.xn--6-ql4r7skmwc95ai5j.com/skyBoard/lis | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 제주사회적경제지원센터 | html_table | https://jejuhub.org/user/news/support | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 제주산업정보서비스 | html_table | https://jeis.or.kr/suppis/suppbis.ac | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 제주신용보증재단 | html_table | https://www.jcgf.or.kr/bbs/board.php?bo_table=5_1_ | OK | 16 | 0 | 16 | 0 | 높음 |  |
| 제주지역인적자원개발위원회 | html_table | http://www.jejuhrd.or.kr/index.php/contents/commun | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 제주창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/jeju/custom/notic | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 제주테크노파크 | html_table | https://jejutp.or.kr/board/notice?searchType=subje | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 제주특별자치도 경제통상진흥원 | html_table | https://www.jba.or.kr/m/bbs/board.php?bo_table=2_1 | OK | 18 | 0 | 18 | 0 | 높음 |  |
| 제주특별자치도 경제통상진흥원 | html_table | https://www.jba.or.kr/m/bbs/board.php?bo_table=2_4 | OK | 18 | 0 | 18 | 0 | 높음 |  |
| 제주특별자치도사회서비스원 | html_table | https://jeju.pass.or.kr/notice-board | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 중소기업 기술개발사업 종합관리시스템 | html_table | https://www.smtech.go.kr/front/ifg/no/notice01_lis | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 중소기업 기술개발사업 종합관리시스템 | html_table | https://www.smtech.go.kr/front/ifg/no/notice03_lis | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 중소기업 기술보호울타리 | html_table | https://www.ultari.go.kr/site/board/biz/nv_bizNoti | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소기업 기술보호울타리 | html_table | https://www.ultari.go.kr/site/board/expert/recruit | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소기업 혁신플랫폼 | html_table | https://www.mssmiv.com/portal/board/BoardList?bbsI | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소기업기술마켓 | html_table | https://techmarket.kr/noticeList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소기업기술정보진흥원(TIPA) | tipa_html | https://www.tipa.or.kr/s040101/index/page/1 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 중소벤처24 | html_table | https://www.smes.go.kr/main/sportsBsnsPolicy | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소벤처기업부 비즈니스지원단 | html_table | https://www.smes.go.kr/bizlink/board/noticeList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소벤처기업연구원 | html_table | https://www.kosi.re.kr/kosbiWar/front/functionDisp | OK | 20 | 1 | 0 | 1 | 낮음 |  |
| 중소벤처기업연수원 | html_table | https://ssup.kosmes.or.kr/support/notice/0 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 중소상공인희망재단 | html_table | https://www.heemangfdn.or.kr/layout/res/home.php?g | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 중소상공인희망재단 | html_table | https://www.heemangfdn.or.kr/layout/res/home.php?g | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 지역지식재산센터 | html_table | https://pms.ripc.org/www/portal/notice/boardList.d | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 지역지식재산센터 | html_table | https://pms.ripc.org/www/portal/notice/boardList.d | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 지역지식재산센터 | html_table | https://pms.ripc.org/www/portal/notice/boardList.d | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 지역지식재산센터(RIPC) 사업공고 | ripc_api | https://pms.ripc.org/pms/biz/applicant/notice/list | OK | 50 | 0 | 0 | 0 | 낮음 |  |
| 창업기업 확인시스템 | html_table | https://cert.k-startup.go.kr/usr/bbs/selectArticle | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 창업진흥원(창진원) | html_table | https://www.kised.or.kr/misAnnouncement/index.es?m | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 창원산업진흥원 | html_table | https://www.cwip.or.kr/bbs/board.php?bo_table=b050 | OK | 12 | 0 | 12 | 0 | 높음 |  |
| 창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/custom/notice_lis | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 천안과학산업진흥원 | html_table | https://www.cistep.re.kr/zboard/list.do?lmCode=not | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 첨단정보통신융합산업기술원 | html_table | https://iact.or.kr/module/board/board.php?bo_id=no | OK | 22 | 0 | 22 | 0 | 높음 |  |
| 첨단정보통신융합산업기술원 | html_table | https://iact.or.kr/module/board/board.php?bo_id=bu | OK | 19 | 0 | 19 | 0 | 높음 |  |
| 청년인재DB | html_table | https://www.2030db.go.kr/user/ntt/BBS_000000000000 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 청년인재DB | html_table | https://www.2030db.go.kr/user/ntt/BBS_000000000000 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 청년창업사관학교 | html_table | https://start.kosmes.or.kr/yh_bsm080_001.do | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 청년창업사관학교 | html_table | https://start.kosmes.or.kr/yh_not002_001.do | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 축산물품질평가원 | html_table | https://www.ekape.or.kr/board/list.do?menuId=menu1 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 춘천바이오산업진흥원 | html_table | https://www.cbfo.kr/twb_bbs/bbs_list.php?bcd=01_05 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충남경제진흥원 | html_table | https://www.cepa.or.kr/notice/notice.do?pm=6&ms=32 | OK | 10 | 1 | 0 | 1 | 낮음 |  |
| 충남농업6차산업센터 | html_table | https://www.xn--6-6v7en42by2es7i6jc.com/100101/boa | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 충남사회적경제지원센터 | html_table | https://www.cnse.kr/app/board/index?md_id=center_n | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 충남신용보증재단 | html_table | https://www.cnsinbo.co.kr/boardCnts/list.do?boardI | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충남지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/chungnam/ex/bbs/List.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충남창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/chungnam/allim/al | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충남창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/chungnam/custom/n | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충남테크노파크 | html_table | https://www.ctp.or.kr/business/data.do | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 충북경영자총협회 | html_table | http://www.cbef.or.kr/www/brd/list/161595670973793 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충북농촌융복합산업지원센터 | html_table | http://xn--6-482fq5fy8gs7i6jc.com/bbs/board.php?bo | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 충북사회적경제센터 | html_table | http://www.cbse.co/board/blist/notice | OK | 23 | 0 | 23 | 0 | 높음 |  |
| 충북신용보증재단 | html_table | https://www.cbsinbo.or.kr/sub.php?code=123 | OK | 15 | 1 | 0 | 1 | 낮음 |  |
| 충북지방중소벤처기업청 | html_table | https://www.mss.go.kr/site/chungbuk/ex/bbs/List.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충북지역인적자원개발위원회 | html_table | https://www.cjrhrdc.org/board/notice | OK | 20 | 0 | 20 | 0 | 높음 |  |
| 충북창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/chungbuk/custom/n | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 충북테크노파크 | html_table | https://www.cbtp.or.kr/index.php?control=bbs&board | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 충북테크노파크 | html_table | https://www.cbtp.or.kr/index.php?control=bbs&board | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 충북테크노파크 컨택센터 | html_table | https://contact.cbtp.or.kr/index.php?control=bbs&b | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 충청남도 소상공인 지원센터 | html_table | https://sbiz.cepa.or.kr/sosang/notice/notice.do?pm | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 충청남도 소상공인 지원센터 | html_table | https://sbiz.cepa.or.kr/sosang/notice/notice.do?pm | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 충청북도기업진흥원 | html_table | https://www.cba.ne.kr/home/sub.php?menukey=140 | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 충청북도소상공인지원센터 | html_table | https://www.cbsb.kr/home/sub.php?menukey=288 | OK | 13 | 0 | 0 | 0 | 낮음 |  |
| 카페: 경북도(경영 기술 지도사 컨설…) | html_table | https://cafe.naver.com/f-e/cafes/30454029/menus/4? | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 카페: 고을스페이스 | html_table | https://cafe.naver.com/f-e/cafes/30864795/menus/16 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 카페: 지도사랑(한국경영기술지도사) | html_table | https://cafe.naver.com/f-e/cafes/30044569/menus/26 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 카페: 키노프 경영지도사 | html_table | https://cafe.naver.com/f-e/cafes/23509311/menus/40 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 클린아이 지방공공기관통합공시 | html_table | https://www.cleaneye.go.kr/user/noticeBoardList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 파주시청 | html_table | https://www.paju.go.kr/user/board/BD_board.list.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 판판대로 | html_table | https://fanfandaero.kr/portal/readUcenterNtcBbs.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 판판대로 | html_table | https://fanfandaero.kr/portal/preSprtBizPbanc.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 평택산업진흥원 | html_table | https://www.pipabiz.or.kr/web/contents/notice.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 포항창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/pohang/allim/alli | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 포항창조경제혁신센터 | html_table | https://ccei.creativekorea.or.kr/pohang/custom/not | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 포항테크노파크 | html_table | https://www.ptp.or.kr/main/board/index.do?menu_idx | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 포항테크노파크 | html_table | https://www.ptp.or.kr/main/board/index.do?menu_idx | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 핀테크 포털 - 한국핀테크지원센터 | html_table | https://fintech.or.kr/web/board/boardContentsListP | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 하이브레인넷 | html_table | https://www.hibrain.net/research/researches/34/rec | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국건강가정진흥원 | html_table | https://www.kihf.or.kr/web/lay1/bbs/S1T838C97/A/3/ | OK | 11 | 0 | 0 | 0 | 낮음 |  |
| 한국경영기술지도사회 | html_table | https://www.kmtca.or.kr/?p=23 | OK | 11 | 0 | 0 | 0 | 낮음 |  |
| 한국경영기술지도사회 | html_table | https://www.kmtca.or.kr/?p=28 | OK | 11 | 1 | 0 | 1 | 낮음 |  |
| 한국경영기술지도사회 | html_table | https://www.kmtca.or.kr/?p=128 | OK | 17 | 0 | 0 | 0 | 낮음 |  |
| 한국경영자총협회 | html_table | https://www.kefplaza.com/web/pages/gc75749b.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국경영혁신중소기업협회 | html_table | https://mainbiz.or.kr/notice/notice.asp?smen=1 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국경영혁신중소기업협회 | html_table | https://mainbiz.or.kr/notice/company.asp?smen=2 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국경영혁신중소기업협회 | html_table | https://mainbiz.or.kr/notice/library.asp?smen=8 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국고용노동교육원 | html_table | https://www.keli.kr/home/cmmn/bbs/228/list.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국농업기술진흥원 | html_table | https://www.koat.or.kr/board/business/list.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국능률협회(KMA) | html_table | https://www.kma.or.kr/usrs/tutor/tutorForm.do | OK | 86 | 0 | 86 | 0 | 높음 |  |
| 한국능률협회(KMA) | html_table | https://kma.or.kr/kr/usrs/eduRegMgmt/eduRegMgmtFor | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국능률협회컨설팅(KMAC) | html_table | https://kmac.recruiter.co.kr/career/Notice | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국데이터산업진흥원 | html_table | https://www.kdata.or.kr/kr/board/notice_01/boardLi | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국무역보험공사 | html_table | https://www.ksure.or.kr/rh-kr/bbs/i-412/list.do | OK | 114 | 0 | 114 | 0 | 높음 |  |
| 한국무역협회 | html_table | https://www.kita.net/board/notice/noticeList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국문화산업협회 | html_table | http://www.kcia.or.kr/bbs/board.php?bo_table=notic | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국발명진흥회 | html_table | https://www.kipa.org/kipa/notice/kw_0403_01.jsp | OK | 10 | 2 | 0 | 2 | 낮음 |  |
| 한국발명진흥회 | html_table | https://www.kipa.org/kipa/ip004/kw_apquestion_0501 | OK | 10 | 2 | 0 | 2 | 낮음 |  |
| 한국보건산업진흥원 | html_table | https://www.khidi.or.kr/board?menuId=MENU00099 | OK | 11 | 0 | 0 | 0 | 낮음 |  |
| 한국사회적기업진흥원 | html_table | https://www.socialenterprise.or.kr/homepage/bbs/bo | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국산업기술기획평가원(KEIT) | html_table | https://www.keit.re.kr/board.es?mid=a10301010000&b | OK | 1 | 0 | 0 | 0 | 낮음 |  |
| 한국산업기술진흥원(KIAT) | html_table | https://www.kiat.or.kr/front/board/boardContentsLi | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국산업기술진흥원(KIAT) | html_table | https://www.kiat.or.kr/front/board/boardContentsLi | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국산업기술진흥협회 | html_table | https://www.koita.or.kr/board/commBoardNoticeList. | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국산업단지공단 | html_table | https://www.kicox.or.kr/user/bbs/BD_selectBbsList. | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국산업인력공단(HRDK) | html_table | https://www.hrdkorea.or.kr/3/1/1 | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 한국산업인력공단(HRDK) | html_table | https://hrms.hrdkorea.or.kr/hrpRcrt/hrpRcrtPbanc.d | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국상생지원협회 | html_table | https://www.lmca.or.kr/22 | OK | 6 | 0 | 6 | 0 | 높음 |  |
| 한국생산성본부 | html_table | https://www.kpc.or.kr/PTWCC002_board.index.do?nbno | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국생산성본부 | html_table | https://www.kpc.or.kr/PTWCC002_board.index2.do?typ | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국엔젤투자협회 | html_table | https://home.kban.or.kr/assoc/intrcn/noticeList | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국양성평등교육진흥원 | html_table | https://www.kigepe.or.kr/user/cop/bbs/selectBoardL | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국어촌어항공단 | html_table | https://www.fipa.or.kr/fipa/bbs/i-167/list.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국어촌어항공단 | html_table | https://www.fipa.or.kr/fipa/bbs/i-326/list.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국에너지공단 | html_table | https://www.energy.or.kr/front/board/List2.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국에너지공단 신재생에너지센터 | html_table | https://www.knrec.or.kr/biz/pds/notice/list.do | OK | 24 | 0 | 0 | 0 | 낮음 |  |
| 한국여성발명협회 | html_table | https://www.inventor.or.kr/bbs/board.php?bo_table= | OK | 15 | 0 | 0 | 0 | 낮음 |  |
| 한국인터넷진흥원(KISA) | html_table | https://www.kisa.or.kr/401 | OK | 10 | 3 | 0 | 3 | 낮음 |  |
| 한국중소벤처기업유통원 | html_table | https://www.kodma.or.kr/bbs/list.do?key=2409240028 | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국콘텐츠진흥원 | html_table | https://www.kocca.kr/kocca/bbs/list/B0000137.do?me | OK | 10 | 4 | 0 | 4 | 낮음 |  |
| 한국콘텐츠진흥원 | html_table | https://www.kocca.kr/kocca/pims/list.do?menuNo=204 | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 한국테크노파크진흥회 | html_table | https://www.technopark.kr/businessboard | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 한국표준협회(KSA) | html_table | https://www.ksa.or.kr/ksa_kr/5217/subview.do | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 한국표준협회(KSA) | html_table | https://ksa.or.kr/bbs/ksa_kr/1021/artclList.do?lay | OK | 10 | 0 | 10 | 0 | 높음 |  |
| 한국환경공단 | html_table | https://www.keco.or.kr/web/lay1/bbs/S1T10C108/A/18 | OK | 10 | 5 | 0 | 5 | 낮음 |  |
| 한성대학교 | html_table | https://hansung.ac.kr/kscon/6279/subview.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
| 홍천군청 | html_table | https://www.hongcheon.go.kr/www/selectBbsNttList.d | OK | 10 | 0 | 0 | 0 | 낮음 |  |
| 화성산업진흥원 | html_table | https://www.hsbiz.or.kr/bbs/BBSMSTR_000000000040/l | OK | 5 | 1 | 0 | 1 | 낮음 |  |
| 화성시인재육성재단 | html_table | https://www.hstree.org/news/notice.do | OK | 12 | 0 | 0 | 0 | 낮음 |  |
| 희망리턴패키지 | html_table | https://www.sbiz.or.kr/nhrp/pblanc/pblancList.do | FAIL | 0 | 0 | 0 | 0 | 낮음 | disabled_in_config |
