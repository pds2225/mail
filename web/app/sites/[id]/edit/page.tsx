"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { COLLECTOR_TYPES, type SiteEditInput, type SiteRecord } from "@/lib/site-types";

type ValidationView = {
  errors?: { message: string }[];
  warnings?: { message: string }[];
  checks?: Record<string, unknown>;
};

type UpdateResponse = {
  ok?: boolean;
  error?: string;
  notice?: string;
  branch?: string;
  packetMarkdown?: string;
  changedFields?: string[];
  validation?: ValidationView;
};

const emptyForm: SiteEditInput = {
  id: "",
  name: "",
  url: "",
  collectorType: "html_table",
  enabled: true,
  isAggregator: false,
  note: "",
  selectorsRow: "",
  testCollect: false,
};

export default function SiteEditPage() {
  const params = useParams<{ id: string }>();
  const siteId = decodeURIComponent(String(params.id || ""));
  const [form, setForm] = useState<SiteEditInput>(emptyForm);
  const [source, setSource] = useState<SiteRecord | null>(null);
  const [result, setResult] = useState<UpdateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.json())
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "설정을 불러오지 못했습니다.");
        const site = (data.sites || []).find((entry: SiteRecord) => entry.id === siteId);
        if (!site) throw new Error(`사이트를 찾을 수 없습니다: ${siteId}`);
        setSource(site);
        setForm({
          id: site.id,
          name: site.name || "",
          url: site.url || "",
          collectorType: site.type || "html_table",
          enabled: site.enabled !== false,
          isAggregator: Boolean(site.is_aggregator),
          note: typeof site.note === "string" ? site.note : "",
          selectorsRow:
            site.selectors && typeof site.selectors.row === "string" ? site.selectors.row : "",
          testCollect: false,
        });
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "load failed"))
      .finally(() => setLoading(false));
  }, [siteId]);

  function update<K extends keyof SiteEditInput>(key: K, value: SiteEditInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setResult(null);
  }

  async function submit(createPacket: boolean) {
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/sites/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          createPacket,
          probeUrl: form.testCollect,
        }),
      });
      const data = (await response.json()) as UpdateResponse;
      setResult(data);
      if (!response.ok && data.error) setError(data.error);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "request failed");
    } finally {
      setSubmitting(false);
    }
  }

  const validation = result?.validation;

  return (
    <div>
      <header className="page-header page-header-row">
        <div>
          <h1 className="page-title">사이트 편집</h1>
          <p className="page-desc">
            기존 JSON을 보존한 변경 제안만 생성합니다. 운영 파일은 직접 수정하지 않습니다.
          </p>
        </div>
        <Link className="btn btn-secondary" href="/sites">
          목록으로
        </Link>
      </header>

      {loading && <div className="empty">불러오는 중…</div>}
      {error && <p className="error">{error}</p>}

      {!loading && source ? (
        <div className="card">
          <div className="grid2">
            <div className="field">
              <label className="label" htmlFor="site-id">
                사이트 ID
              </label>
              <input id="site-id" className="input" value={form.id} readOnly />
              <p className="hint">수집 상태와 중복 키를 보존하기 위해 ID는 변경하지 않습니다.</p>
            </div>
            <div className="field">
              <label className="label" htmlFor="site-name">
                사이트명 *
              </label>
              <input
                id="site-name"
                className="input"
                value={form.name}
                onChange={(event) => update("name", event.target.value)}
              />
            </div>
            <div className="field">
              <label className="label" htmlFor="site-url">
                URL *
              </label>
              <input
                id="site-url"
                className="input"
                value={form.url}
                onChange={(event) => update("url", event.target.value)}
              />
            </div>
            <div className="field">
              <label className="label" htmlFor="site-collector">
                수집 방식 *
              </label>
              <select
                id="site-collector"
                className="select"
                value={form.collectorType}
                onChange={(event) => update("collectorType", event.target.value)}
              >
                {COLLECTOR_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="field mt">
            <label className="label" htmlFor="site-row">
              목록 행 selector
            </label>
            <input
              id="site-row"
              className="input"
              value={form.selectorsRow}
              onChange={(event) => update("selectorsRow", event.target.value)}
              placeholder="table tbody tr"
            />
          </div>

          <div className="field mt">
            <label className="label" htmlFor="site-note">
              메모
            </label>
            <textarea
              id="site-note"
              className="textarea"
              rows={3}
              value={form.note}
              onChange={(event) => update("note", event.target.value)}
            />
          </div>

          <div className="check-row mt">
            <label className="check">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => update("enabled", event.target.checked)}
              />
              활성
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={form.isAggregator}
                onChange={(event) => update("isAggregator", event.target.checked)}
              />
              통합포털(aggregator)
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={form.testCollect}
                onChange={(event) => update("testCollect", event.target.checked)}
              />
              URL 접근 테스트
            </label>
          </div>

          <div className="row mt">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => submit(false)}
              disabled={submitting}
            >
              {submitting ? "처리 중…" : "변경 검증"}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => submit(true)}
              disabled={submitting}
            >
              {submitting ? "처리 중…" : "수정 PR 패킷 생성"}
            </button>
          </div>
        </div>
      ) : null}

      {result?.changedFields ? (
        <div className="card">
          <h3 className="card-title">변경 필드</h3>
          <div className="row">
            {result.changedFields.length ? (
              result.changedFields.map((field) => (
                <span className="tag" key={field}>
                  {field}
                </span>
              ))
            ) : (
              <span className="stat">변경 없음</span>
            )}
          </div>
        </div>
      ) : null}

      {validation?.errors?.length ? (
        <div className="card">
          <h3 className="card-title">오류</h3>
          {validation.errors.map((issue, index) => (
            <p className="error" key={index}>
              {issue.message}
            </p>
          ))}
        </div>
      ) : null}

      {validation?.warnings?.length ? (
        <div className="card">
          <h3 className="card-title">경고</h3>
          {validation.warnings.map((issue, index) => (
            <p className="warn" key={index}>
              {issue.message}
            </p>
          ))}
        </div>
      ) : null}

      {result?.packetMarkdown ? (
        <div className="card">
          <h3 className="card-title">SITE_UPDATE_PR_PACKET</h3>
          <p className="stat">{result.notice}</p>
          <pre className="pre">{result.packetMarkdown}</pre>
          <button
            type="button"
            className="btn btn-secondary mt"
            onClick={() => navigator.clipboard.writeText(result.packetMarkdown || "")}
          >
            패킷 복사
          </button>
        </div>
      ) : null}
    </div>
  );
}
