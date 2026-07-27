"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Site = {
  id: string;
  name: string;
  url: string;
  type: string;
  enabled: boolean;
  note?: string;
};

export default function SitesPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error || "load failed");
        setSites(d.sites || []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const active = sites.filter((s) => s.enabled !== false).length;
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = normalizedQuery
    ? sites.filter((site) =>
        [site.id, site.name, site.url, site.type].some((value) =>
          String(value || "").toLowerCase().includes(normalizedQuery),
        ),
      )
    : sites;

  return (
    <div>
      <header className="page-header page-header-row">
        <div>
          <h1 className="page-title">사이트 목록</h1>
          <p className="page-desc">
            GitHub <code>config/sites.json</code> 기준 · 활성 {active} / 전체 {sites.length}
          </p>
        </div>
        <Link className="btn btn-primary" href="/sites/add">
          ＋ 사이트 추가
        </Link>
      </header>

      {error && <p className="error">{error}</p>}
      {loading && !error && <div className="empty">불러오는 중…</div>}
      {!loading && !error && sites.length === 0 && (
        <div className="empty">등록된 사이트가 없습니다.</div>
      )}

      {!loading && sites.length ? (
        <div className="field card-tight">
          <label className="label" htmlFor="site-search">
            사이트 검색
          </label>
          <input
            id="site-search"
            className="input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="이름, ID, URL, 수집 방식"
          />
          <p className="hint">
            검색 결과 {filtered.length}건 · 모든 사이트는 검색 후 편집할 수 있습니다.
          </p>
        </div>
      ) : null}

      {!loading && sites.length > 0 && filtered.length === 0 ? (
        <div className="empty">검색 결과가 없습니다.</div>
      ) : null}

      {filtered.slice(0, 80).map((s) => (
        <div key={s.id} className="site-row">
          <div className="site-main">
            <div className="site-name">
              {s.name}
              <span className="tag">{s.type}</span>
            </div>
            <div className="site-url" title={s.url}>
              {s.url}
            </div>
          </div>
          <span className={s.enabled !== false ? "badge badge-green" : "badge badge-gray"}>
              {s.enabled !== false ? "활성" : "비활성"}
          </span>
          <Link className="btn btn-secondary btn-small" href={`/sites/${encodeURIComponent(s.id)}/edit`}>
            편집
          </Link>
        </div>
      ))}

      {filtered.length > 80 && (
        <p className="stat">… 외 {filtered.length - 80}건 (검색어로 범위를 좁혀 주세요)</p>
      )}
    </div>
  );
}
