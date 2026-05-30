"use client";

import { useEffect, useState } from "react";
import type { StoredPacket } from "@/lib/packet-store";
import { loadPacketFromSession, savePacketToSession } from "@/lib/packet-store";

type Props = {
  title: string;
  storageKey: string;
  packet: Record<string, unknown> | null;
};

export function PacketPanel({ title, storageKey, packet }: Props) {
  const [restored, setRestored] = useState<StoredPacket | null>(null);

  useEffect(() => {
    if (packet?.packetMarkdown) {
      const stored: StoredPacket = {
        savedAt: new Date().toISOString(),
        markdown: String(packet.packetMarkdown),
        branch: packet.branch ? String(packet.branch) : undefined,
        meta: {
          prTitle: packet.prTitle,
          siteJsonPatch: packet.siteJsonPatch,
          patchSnippet: packet.patchSnippet,
        },
      };
      savePacketToSession(storageKey, stored);
      setRestored(stored);
    }
  }, [packet, storageKey]);

  useEffect(() => {
    if (!packet) setRestored(loadPacketFromSession(storageKey));
  }, [packet, storageKey]);

  const markdown = packet?.packetMarkdown
    ? String(packet.packetMarkdown)
    : restored?.markdown;
  if (!markdown) return null;

  function download(name: string, content: string, mime: string) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }

  const sitePatch = packet?.siteJsonPatch ? String(packet.siteJsonPatch) : null;

  return (
    <div className="card">
      <h3>{title}</h3>
      {packet?.notice ? <p style={{ fontSize: 14 }}>{String(packet.notice)}</p> : null}
      {restored && !packet ? (
        <p className="warn" style={{ fontSize: 13 }}>
          세션에 저장된 패킷 ({new Date(restored.savedAt).toLocaleString()})
        </p>
      ) : null}
      {packet?.branch ? (
        <p>
          브랜치 제안: <code>{String(packet.branch)}</code>
        </p>
      ) : null}
      {sitePatch ? (
        <>
          <h4>sites.json 추가 객체</h4>
          <pre className="pre">{sitePatch}</pre>
        </>
      ) : null}
      <pre className="pre">{markdown}</pre>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => navigator.clipboard.writeText(markdown)}
        >
          패킷 복사
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => download("PR_PACKET.md", markdown, "text/markdown")}
        >
          .md 다운로드
        </button>
        {sitePatch ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => download("site-add.json", sitePatch, "application/json")}
          >
            site JSON 다운로드
          </button>
        ) : null}
      </div>
    </div>
  );
}
