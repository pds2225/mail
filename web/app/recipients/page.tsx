"use client";

import { useState } from "react";

export default function RecipientsPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null);

  async function validate() {
    const emails = text.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
    const res = await fetch("/api/recipients/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emails }),
    });
    setResult(await res.json());
    setPacket(null);
  }

  async function createPacket() {
    const emails = text.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
    const res = await fetch("/api/recipients/packet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emails, target: "raw_all" }),
    });
    setPacket(await res.json());
  }

  const validation = result?.validation as {
    valid?: string[];
    rejected?: { value: string; reason: string }[];
    masked?: string[];
  };

  return (
    <div>
      <h1>수신자 검증 · PR 패킷</h1>
      <p style={{ color: "#64748b" }}>
        이메일은 <code>groups.json</code> / <code>settings.json</code>에 PR로만 반영합니다. 임의
        주소를 코드에 추가하지 않습니다.
      </p>
      <div className="card">
        <label className="label">이메일 (줄바꿈·쉼표 구분)</label>
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
              {r.reason}: (마스킹됨)
            </p>
          ))}
        </div>
      ) : null}
      {packet?.packetMarkdown ? (
        <div className="card">
          <h3>RECIPIENT_UPDATE_PACKET</h3>
          <pre className="pre">{String(packet.packetMarkdown)}</pre>
        </div>
      ) : null}
    </div>
  );
}
