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

  return (
    <div>
      <header className="page-header page-header-row">
        <div>
          <h1 className="page-title">사이트 목록</h1>
          <p className="page-desc">
            GitHub <code>sites.json</code> 기준 · 활성 {active} / 전체 {sites.length}
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

      {sites.slice(0, 80).map((s) => (
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
        </div>
      ))}

      {sites.length > 80 && (
        <p className="stat">… 외 {sites.length - 80}건 (UI 표시 제한)</p>
      )}
    </div>
  );
}
