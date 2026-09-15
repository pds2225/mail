"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type ConfigPayload = {
  ok?: boolean;
  counts?: { sites?: number; groups?: number };
  sites?: { enabled?: boolean }[];
  groups?: { active?: boolean }[];
  settings?: Record<string, unknown>;
};

export default function HomePage() {
  const [data, setData] = useState<ConfigPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.json())
      .then((payload) => {
        if (!payload.ok) throw new Error(payload.error || "설정을 불러오지 못했습니다.");
        setData(payload);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const metrics = useMemo(() => {
    const sites = data?.sites || [];
    const groups = data?.groups || [];
    const settings = data?.settings || {};
    return {
      activeSites: sites.filter((site) => site.enabled !== false).length,
      allSites: data?.counts?.sites ?? sites.length,
      activeGroups: groups.filter((group) => group.active !== false).length,
      allGroups: data?.counts?.groups ?? groups.length,
      dateFilter: settings.date_filter_enabled === false ? "OFF" : `D-${String(settings.days_back ?? 3)}`,
      unknownLimit: Number(settings.region_unknown_mail_limit ?? 10),
    };
  }, [data]);

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">정부지원사업 메일링</h1>
        <p className="page-desc">수집 소스, 추천 조건, 실행, 공고 검수를 모바일에서 한곳에서 관리합니다.</p>
      </header>

      {error ? <p className="error">{error}</p> : null}

      <section className="dashboard-grid" aria-label="운영 현황">
        <div className="metric-card">
          <span className="metric-label">활성 소스</span>
          <strong className="metric-value">{data ? metrics.activeSites : "–"}</strong>
          <span className="metric-sub">전체 {data ? metrics.allSites : "–"}개</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">활성 그룹</span>
          <strong className="metric-value">{data ? metrics.activeGroups : "–"}</strong>
          <span className="metric-sub">전체 {data ? metrics.allGroups : "–"}개</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">날짜 필터</span>
          <strong className="metric-value">{data ? metrics.dateFilter : "–"}</strong>
          <span className="metric-sub">최근 공고 우선</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">지역 확인</span>
          <strong className="metric-value">{data ? `${metrics.unknownLimit}건` : "–"}</strong>
          <span className="metric-sub">메일 표시 상한</span>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">바로 하기</h2>
        <div className="quick-grid">
          <Link className="quick-action" href="/sites">
            <strong>소스 관리</strong>
            <span>사이트 추가·수정·활성화</span>
          </Link>
          <Link className="quick-action" href="/groups">
            <strong>그룹 관리</strong>
            <span>지역·포함·제외 키워드 수정</span>
          </Link>
          <Link className="quick-action" href="/settings">
            <strong>설정</strong>
            <span>날짜·지역미상 표시 기준</span>
          </Link>
          <Link className="quick-action" href="/run">
            <strong>미리보기 실행</strong>
            <span>실제 발송 없이 결과 확인</span>
          </Link>
          <Link className="quick-action" href="/review">
            <strong>공고 검수</strong>
            <span>제목을 보고 O / X 판정</span>
          </Link>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">운영 원칙</h2>
        <ul>
          <li>웹 기본 실행은 미리보기이며 실제 메일을 보내지 않습니다.</li>
          <li>수신자 개인정보는 공개 설정 화면에서 직접 노출하지 않습니다.</li>
          <li>저장 시 기존 고급 설정을 유지하고 화면에서 수정한 값만 변경합니다.</li>
        </ul>
      </section>
    </div>
  );
}
