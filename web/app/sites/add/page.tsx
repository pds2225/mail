"use client";

import { useState } from "react";
import { PacketPanel } from "@/app/components/PacketPanel";
import { SITE_PACKET_STORAGE_KEY } from "@/lib/packet-store";
import { COLLECTOR_TYPES, SITE_CATEGORIES } from "@/lib/site-types";

const defaultForm = {
  name: "",
  url: "",
  category: "전용 HTML",
  collectorType: "html_table",
  enabled: true,
  isAggregator: false,
  note: "",
  testCollect: true,
};

export default function SiteAddPage() {
  const [form, setForm] = useState(defaultForm);
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setValidation(null);
    setPacket(null);
  }

  async function runValidate() {
    setLoading(true);
    setPacket(null);
    try {
      const res = await fetch("/api/sites/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, probeUrl: form.testCollect }),
      });
      const data = await res.json();
      setValidation(data);
    } finally {
      setLoading(false);
    }
  }

  async function generatePacket() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/sites/packet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, probeUrl: form.testCollect }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "검증 실패 — 패킷을 생성하지 않았습니다.");
        if (data.validation) setValidation({ validation: data.validation });
        setPacket(null);
        return;
      }
      setPacket(data);
      if (data.validation) setValidation(data);
    } finally {
      setLoading(false);
    }
  }

  const v = validation?.validation as {
    errors?: { message: string }[];
    warnings?: { message: string }[];
    checks?: Record<string, unknown>;
  } | undefined;

  return (
    <div>
      <h1>사이트 추가</h1>
      <p style={{ color: "#64748b" }}>
        저장은 PR 패킷 생성입니다. 운영 <code>sites.json</code>은 자동 변경되지 않습니다.
      </p>

      <div className="card">
        <div className="grid2">
          <div>
            <label className="label">사이트명 *</label>
            <input
              className="input"
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="예: OOO 지원사업"
            />
          </div>
          <div>
            <label className="label">URL *</label>
            <input
              className="input"
              value={form.url}
              onChange={(e) => update("url", e.target.value)}
              placeholder="https://"
            />
          </div>
          <div>
            <label className="label">그룹/카테고리</label>
            <select
              className="select"
              value={form.category}
              onChange={(e) => update("category", e.target.value)}
            >
              {SITE_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">수집 방식 *</label>
            <select
              className="select"
              value={form.collectorType}
              onChange={(e) => update("collectorType", e.target.value)}
            >
              {COLLECTOR_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ marginTop: "1rem" }}>
          <label className="label">메모</label>
          <textarea
            className="textarea"
            rows={2}
            value={form.note}
            onChange={(e) => update("note", e.target.value)}
          />
        </div>
        <div style={{ display: "flex", gap: "1.5rem", marginTop: "1rem", flexWrap: "wrap" }}>
          <label>
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => update("enabled", e.target.checked)}
            />{" "}
            활성
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.isAggregator}
              onChange={(e) => update("isAggregator", e.target.checked)}
            />{" "}
            통합포털(aggregator)
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.testCollect}
              onChange={(e) => update("testCollect", e.target.checked)}
            />{" "}
            URL 접근 테스트
          </label>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: "1.25rem" }}>
          <button type="button" className="btn btn-secondary" onClick={runValidate} disabled={loading}>
            검증
          </button>
          <button type="button" className="btn btn-primary" onClick={generatePacket} disabled={loading}>
            PR 패킷 생성
          </button>
        </div>
      </div>

      {v?.errors?.length ? (
        <div className="card">
          <h3>오류</h3>
          {v.errors.map((e, i) => (
            <p key={i} className="error">
              {e.message}
            </p>
          ))}
        </div>
      ) : null}
      {v?.warnings?.length ? (
        <div className="card">
          <h3>경고</h3>
          {v.warnings.map((e, i) => (
            <p key={i} className="warn">
              {e.message}
            </p>
          ))}
        </div>
      ) : null}
      {v?.checks && (
        <div className="card">
          <h3>수집 누락 점검</h3>
          <ul>
            {Object.entries(v.checks).map(([k, val]) => (
              <li key={k}>
                <code>{k}</code>: {String(val)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {error ? <p className="error">{error}</p> : null}
      <PacketPanel title="PR 패킷" storageKey={SITE_PACKET_STORAGE_KEY} packet={packet} />
    </div>
  );
}
