"""수출지원 모니터링 관리 대시보드 v6
실행: streamlit run streamlit_app.py
"""
import hashlib, json, subprocess, sys
from pathlib import Path
import streamlit as st

# ── 경로 ─────────────────────────────────────────────────────────────────────
SITES_PATH    = Path("sites.json")
GROUPS_PATH   = Path("groups.json")
SETTINGS_PATH = Path("settings.json")
SEEN_IDS_PATH = Path("seen_ids.json")

# ── 상수 ─────────────────────────────────────────────────────────────────────
SITE_TYPES = {
    "bizinfo_api":   "기업마당 API (통합포털)",
    "myfair_html":   "마이페어 HTML (통합포털)",
    "kstartup_html": "K-Startup HTML (주관기관급)",
    "kita_html":     "한국무역협회 KITA (전용)",
    "iris_api":      "IRIS 범부처통합연구지원 (전용 API)",
    "smtech_html":   "SMTECH 중소기업기술개발 (전용)",
    "kocca_pims":    "KOCCA 사업공고 (전용)",
    "kocca_bbs":     "KOCCA 금융공고 (전용)",
    "gtp_html":      "경기TP (전용)",
    "gsp_html":      "경기스타트업플랫폼 (전용)",
    "ccei_html":     "창조경제혁신센터 (전용)",
    "html_table":    "신규 — HTML 테이블",
    "html_card":     "신규 — HTML 카드",
}
ALL_SUPPORT_TYPES = ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"]
SUPPORT_ICONS     = {"지원금/바우처": "💰", "컨설팅·교육·상담": "🎓", "투자": "📈", "그외": "📋"}
SUPPORT_DESC      = {
    "지원금/바우처":   "바우처·보조금·참가비·자금지원 등",
    "컨설팅·교육·상담": "컨설팅·멘토링·교육·세미나 등",
    "투자":           "엔젤·VC·시드투자 등",
    "그외":           "위 3개 미해당 공고",
}
KNOWN_REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
                 "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default

def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def new_group_id() -> str:
    import time
    return f"grp_{int(time.time())}"


# ── 초기화 ───────────────────────────────────────────────────────────────────
def init_defaults() -> None:
    if not SITES_PATH.exists():
        save_json(SITES_PATH, [
            {"id": "bizinfo",   "name": "기업마당",  "type": "bizinfo_api",
             "url": "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do",
             "enabled": True, "is_aggregator": True, "note": "통합포털"},
            {"id": "myfair",   "name": "마이페어",  "type": "myfair_html",
             "url": "https://myfair.co/support-program-list",
             "enabled": True, "is_aggregator": True, "note": "해외전시회 통합포털"},
            {"id": "kstartup", "name": "K-Startup", "type": "kstartup_html",
             "url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do",
             "enabled": True, "is_aggregator": False, "note": "창업지원포털"},
        ])
    if not GROUPS_PATH.exists():
        save_json(GROUPS_PATH, [{
            "id": "grp_default", "name": "인천 화장품 수출팀", "active": True,
            "regions": ["인천"],
            "keywords": {"logic": "OR", "keywords": ["화장품", "뷰티", "해외전시회", "수출지원"]},
            "support_types": ["지원금/바우처", "컨설팅·교육·상담", "투자", "그외"],
            "recipients": ["ekth3691@gmail.com"],
        }])
    if not SETTINGS_PATH.exists():
        save_json(SETTINGS_PATH, {
            "date_filter_enabled": True, "days_back": 1,
            "raw_all_enabled": True, "raw_all_recipients": ["ekth3691@gmail.com"],
        })

init_defaults()

# ── 앱 ───────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="수출지원 모니터링", page_icon="📡", layout="wide")
st.title("📡 수출지원 모니터링 관리")

tab_sites, tab_groups, tab_settings, tab_run = st.tabs(
    ["📡 소스 관리", "👥 그룹 관리", "⚙️ 설정", "▶ 실행"]
)


# ══════════════════════════════════════════════════════════════════
# TAB 1 — 소스 관리
# ══════════════════════════════════════════════════════════════════
with tab_sites:
    sites: list[dict] = load_json(SITES_PATH, [])
    st.subheader(f"등록된 소스 ({len(sites)}개)")

    for i, site in enumerate(sites):
        icon = "✅" if site.get("enabled") else "❌"
        agg  = "🔀 통합포털" if site.get("is_aggregator") else "🏢 주관기관"
        with st.expander(f"{icon} {site['name']}  ·  {agg}", expanded=False):
            c1, c2 = st.columns([3, 1])
            with c1:
                n_name = st.text_input("사이트명", value=site["name"], key=f"s_name_{i}")
                n_url  = st.text_input("URL",       value=site.get("url",""), key=f"s_url_{i}")
                n_note = st.text_input("메모",       value=site.get("note",""), key=f"s_note_{i}")
            with c2:
                type_keys = list(SITE_TYPES.keys())
                cur_idx   = type_keys.index(site["type"]) if site["type"] in type_keys else 0
                n_type    = st.selectbox("타입", type_keys, index=cur_idx,
                                         format_func=lambda x: SITE_TYPES[x], key=f"s_type_{i}")
                n_on      = st.checkbox("활성화", value=site.get("enabled", True), key=f"s_on_{i}")
                n_agg     = st.checkbox("통합포털 (중복시 후순위)",
                                        value=site.get("is_aggregator", False), key=f"s_agg_{i}")
                sc1, sc2 = st.columns(2)
                with sc1:
                    if st.button("💾", key=f"s_save_{i}", use_container_width=True):
                        sites[i] = {**site, "name": n_name, "url": n_url, "note": n_note,
                                    "type": n_type, "enabled": n_on, "is_aggregator": n_agg}
                        save_json(SITES_PATH, sites); st.success("저장"); st.rerun()
                with sc2:
                    if st.button("🗑", key=f"s_del_{i}", use_container_width=True):
                        sites.pop(i); save_json(SITES_PATH, sites); st.rerun()

    st.divider()
    st.subheader("➕ 소스 추가")
    st.caption("URL 입력 → 자동 분석 → 사이트명 입력 → 추가")

    url_in = st.text_input("공고 목록 URL", placeholder="https://example.go.kr/list", key="new_url")
    if st.button("🔍 자동 분석", disabled=not url_in.strip()):
        with st.spinner("분석 중..."):
            import httpx
            from bs4 import BeautifulSoup as BS
            headers = {"User-Agent": "Mozilla/5.0"}
            candidates = [
                ("HTML 테이블", "html_table", "table tbody tr",
                 lambda el: el.select_one("td a") or el.select_one("td")),
                ("HTML 카드",   "html_card",  "ul li",
                 lambda el: el.select_one("a") or el),
                ("HTML 카드",   "html_card",  ".notice",
                 lambda el: el.select_one("a") or el),
                ("HTML 카드",   "html_card",  ".board-list li",
                 lambda el: el.select_one("a") or el),
            ]
            try:
                with httpx.Client(timeout=15, headers=headers, follow_redirects=True) as c:
                    r = c.get(url_in.strip()); r.raise_for_status()
                    soup = BS(r.text, "html.parser")
                best, best_cnt = None, 0
                for label, stype, sel, fn in candidates:
                    valid = [fn(row).get_text(strip=True)[:60]
                             for row in soup.select(sel)
                             if len((fn(row).get_text(strip=True) if fn(row) else "")) >= 10]
                    if len(valid) > best_cnt:
                        best_cnt = len(valid)
                        best = {"label": label, "type": stype, "sel": sel, "preview": valid[:5]}
                if best and best_cnt >= 2:
                    st.session_state["detected"] = {"status": "ok", **best, "count": best_cnt}
                else:
                    st.session_state["detected"] = {"status": "no_list"}
            except Exception as e:
                st.session_state["detected"] = {"status": "error", "message": str(e)}

    if "detected" in st.session_state:
        det = st.session_state["detected"]
        if det["status"] == "error":
            st.error(f"❌ 접속 실패: {det['message']}")
        elif det["status"] == "ok":
            st.success(f"✅ {det['label']} 구조 — 공고 {det['count']}개 발견")
            with st.expander("미리보기", expanded=True):
                for row in det["preview"]: st.markdown(f"- {row}")
            c1, c2, c3 = st.columns(3)
            with c1: nm = st.text_input("사이트명 *", key="confirm_name")
            with c2: nt = st.text_input("메모", key="confirm_note")
            with c3: na = st.checkbox("통합포털 여부", value=False, key="confirm_agg")
            if st.button("➕ 추가하기", type="primary", disabled=not nm.strip()):
                new_id = f"custom_{hashlib.sha256(url_in.encode()).hexdigest()[:8]}"
                sites.append({"id": new_id, "name": nm.strip(), "type": det["type"],
                              "url": url_in.strip(), "note": nt.strip(), "enabled": True,
                              "is_aggregator": na, "selectors": {"row": det["sel"]}})
                save_json(SITES_PATH, sites)
                del st.session_state["detected"]; st.success("추가 완료!"); st.rerun()
        else:
            st.warning("⚠️ 공고 목록을 자동으로 찾지 못했습니다. URL을 다시 확인하거나 Claude에 문의하세요.")

    with st.expander("ℹ️ 통합포털 vs 주관기관 차이"):
        st.markdown("""
- **🏢 주관기관**: NIPA, KOTRA, 중진공 등 실제 공고를 내는 기관 사이트 → **중복 시 우선 유지**
- **🔀 통합포털**: 기업마당, 마이페어처럼 다른 곳 공고를 모아서 보여주는 사이트 → **중복 시 제거**
        """)


# ══════════════════════════════════════════════════════════════════
# TAB 2 — 그룹 관리
# ══════════════════════════════════════════════════════════════════
with tab_groups:
    groups: list[dict] = load_json(GROUPS_PATH, [])
    st.subheader(f"등록된 그룹 ({len(groups)}개)")
    st.caption("그룹 = 조건(지역+키워드+지원유형) + 수신자. 그룹마다 별도 메일 발송.")

    for i, grp in enumerate(groups):
        icon = "✅" if grp.get("active") else "❌"
        rgns = ", ".join(grp.get("regions", [])) or "전국"
        with st.expander(f"{icon} {grp['name']}  ·  지역: {rgns}", expanded=False):

            # 기본 정보
            g1, g2 = st.columns([3, 1])
            with g1:
                g_name = st.text_input("그룹명", value=grp["name"], key=f"g_name_{i}")
            with g2:
                g_active = st.checkbox("활성화", value=grp.get("active", True), key=f"g_on_{i}")

            st.markdown("**📍 지역 설정**")
            st.caption("선택한 지역 + 전국 공고만 수신. 미선택 시 전체 수신.")
            g_regions = st.multiselect("지역 선택", KNOWN_REGIONS,
                                        default=grp.get("regions", []), key=f"g_reg_{i}")

            st.markdown("**🔑 키워드 조건**")
            kw_cfg = grp.get("keywords", {"logic": "OR", "keywords": []})
            gk1, gk2 = st.columns([1, 3])
            with gk1:
                g_logic = st.radio("조건", ["OR", "AND"], key=f"g_logic_{i}",
                                    index=0 if kw_cfg.get("logic","OR") == "OR" else 1,
                                    horizontal=True)
            with gk2:
                st.caption("OR: 하나라도 포함  |  AND: 전부 포함")

            kw_list = kw_cfg.get("keywords", [])
            # 키워드 태그 표시 + 삭제
            kw_del = None
            if kw_list:
                cols = st.columns(min(len(kw_list), 5))
                for j, kw in enumerate(kw_list):
                    with cols[j % 5]:
                        if st.button(f"❌ {kw}", key=f"g_kw_del_{i}_{j}", use_container_width=True):
                            kw_del = kw
            if kw_del:
                kw_list.remove(kw_del)
                grp["keywords"] = {"logic": g_logic, "keywords": kw_list}
                save_json(GROUPS_PATH, groups); st.rerun()

            gka1, gka2 = st.columns([3, 1])
            with gka1:
                new_kw = st.text_input("키워드 추가", placeholder="예: 화장품", key=f"g_kw_add_{i}",
                                        label_visibility="collapsed")
            with gka2:
                if st.button("➕", key=f"g_kw_btn_{i}", use_container_width=True,
                              disabled=not new_kw.strip()):
                    if new_kw.strip() not in kw_list:
                        kw_list.append(new_kw.strip())
                        grp["keywords"] = {"logic": g_logic, "keywords": kw_list}
                        save_json(GROUPS_PATH, groups); st.rerun()

            st.markdown("**📂 지원유형**")
            g_stypes = []
            scols = st.columns(4)
            for j, stype in enumerate(ALL_SUPPORT_TYPES):
                with scols[j]:
                    checked = st.checkbox(
                        f"{SUPPORT_ICONS[stype]} {stype}",
                        value=stype in grp.get("support_types", ALL_SUPPORT_TYPES),
                        key=f"g_st_{i}_{j}",
                        help=SUPPORT_DESC[stype],
                    )
                    if checked: g_stypes.append(stype)

            st.markdown("**📧 수신자 이메일**")
            recip_text = st.text_area(
                "이메일 (한 줄에 하나씩)",
                value="\n".join(grp.get("recipients", [])),
                height=100, key=f"g_recip_{i}",
                label_visibility="collapsed",
            )

            # 저장 / 삭제
            bs1, bs2 = st.columns([1, 1])
            with bs1:
                if st.button("💾 그룹 저장", key=f"g_save_{i}", use_container_width=True):
                    groups[i] = {
                        **grp,
                        "name": g_name, "active": g_active,
                        "regions": g_regions,
                        "keywords": {"logic": g_logic, "keywords": kw_list},
                        "support_types": g_stypes,
                        "recipients": [e.strip() for e in recip_text.splitlines() if e.strip()],
                    }
                    save_json(GROUPS_PATH, groups); st.success("저장 완료"); st.rerun()
            with bs2:
                if st.button("🗑 그룹 삭제", key=f"g_del_{i}", use_container_width=True):
                    groups.pop(i); save_json(GROUPS_PATH, groups); st.rerun()

    # ── 그룹 추가 ─────────────────────────────────────────────────
    st.divider()
    st.subheader("➕ 새 그룹 추가")
    with st.form("add_group", clear_on_submit=True):
        ng1, ng2 = st.columns(2)
        with ng1:
            ng_name = st.text_input("그룹명 *", placeholder="예: 경기 제조업 수출팀")
            ng_regions = st.multiselect("지역", KNOWN_REGIONS)
        with ng2:
            ng_logic = st.radio("키워드 조건", ["OR", "AND"], horizontal=True)
            ng_kws   = st.text_input("키워드 (쉼표 구분)", placeholder="화장품, 뷰티, 수출")
            ng_email = st.text_input("수신자 이메일 *", placeholder="example@gmail.com")
        ng_stypes = st.multiselect("지원유형", ALL_SUPPORT_TYPES, default=ALL_SUPPORT_TYPES)
        if st.form_submit_button("그룹 추가", use_container_width=True):
            if not ng_name.strip() or not ng_email.strip():
                st.error("그룹명과 이메일은 필수입니다.")
            else:
                kws = [k.strip() for k in ng_kws.split(",") if k.strip()]
                groups.append({
                    "id": new_group_id(), "name": ng_name.strip(), "active": True,
                    "regions": ng_regions,
                    "keywords": {"logic": ng_logic, "keywords": kws},
                    "support_types": ng_stypes or ALL_SUPPORT_TYPES,
                    "recipients": [ng_email.strip()],
                })
                save_json(GROUPS_PATH, groups); st.success(f"'{ng_name}' 추가 완료!"); st.rerun()

    with st.expander("💡 그룹 설정 안내"):
        st.markdown("""
**그룹 = 조건 묶음 + 수신자**

각 그룹은 독립적으로 동작하며, 조건에 맞는 공고를 해당 수신자에게 발송합니다.

| 조건 | 설명 |
|------|------|
| **지역** | 선택 지역 + "전국" 공고 수신. 미선택 시 모든 공고 |
| **키워드(OR)** | 키워드 중 하나라도 포함된 공고 |
| **키워드(AND)** | 키워드 전부 포함된 공고만 (엄격) |
| **지원유형** | 체크된 유형의 공고만 포함 |

→ 예: "인천 화장품팀" = 지역:인천 + 키워드:화장품/뷰티(OR) + 유형:지원금/컨설팅
        """)


# ══════════════════════════════════════════════════════════════════
# TAB 3 — 설정
# ══════════════════════════════════════════════════════════════════
with tab_settings:
    settings: dict = load_json(SETTINGS_PATH, {})
    st.subheader("⚙️ 전역 설정")

    st.markdown("**📅 날짜 필터 (D-1 공고만)**")
    col_df1, col_df2 = st.columns([1, 2])
    with col_df1:
        df_on  = st.checkbox("활성화", value=settings.get("date_filter_enabled", True), key="df_on")
        days_b = st.number_input("며칠 전 공고", min_value=1, max_value=7,
                                  value=settings.get("days_back", 1), key="days_back")
    with col_df2:
        st.info(f"현재 설정: 메일 발송일 기준 **{days_b}일 전** 공고만 수신\n\n"
                "⚠️ 날짜 정보가 없는 공고는 예외적으로 포함됩니다.")

    st.divider()
    st.markdown("**📧 원본전체 메일**")
    st.caption("필터링 없이 수집된 모든 공고를 받을 주소입니다.")
    raw_on = st.checkbox("원본전체 메일 발송", value=settings.get("raw_all_enabled", True))
    raw_emails = st.text_area("수신자 (한 줄에 하나씩)",
                               value="\n".join(settings.get("raw_all_recipients", [])),
                               height=100, disabled=not raw_on)

    if st.button("💾 설정 저장", type="primary"):
        new_settings = {
            "date_filter_enabled": df_on,
            "days_back": int(days_b),
            "raw_all_enabled": raw_on,
            "raw_all_recipients": [e.strip() for e in raw_emails.splitlines() if e.strip()],
        }
        save_json(SETTINGS_PATH, new_settings)
        st.success("설정 저장 완료!")


# ══════════════════════════════════════════════════════════════════
# TAB 4 — 실행
# ══════════════════════════════════════════════════════════════════
with tab_run:
    sites_now    = load_json(SITES_PATH, [])
    groups_now   = load_json(GROUPS_PATH, [])
    settings_now = load_json(SETTINGS_PATH, {})

    active_sites  = [s for s in sites_now  if s.get("enabled")]
    active_groups = [g for g in groups_now if g.get("active")]

    # 현황 요약
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("활성 소스",  len(active_sites),  f"전체 {len(sites_now)}개")
    c2.metric("활성 그룹",  len(active_groups), f"전체 {len(groups_now)}개")
    c3.metric("날짜필터",   "ON" if settings_now.get("date_filter_enabled") else "OFF",
              f"D-{settings_now.get('days_back', 1)}")
    seen_cnt = len(load_json(SEEN_IDS_PATH, []))
    c4.metric("중복방지 DB", f"{seen_cnt}건")

    st.divider()

    # 그룹별 설정 요약
    st.markdown("**활성 그룹 요약**")
    for g in active_groups:
        kw = g.get("keywords", {})
        rgn = ", ".join(g.get("regions", [])) or "전국"
        kws = f"{kw.get('logic','OR')}: {', '.join(kw.get('keywords',[])[:3])}"
        st.markdown(f"- **{g['name']}** | 지역: {rgn} | 키워드 {kws} | "
                    f"수신: {', '.join(g.get('recipients', []))}")

    st.divider()
    st.subheader("▶ 지금 실행")

    if not active_sites:
        st.error("활성 소스가 없습니다.")
    elif not active_groups and not settings_now.get("raw_all_recipients"):
        st.error("수신자가 없습니다. 그룹 또는 원본전체 수신자를 설정하세요.")
    else:
        if st.button("▶ 모니터링 실행", type="primary", use_container_width=True):
            with st.spinner("실행 중... (수십 초 소요)"):
                result = subprocess.run(
                    [sys.executable, "monitor.py"],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )
            if result.returncode == 0:
                st.success("✅ 실행 완료!")
            else:
                st.error(f"❌ 오류 발생 (종료코드 {result.returncode})")
            st.subheader("실행 로그")
            log_out = (result.stdout + result.stderr).strip()
            st.code(log_out or "(출력 없음)", language="text")
