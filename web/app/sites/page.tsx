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

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) throw new Error(d.error || "load failed");
        setSites(d.sites || []);
      })
      .catch((e) => setError(e.message));
  }, []);

  const active = sites.filter((s) => s.enabled !== false).length;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>사이트 목록</h1>
        <Link className="btn btn-primary" href="/sites/add">
          ＋ 사이트 추가
        </Link>
      </div>
      <p style={{ color: "#64748b" }}>
        GitHub <code>sites.json</code> 기준 · 활성 {active} / 전체 {sites.length}
      </p>
      {error && <p className="error">{error}</p>}
      {sites.slice(0, 80).map((s) => (
        <div key={s.id} className="card" style={{ padding: "0.75rem 1rem" }}>
          <strong>{s.name}</strong>
          <span style={{ marginLeft: 8, fontSize: 12, color: "#64748b" }}>{s.type}</span>
          <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>{s.url}</div>
          <span style={{ fontSize: 12 }}>{s.enabled !== false ? "활성" : "비활성"}</span>
        </div>
      ))}
      {sites.length > 80 && (
        <p style={{ color: "#64748b" }}>… 외 {sites.length - 80}건 (UI 표시 제한)</p>
      )}
    </div>
  );
}
