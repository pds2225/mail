"use client";

import { useEffect, useMemo, useState } from "react";
import { applyHeaders, followApplyResult } from "@/lib/apply-client";

type ReviewItem = {
  id: string;
  title: string;
  verdict?: "O" | "X" | null;
};

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [pending, setPending] = useState<Record<string, "O" | "X">>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showReviewed, setShowReviewed] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    fetch("/api/review")
      .then((response) => response.json())
      .then((payload) => {
        if (!payload.ok) throw new Error(payload.error || "검수 큐를 불러오지 못했습니다.");
        setItems(payload.items || []);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(
    () => (showReviewed ? items : items.filter((item) => !item.verdict)),
    [items, showReviewed],
  );
  const reviewed = items.filter((item) => item.verdict).length;
  const pendingIds = Object.keys(pending);
  const pendingCount = pendingIds.length;

  function choose(item: ReviewItem, verdict: "O" | "X") {
    setPending((current) => {
      if (current[item.id] === verdict) {
        // 같은 값을 다시 누르면 선택 취소.
        const next = { ...current };
        delete next[item.id];
        return next;
      }
      return { ...current, [item.id]: verdict };
    });
    setResult(null);
  }

  async function saveSelected() {
    if (pendingCount === 0) return;
    setSaving(true);
    setError("");
    setResult(null);
    try {
      const byId = new Map(items.map((item) => [item.id, item]));
      const payloadItems = pendingIds.map((id) => ({
        id,
        title: byId.get(id)?.title || "",
        verdict: pending[id],
      }));
      const response = await fetch("/api/review/apply", {
        method: "POST",
        headers: applyHeaders(),
        body: JSON.stringify({ items: payloadItems }),
      });
      const data = await response.json();
      setResult(data);
      if (!response.ok || !data.ok) throw new Error(data.error || "검수를 저장하지 못했습니다.");
      if (data.applied) {
        setItems((current) =>
          current.map((row) => (pending[row.id] ? { ...row, verdict: pending[row.id] } : row)),
        );
        setPending({});
      }
      followApplyResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <header className="page-header page-header-row">
        <div>
          <h1 className="page-title">공고 검수</h1>
          <p className="page-desc">
            V1의 제목 O/X 검수 기능을 그대로 사용합니다. O=내게 맞는 공고, X=아님. O/X를 눌러
            선택한 뒤 아래 &ldquo;선택 저장&rdquo;을 눌러야 실제로 기록됩니다(선택만으로는
            저장되지 않음).
          </p>
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={showReviewed}
            onChange={(event) => setShowReviewed(event.target.checked)}
          />
          검수 완료 포함
        </label>
      </header>

      <section className="dashboard-grid">
        <div className="metric-card">
          <span className="metric-label">검수 큐</span>
          <strong className="metric-value">{items.length || "–"}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">완료</span>
          <strong className="metric-value">{reviewed}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">남음</span>
          <strong className="metric-value">{Math.max(items.length - reviewed, 0)}</strong>
        </div>
      </section>

      <div className="row mt" style={{ alignItems: "center", gap: "0.75rem" }}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={pendingCount === 0 || saving}
          onClick={saveSelected}
        >
          {saving ? "저장 중…" : `선택 저장 (${pendingCount}건)`}
        </button>
        {pendingCount > 0 && !saving ? (
          <button type="button" className="btn btn-secondary btn-small" onClick={() => setPending({})}>
            선택 취소
          </button>
        ) : null}
      </div>

      {error ? <p className="error">{error}</p> : null}
      {loading ? <div className="empty">검수 큐 불러오는 중…</div> : null}

      {!loading && visible.length === 0 ? (
        <div className="empty">현재 표시할 검수 항목이 없습니다.</div>
      ) : null}

      <div className="review-list">
        {visible.slice(0, 40).map((item, index) => {
          const staged = pending[item.id];
          return (
            <article className="review-card" key={item.id}>
              <div className="review-index">{index + 1}</div>
              <div className="review-main">
                <div className="review-title">{item.title}</div>
                <div className="hint">{item.id}</div>
              </div>
              {item.verdict ? (
                <span className={item.verdict === "O" ? "badge badge-green" : "badge badge-red"}>
                  {item.verdict}
                </span>
              ) : (
                <div className="review-actions">
                  {staged ? (
                    <span className={staged === "O" ? "badge badge-green" : "badge badge-red"}>
                      선택됨: {staged} (미저장)
                    </span>
                  ) : null}
                  <button
                    type="button"
                    className={`btn btn-small review-o ${staged === "O" ? "btn-primary" : "btn-secondary"}`}
                    disabled={saving}
                    onClick={() => choose(item, "O")}
                  >
                    O 맞음
                  </button>
                  <button
                    type="button"
                    className={`btn btn-small review-x ${staged === "X" ? "btn-primary" : "btn-secondary"}`}
                    disabled={saving}
                    onClick={() => choose(item, "X")}
                  >
                    X 아님
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>

      {visible.length > 40 ? <p className="stat">상위 40건 표시 · 남은 {visible.length - 40}건</p> : null}

      {result?.notice ? (
        <section className="card mt">
          <h2 className="card-title">검수 저장</h2>
          <p>{String(result.notice)}</p>
        </section>
      ) : null}
    </div>
  );
}
