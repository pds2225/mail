"use client";

import { useState } from "react";
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
    try {
      const res = await fetch("/api/sites/packet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, probeUrl: form.testCollect }),
      });
      const data = await res.json();
      setPacket(data);
      if (data.validation) setValidation(data);
    } finally {
      setLoading(false);
    }
  }

  const v = validation?.validation as
    | {
        errors?: { message: string }[];
        warnings?: { message: string }[];
        checks?: Record<string, unknown>;
      }
    | undefined;

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">사이트 추가</h1>
        <p className="page-desc">
          저장은 PR 패킷 생성입니다. 운영 <code>config/sites.json</code>은 자동 변경되지 않습니다.
        </p>
      </header>

      <div className="card">
        <div className="grid2">
          <div className="field">
            <label className="label" htmlFor="f-name">
              사이트명 *
            </label>
            <input
              id="f-name"
              className="input"
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="예: OOO 지원사업"
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="f-url">
              URL *
            </label>
            <input
              id="f-url"
              className="input"
              value={form.url}
              onChange={(e) => update("url", e.target.value)}
              placeholder="https://"
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="f-cat">
              그룹/카테고리
            </label>
            <select
              id="f-cat"
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
          <div className="field">
            <label className="label" htmlFor="f-col">
              수집 방식 *
            </label>
            <select
              id="f-col"
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

        <div className="field mt">
          <label className="label" htmlFor="f-note">
            메모
          </label>
          <textarea
            id="f-note"
            className="textarea"
            rows={2}
            value={form.note}
            onChange={(e) => update("note", e.target.value)}
          />
        </div>

        <div className="check-row mt">
          <label className="check">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => update("enabled", e.target.checked)}
            />
            활성
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={form.isAggregator}
              onChange={(e) => update("isAggregator", e.target.checked)}
            />
            통합포털(aggregator)
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={form.testCollect}
              onChange={(e) => update("testCollect", e.target.checked)}
            />
            URL 접근 테스트
          </label>
        </div>

        <div className="row mt">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={runValidate}
            disabled={loading}
          >
            {loading ? "처리 중…" : "검증"}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={generatePacket}
            disabled={loading}
          >
            {loading ? "처리 중…" : "PR 패킷 생성"}
          </button>
        </div>
      </div>

      {v?.errors?.length ? (
        <div className="card">
          <h3 className="card-title">
            오류 <span className="badge badge-red">{v.errors.length}</span>
          </h3>
          {v.errors.map((e, i) => (
            <p key={i} className="error">
              {e.message}
            </p>
          ))}
        </div>
      ) : null}

      {v?.warnings?.length ? (
        <div className="card">
          <h3 className="card-title">
            경고 <span className="badge badge-gray">{v.warnings.length}</span>
          </h3>
          {v.warnings.map((e, i) => (
            <p key={i} className="warn">
              {e.message}
            </p>
          ))}
        </div>
      ) : null}

      {v?.checks && (
        <div className="card">
          <h3 className="card-title">수집 누락 점검</h3>
          <ul>
            {Object.entries(v.checks).map(([k, val]) => (
              <li key={k}>
                <code>{k}</code>: {String(val)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {packet?.packetMarkdown ? (
        <div className="card">
          <h3 className="card-title">PR 패킷</h3>
          <p style={{ fontSize: 14 }}>{String(packet.notice)}</p>
          <p>
            브랜치 제안: <code>{String(packet.branch)}</code>
          </p>
          <pre className="pre">{String(packet.packetMarkdown)}</pre>
          <button
            type="button"
            className="btn btn-secondary mt"
            onClick={() => navigator.clipboard.writeText(String(packet.packetMarkdown))}
          >
            패킷 복사
          </button>
        </div>
      ) : null}
    </div>
  );
}
