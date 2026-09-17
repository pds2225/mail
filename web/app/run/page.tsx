"use client";

import { useEffect, useMemo, useState } from "react";

type RunResult = Record<string, unknown>;

type ConfigPayload = {
  ok?: boolean;
  sites?: { enabled?: boolean }[];
  groups?: { active?: boolean; name?: string }[];
  settings?: Record<string, unknown>;
};

export default function RunPage() {
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState("");
  const [secret, setSecret] = useState("");
  const [needsSecret, setNeedsSecret] = useState(false);

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.json())
      .then((payload) => setConfig(payload))
      .catch(() => setConfig(null));
  }, []);

  const summary = useMemo(() => {
    const sites = config?.sites || [];
    const groups = config?.groups || [];
    return {
      sites: sites.filter((item) => item.enabled !== false).length,
      groups: groups.filter((item) => item.active !== false).length,
      days: Number(config?.settings?.days_back ?? 3),
    };
  }, [config]);

  async function runPreview() {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (secret.trim()) headers.Authorization = `Bearer ${secret.trim()}`;
      const response = await fetch("/api/run", {
        method: "POST",
        headers,
        body: JSON.stringify({ dry_run: true, include_raw_all: false, persist_seen: false }),
      });
      const payload = await response.json();
      if (response.status === 401) {
        setNeedsSecret(true);
        throw new Error("실행 암호가 필요한 환경입니다.");
      }
      if (!response.ok || !payload.ok) throw new Error(payload.error || "실행에 실패했습니다.");
      setResult((payload.result || {}) as RunResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const counts = result
    ? [
        ["수집", result.collected],
        ["중복 제거 후", result.deduped],
        ["날짜 대상", result.date_matched ?? result.filtered_by_date],
        ["추천", result.final_mail_count ?? result.included],
      ]
    : [];

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">실행</h1>
        <p className="page-desc">V1의 실행 화면을 복구했습니다. 웹에서는 실제 발송 없이 dry-run만 실행합니다.</p>
      </header>

      <section className="dashboard-grid">
        <div className="metric-card">
          <span className="metric-label">활성 소스</span>
          <strong className="metric-value">{config ? summary.sites : "–"}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">활성 그룹</span>
          <strong className="metric-value">{config ? summary.groups : "–"}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">조회 기준</span>
          <strong className="metric-value">D-{summary.days}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">발송</span>
          <strong className="metric-value">OFF</strong>
          <span className="metric-sub">미리보기 전용</span>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">지금 미리보기</h2>
        <p className="page-desc">현재 설정으로 공고를 수집·판정하지만 SMTP 발송과 seen 상태 저장은 하지 않습니다.</p>
        {needsSecret ? (
          <div className="field mt">
            <label className="label" htmlFor="run-secret">실행 암호</label>
            <input
              id="run-secret"
              type="password"
              className="input"
              value={secret}
              onChange={(event) => setSecret(event.target.value)}
              autoComplete="off"
            />
          </div>
        ) : null}
        <div className="row mt">
          <button className="btn btn-primary" type="button" onClick={runPreview} disabled={running}>
            {running ? "실행 중…" : "미리보기 실행"}
          </button>
        </div>
      </section>

      {error ? <p className="error">{error}</p> : null}

      {result ? (
        <>
          <section className="dashboard-grid" aria-label="실행 결과">
            {counts.map(([label, value]) => (
              <div className="metric-card" key={String(label)}>
                <span className="metric-label">{String(label)}</span>
                <strong className="metric-value">{value == null ? "–" : String(value)}</strong>
              </div>
            ))}
          </section>
          <section className="card">
            <h2 className="card-title">실행 판정</h2>
            <p>
              상태: <strong>{String(result.run_status || result.mode || "완료")}</strong>
            </p>
            <p className="hint">실제 메일 발송: {String(result.mail_sent ?? false)}</p>
            <details>
              <summary>상세 결과 보기</summary>
              <pre className="pre mt">{JSON.stringify(result, null, 2)}</pre>
            </details>
          </section>
        </>
      ) : null}
    </div>
  );
}
