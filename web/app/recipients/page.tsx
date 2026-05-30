"use client";

import { useEffect, useState } from "react";
import { PacketPanel } from "@/app/components/PacketPanel";
import { RECIPIENT_PACKET_STORAGE_KEY } from "@/lib/packet-store";

type Group = { id: string; name: string; recipients?: string[] };

export default function RecipientsPage() {
  const [text, setText] = useState("");
  const [groups, setGroups] = useState<Group[]>([]);
  const [target, setTarget] = useState<"group" | "raw_all">("raw_all");
  const [groupId, setGroupId] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((d) => {
        if (d.ok && Array.isArray(d.groups)) {
          setGroups(d.groups);
          if (d.groups[0]?.id) setGroupId(d.groups[0].id);
        }
      })
      .catch(() => setError("그룹 목록을 불러오지 못했습니다."));
  }, []);

  function parseEmails() {
    return text.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
  }

  async function validate() {
    setError("");
    setPacket(null);
    const res = await fetch("/api/recipients/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emails: parseEmails() }),
    });
    const data = await res.json();
    setResult(data);
  }

  async function createPacket() {
    setError("");
    const res = await fetch("/api/recipients/packet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        emails: parseEmails(),
        target,
        groupId: target === "group" ? groupId : undefined,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.error || "패킷 생성 실패");
      if (data.validation) setResult({ validation: data.validation });
      setPacket(null);
      return;
    }
    setPacket(data);
    setResult({ validation: data.validation });
  }

  const validation = result?.validation as {
    valid?: string[];
    rejected?: { reason: string }[];
    masked?: string[];
    validCount?: number;
  };

  const selectedGroup = groups.find((g) => g.id === groupId);

  return (
    <div>
      <h1>수신자 검증 · PR 패킷</h1>
      <p style={{ color: "#64748b" }}>
        이메일은 <code>groups.json</code> / <code>settings.json</code>에 PR로만 반영합니다. 기존
        수신자는 마스킹만 표시됩니다.
      </p>
      <div className="card">
        <label className="label">반영 대상</label>
        <select
          className="select"
          value={target}
          onChange={(e) => setTarget(e.target.value as "group" | "raw_all")}
        >
          <option value="raw_all">settings.json — raw_all_recipients</option>
          <option value="group">groups.json — 그룹별 recipients</option>
        </select>
        {target === "group" ? (
          <div style={{ marginTop: 12 }}>
            <label className="label">그룹</label>
            <select className="select" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} ({g.id})
                </option>
              ))}
            </select>
            {selectedGroup?.recipients?.length ? (
              <p style={{ fontSize: 13, color: "#64748b", marginTop: 8 }}>
                현재 수신자(마스킹): {selectedGroup.recipients.join(", ")}
              </p>
            ) : null}
          </div>
        ) : null}
        <label className="label" style={{ marginTop: 12 }}>
          추가할 이메일 (줄바꿈·쉼표 구분)
        </label>
        <textarea
          className="textarea"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="user@example.com"
        />
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button type="button" className="btn btn-secondary" onClick={validate}>
            검증
          </button>
          <button type="button" className="btn btn-primary" onClick={createPacket}>
            PR 패킷 생성
          </button>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {validation?.masked?.length ? (
        <div className="card">
          <h3>유효 (마스킹)</h3>
          <ul>
            {validation.masked.map((m, i) => (
              <li key={i}>
                <code>{m}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {validation?.rejected?.length ? (
        <div className="card">
          <h3>거부됨</h3>
          {validation.rejected.map((r, i) => (
            <p key={i} className="error">
              {r.reason}
            </p>
          ))}
        </div>
      ) : null}
      <PacketPanel
        title="RECIPIENT_UPDATE_PACKET"
        storageKey={RECIPIENT_PACKET_STORAGE_KEY}
        packet={packet}
      />
    </div>
  );
}
