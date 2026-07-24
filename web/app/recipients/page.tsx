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
      <header className="page-header">
        <h1 className="page-title">수신자 검증 · PR 패킷</h1>
        <p className="page-desc">
          이메일은 <code>config/groups.json</code> / <code>config/settings.json</code>에 PR로만 반영합니다. 임의
          주소를 코드에 추가하지 않습니다.
        </p>
      </header>

      <div className="card">
        <label className="label" htmlFor="emails">
          이메일 (줄바꿈·쉼표 구분)
        </label>
        <textarea
          id="emails"
          className="textarea"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="user@example.com"
        />
        <p className="hint">검증 후 PR 패킷을 생성하면 변경 내용을 복사해 PR로 반영할 수 있습니다.</p>
        <div className="row mt">
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
          <h3 className="card-title">
            유효 <span className="badge badge-green">{validation.masked.length}</span>
          </h3>
          <div className="row">
            {validation.masked.map((m, i) => (
              <span key={i} className="tag">
                {m}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {validation?.rejected?.length ? (
        <div className="card">
          <h3 className="card-title">
            거부됨 <span className="badge badge-red">{validation.rejected.length}</span>
          </h3>
          {validation.rejected.map((r, i) => (
            <p key={i} className="error">
              {r.reason}: (마스킹됨)
            </p>
          ))}
        </div>
      ) : null}

      {packet?.packetMarkdown ? (
        <div className="card">
          <h3 className="card-title">RECIPIENT_UPDATE_PACKET</h3>
          <pre className="pre">{String(packet.packetMarkdown)}</pre>
        </div>
      ) : null}
    </div>
  );
}
