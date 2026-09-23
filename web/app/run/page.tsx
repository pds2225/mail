"use client";

import { useMemo, useState, useEffect } from "react";

type RunResult = Record<string, unknown>;

type MailPreview = {
  group_id?: string;
  group_name?: string;
  subject?: string;
  recipient_masked?: string[];
  notice_count?: number;
  html?: string;
  text?: string;
  generated_at?: string;
};

type ConfigPayload = {
  ok?: boolean;
  sites?: { enabled?: boolean }[];
  groups?: { active?: boolean; name?: string }[];
  settings?: Record<string, unknown>;
};

function formatProcessingTime(value: unknown): string {
  const ms = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(ms)) return "–";
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}초`;
}

export default function RunPage() {
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState("");
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"html" | "text">("html");

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
    setSelectedGroupId(null);
    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dry_run: true,
          include_raw_all: false,
          persist_seen: false,
          include_previews: true,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || "실행에 실패했습니다.");
      const nextResult = (payload.result || {}) as RunResult;
      setResult(nextResult);
      const previews = (nextResult.mail_previews as MailPreview[]) || [];
      if (previews[0]) {
        setSelectedGroupId(String(previews[0].group_id ?? previews[0].group_name ?? ""));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const counts = result
    ? [
        ["수집 공고 수", result.collected],
        ["날짜 대상 공고 수", result.date_matched_count],
        ["최종 추천 공고 수", result.final_mail_target_count],
        ["처리 시간", formatProcessingTime(result.processing_time_ms)],
      ]
    : [];

  const mailPreviews = (result?.mail_previews as MailPreview[]) || [];
  const selectedPreview =
    mailPreviews.find((p) => String(p.group_id ?? p.group_name ?? "") === selectedGroupId) ||
    mailPreviews[0] ||
    null;

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">
          실행 <span className="badge badge-gray">DRY RUN</span>
        </h1>
        <p className="page-desc">
          웹에서는 실제 발송 없이 dry-run만 실행합니다. 실제 SMTP 발송·읽음 상태 저장·라벨 변경은
          절대 일어나지 않습니다.
        </p>
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
        <p className="page-desc">
          실행 암호 없이 현재 설정으로 공고를 수집·판정합니다. 실제로 발송될 그룹별 메일도 그대로
          미리 볼 수 있습니다. SMTP 발송과 seen 상태 저장은 하지 않습니다.
        </p>
        <p className="hint mt">
          활성 소스가 많으면(현재 {config ? summary.sites : "여러"}개) 전체 수집에 시간이 오래 걸려
          웹에서 타임아웃될 수 있습니다. 전체 소스 전체 검증은{" "}
          <a
            href="https://github.com/pds2225/mail/actions/workflows/monitor.yml"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub Actions
          </a>
          에서 확인하세요(주의: 그 워크플로는 수동 실행하면 실제로 이메일을 발송합니다 — 확인만
          하려면 실행하지 마세요).
        </p>
        <div className="row mt">
          <button className="btn btn-primary" type="button" onClick={runPreview} disabled={running}>
            {running ? "실행 중…" : "미리보기 실행"}
          </button>
        </div>
      </section>

      {error ? (
        <section className="card">
          <p className="error">{error}</p>
          <p className="hint mt">
            웹 미리보기가 시간 초과됐다면, 활성 소스가 많아서일 수 있습니다. 전체 검증은{" "}
            <a
              href="https://github.com/pds2225/mail/actions/workflows/monitor.yml"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub Actions
            </a>
            에서 진행하세요(수동 실행 시 실제 발송됨에 주의).
          </p>
        </section>
      ) : null}

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

          <section className="card">
            <h2 className="card-title">그룹별 메일 미리보기</h2>
            {mailPreviews.length === 0 ? (
              <p className="empty">
                현재 조건에 맞는 신규 공고가 없어 미리볼 그룹 메일이 없습니다.
              </p>
            ) : (
              <>
                <p className="page-desc">
                  실제 발송이 쓰는 것과 동일한 renderer로 만든 미리보기입니다. 실제로 발송되지
                  않았습니다.
                </p>
                <div className="row mt" role="tablist" aria-label="미리볼 그룹 선택">
                  {mailPreviews.map((p) => {
                    const id = String(p.group_id ?? p.group_name ?? "");
                    const active = id === String(selectedPreview?.group_id ?? selectedPreview?.group_name ?? "");
                    return (
                      <button
                        key={id}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        className={`btn btn-small ${active ? "btn-primary" : "btn-secondary"}`}
                        onClick={() => setSelectedGroupId(id)}
                      >
                        {p.group_name || "(이름없음)"} ({p.notice_count ?? 0}건)
                      </button>
                    );
                  })}
                </div>

                {selectedPreview ? (
                  <div className="mt">
                    <dl className="mail-preview-meta">
                      <div>
                        <dt>그룹</dt>
                        <dd>{selectedPreview.group_name || "-"}</dd>
                      </div>
                      <div>
                        <dt>수신자</dt>
                        <dd>
                          {(selectedPreview.recipient_masked || []).length
                            ? selectedPreview.recipient_masked!.join(", ")
                            : "설정된 수신자 없음"}
                        </dd>
                      </div>
                      <div>
                        <dt>발송 예정 제목</dt>
                        <dd>{selectedPreview.subject || "-"}</dd>
                      </div>
                      <div>
                        <dt>공고 수</dt>
                        <dd>{selectedPreview.notice_count ?? 0}건</dd>
                      </div>
                      <div>
                        <dt>생성 시각</dt>
                        <dd>{selectedPreview.generated_at || "-"}</dd>
                      </div>
                    </dl>

                    <div className="row mt">
                      <button
                        type="button"
                        className={`btn btn-small ${viewMode === "html" ? "btn-primary" : "btn-secondary"}`}
                        onClick={() => setViewMode("html")}
                      >
                        HTML 보기
                      </button>
                      <button
                        type="button"
                        className={`btn btn-small ${viewMode === "text" ? "btn-primary" : "btn-secondary"}`}
                        onClick={() => setViewMode("text")}
                      >
                        텍스트 보기
                      </button>
                    </div>

                    <div className="mt">
                      {viewMode === "html" ? (
                        <iframe
                          title={`${selectedPreview.group_name || "그룹"} 메일 HTML 미리보기`}
                          srcDoc={selectedPreview.html || "<p>내용 없음</p>"}
                          sandbox=""
                          className="preview-frame"
                        />
                      ) : (
                        <pre className="pre" style={{ whiteSpace: "pre" }}>
                          {selectedPreview.text || "내용 없음"}
                        </pre>
                      )}
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
