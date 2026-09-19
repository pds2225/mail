"use client";

import { useEffect, useState } from "react";
import { applyHeaders, followApplyResult } from "@/lib/apply-client";
import ManualPendingApply from "@/app/components/ManualPendingApply";

type Settings = {
  date_filter_enabled?: boolean;
  days_back?: number;
  raw_all_enabled?: boolean;
  date_unknown_policy?: string;
  date_unknown_max_age_days?: number;
  region_unknown_mail_limit?: number;
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.json())
      .then((payload) => {
        if (!payload.ok) throw new Error(payload.error || "설정을 불러오지 못했습니다.");
        setSettings(payload.settings || {});
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  function patch<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((current) => ({ ...(current || {}), [key]: value }));
    setResult(null);
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/config/apply", {
        method: "POST",
        headers: applyHeaders(),
        body: JSON.stringify({
          resource: "settings",
          patch: {
            date_filter_enabled: settings.date_filter_enabled !== false,
            days_back: Number(settings.days_back ?? 3),
            raw_all_enabled: settings.raw_all_enabled !== false,
            date_unknown_policy: settings.date_unknown_policy || "recall",
            date_unknown_max_age_days: Number(settings.date_unknown_max_age_days ?? 40),
            region_unknown_mail_limit: Number(settings.region_unknown_mail_limit ?? 10),
          },
        }),
      });
      const data = await response.json();
      setResult(data);
      if (!response.ok || !data.ok) throw new Error(data.error || "저장하지 못했습니다.");
      if (!data.manualPasteRequired) followApplyResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">설정</h1>
        <p className="page-desc">V1의 전역 설정 화면을 현재 정책값을 보존하는 방식으로 복구했습니다.</p>
      </header>

      {error ? <p className="error">{error}</p> : null}
      {loading ? <div className="empty">불러오는 중…</div> : null}

      {settings ? (
        <>
          <section className="card">
            <h2 className="card-title">날짜 필터</h2>
            <div className="grid2">
              <label className="check">
                <input
                  type="checkbox"
                  checked={settings.date_filter_enabled !== false}
                  onChange={(event) => patch("date_filter_enabled", event.target.checked)}
                />
                최근 공고 날짜 필터 사용
              </label>
              <div className="field">
                <label className="label" htmlFor="days-back">재조회 기간</label>
                <select
                  id="days-back"
                  className="select"
                  value={Number(settings.days_back ?? 3)}
                  onChange={(event) => patch("days_back", Number(event.target.value))}
                >
                  {[1, 2, 3, 4, 5, 7].map((value) => (
                    <option key={value} value={value}>최근 {value}일</option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          <section className="card">
            <h2 className="card-title">날짜가 불명확한 공고</h2>
            <div className="grid2">
              <div className="field">
                <label className="label" htmlFor="unknown-policy">처리 방식</label>
                <select
                  id="unknown-policy"
                  className="select"
                  value={settings.date_unknown_policy || "recall"}
                  onChange={(event) => patch("date_unknown_policy", event.target.value)}
                >
                  <option value="recall">놓치지 않기 우선</option>
                  <option value="strict">날짜 확인된 공고 우선</option>
                </select>
              </div>
              <div className="field">
                <label className="label" htmlFor="unknown-age">최대 확인 기간</label>
                <input
                  id="unknown-age"
                  className="input"
                  type="number"
                  min={1}
                  max={120}
                  value={Number(settings.date_unknown_max_age_days ?? 40)}
                  onChange={(event) => patch("date_unknown_max_age_days", Number(event.target.value))}
                />
              </div>
            </div>
          </section>

          <section className="card">
            <h2 className="card-title">메일 표시</h2>
            <div className="grid2">
              <label className="check">
                <input
                  type="checkbox"
                  checked={settings.raw_all_enabled !== false}
                  onChange={(event) => patch("raw_all_enabled", event.target.checked)}
                />
                원본전체 메일 기능 사용
              </label>
              <div className="field">
                <label className="label" htmlFor="region-limit">지역 확인 필요 표시 상한</label>
                <input
                  id="region-limit"
                  className="input"
                  type="number"
                  min={0}
                  max={30}
                  value={Number(settings.region_unknown_mail_limit ?? 10)}
                  onChange={(event) => patch("region_unknown_mail_limit", Number(event.target.value))}
                />
              </div>
            </div>
            <p className="hint">수신자 주소와 Secret은 이 화면에서 표시하거나 저장하지 않습니다.</p>
          </section>

          <div className="row">
            <button type="button" className="btn btn-primary" disabled={saving} onClick={save}>
              {saving ? "저장 중…" : "설정 저장"}
            </button>
          </div>
        </>
      ) : null}

      {result ? (
        <section className="card mt">
          <h2 className="card-title">저장 결과</h2>
          {result.error ? <p className="error">{String(result.error)}</p> : null}
          {result.notice ? <p>{String(result.notice)}</p> : null}
          <ManualPendingApply result={result} />
        </section>
      ) : null}
    </div>
  );
}
