"use client";

import { useEffect, useState } from "react";
import { readApplySecret, writeApplySecret } from "@/lib/apply-client";

type Status = {
  applyReady?: boolean;
  mode?: "server" | "client-token";
  tokenUrl?: string;
};

export default function ApplySecretField() {
  const [secret, setSecret] = useState("");
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    setSecret(readApplySecret());
    fetch("/api/apply/status")
      .then((response) => response.json())
      .then((data) => setStatus(data))
      .catch(() => setStatus(null));
  }, []);

  function onChange(value: string) {
    setSecret(value);
    writeApplySecret(value);
  }

  const serverReady = Boolean(status?.applyReady);
  const clientMode = status?.mode !== "server";
  const ready = serverReady || (clientMode && Boolean(secret.trim()));
  const label = serverReady ? "반영 암호" : "GitHub 토큰";
  const placeholder = serverReady ? "CONFIG_APPLY_SECRET" : "ghp_… 또는 github_pat_…";

  return (
    <label className="apply-secret">
      <span className="apply-secret-label">{label}</span>
      <input
        type="password"
        className="input apply-secret-input"
        value={secret}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        aria-label={label}
      />
      {clientMode && status?.tokenUrl ? (
        <a
          className="apply-secret-link"
          href={status.tokenUrl}
          target="_blank"
          rel="noreferrer"
        >
          토큰 만들기
        </a>
      ) : null}
      <span className={ready ? "badge badge-green" : "badge badge-gray"}>
        {ready ? "반영 가능" : "토큰 필요"}
      </span>
    </label>
  );
}
