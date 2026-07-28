"use client";

import { useEffect, useMemo, useState } from "react";

type RecipientEntry = {
  id: string;
  masked: string;
};

type RecipientTarget = {
  kind: "group" | "raw_all";
  id: string;
  name: string;
  active?: boolean;
  recipients: RecipientEntry[];
};

type PublicValidation = {
  validCount?: number;
  rejected?: { reason: string }[];
  masked?: string[];
};

type RecipientResponse = {
  ok?: boolean;
  error?: string;
  validation?: PublicValidation;
  update?: {
    beforeCount?: number;
    afterCount?: number;
    addedMasked?: string[];
    removedMasked?: string[];
  };
  packetMarkdown?: string;
  notice?: string;
};

function splitEmails(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

function targetKey(target: RecipientTarget): string {
  return `${target.kind}:${target.id}`;
}

export default function RecipientsPage() {
  const [targets, setTargets] = useState<RecipientTarget[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [text, setText] = useState("");
  const [removeIds, setRemoveIds] = useState<string[]>([]);
  const [result, setResult] = useState<RecipientResponse | null>(null);
  const [packet, setPacket] = useState<RecipientResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/config")
      .then((response) => response.json())
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "설정을 불러오지 못했습니다.");
        const nextTargets = (data.recipientTargets || []) as RecipientTarget[];
        setTargets(nextTargets);
        if (nextTargets.length) setSelectedKey(targetKey(nextTargets[0]));
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "load failed"))
      .finally(() => setLoading(false));
  }, []);

  const target = useMemo(
    () => targets.find((item) => targetKey(item) === selectedKey),
    [selectedKey, targets],
  );

  function selectTarget(value: string) {
    setSelectedKey(value);
    setRemoveIds([]);
    setResult(null);
    setPacket(null);
  }

  function toggleRemove(id: string, checked: boolean) {
    setRemoveIds((current) =>
      checked ? [...new Set([...current, id])] : current.filter((entry) => entry !== id),
    );
    setPacket(null);
  }

  async function validate() {
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/recipients/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ emails: splitEmails(text) }),
      });
      const data = (await response.json()) as RecipientResponse;
      setResult(data);
      setPacket(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "validation failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function createPacket() {
    if (!target) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/recipients/packet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          addEmails: splitEmails(text),
          removeRecipientIds: removeIds,
          target: target.kind,
          groupId: target.kind === "group" ? target.id : undefined,
        }),
      });
      const data = (await response.json()) as RecipientResponse;
      setPacket(data);
      if (data.validation) setResult(data);
      if (!response.ok && data.error) setError(data.error);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "packet failed");
    } finally {
      setSubmitting(false);
    }
  }

  const validation = result?.validation;

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">수신자 편집 · PR 패킷</h1>
        <p className="page-desc">
          GitHub JSON의 현재 수신자를 마스킹해 표시하고, 그룹별 추가·제거 제안을 만듭니다. 운영 설정과
          실제 메일 발송은 직접 실행하지 않습니다.
        </p>
      </header>

      {loading && <div className="empty">불러오는 중…</div>}
      {error && <p className="error">{error}</p>}

      {!loading ? (
        <div className="card">
          <div className="field">
            <label className="label" htmlFor="recipient-target">
              변경 대상
            </label>
            <select
              id="recipient-target"
              className="select"
              value={selectedKey}
              onChange={(event) => selectTarget(event.target.value)}
            >
              {targets.map((item) => (
                <option key={targetKey(item)} value={targetKey(item)}>
                  {item.name}
                  {item.kind === "group" && item.active === false ? " (비활성)" : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="field mt">
            <label className="label" htmlFor="emails">
              추가할 이메일 (줄바꿈·쉼표 구분)
            </label>
            <textarea
              id="emails"
              className="textarea"
              rows={4}
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                setResult(null);
                setPacket(null);
              }}
              placeholder="user@example.com"
            />
          </div>

          <div className="mt">
            <span className="label">현재 수신자 · 제거 선택</span>
            {target?.recipients.length ? (
              <div className="recipient-list">
                {target.recipients.map((entry) => (
                  <label className="check recipient-entry" key={entry.id}>
                    <input
                      type="checkbox"
                      checked={removeIds.includes(entry.id)}
                      onChange={(event) => toggleRemove(entry.id, event.target.checked)}
                    />
                    <span>{entry.masked}</span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="empty">현재 등록된 수신자가 없습니다.</div>
            )}
          </div>

          <p className="hint">
            전체 이메일은 브라우저 응답에 노출하지 않습니다. 제거 대상도 마스킹된 항목으로 선택합니다.
          </p>
          <div className="row mt">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={validate}
              disabled={submitting}
            >
              {submitting ? "처리 중…" : "추가 주소 검증"}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={createPacket}
              disabled={submitting || !target || (!splitEmails(text).length && !removeIds.length)}
            >
              {submitting ? "처리 중…" : "변경 PR 패킷 생성"}
            </button>
          </div>
        </div>
      ) : null}

      {validation?.masked?.length ? (
        <div className="card">
          <h3 className="card-title">
            추가 가능 <span className="badge badge-green">{validation.validCount}</span>
          </h3>
          <div className="row">
            {validation.masked.map((masked, index) => (
              <span key={index} className="tag">
                {masked}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {validation?.rejected?.length ? (
        <div className="card">
          <h3 className="card-title">
            수정 필요 <span className="badge badge-red">{validation.rejected.length}</span>
          </h3>
          {validation.rejected.map((rejected, index) => (
            <p key={index} className="error">
              {rejected.reason}
            </p>
          ))}
        </div>
      ) : null}

      {packet?.update ? (
        <div className="card">
          <h3 className="card-title">변경 요약</h3>
          <p className="stat">
            수신자 {packet.update.beforeCount}건 → {packet.update.afterCount}건
          </p>
          <div className="row">
            {(packet.update.addedMasked || []).map((masked) => (
              <span className="tag" key={`add-${masked}`}>
                + {masked}
              </span>
            ))}
            {(packet.update.removedMasked || []).map((masked) => (
              <span className="tag tag-danger" key={`remove-${masked}`}>
                − {masked}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {packet?.packetMarkdown ? (
        <div className="card">
          <h3 className="card-title">RECIPIENT_UPDATE_PACKET</h3>
          <p className="stat">{packet.notice}</p>
          <pre className="pre">{packet.packetMarkdown}</pre>
          <button
            type="button"
            className="btn btn-secondary mt"
            onClick={() => navigator.clipboard.writeText(packet.packetMarkdown || "")}
          >
            패킷 복사
          </button>
        </div>
      ) : null}
    </div>
  );
}
