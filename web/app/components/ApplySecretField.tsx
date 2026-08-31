"use client";

import { useEffect, useState } from "react";
import { readApplySecret, writeApplySecret } from "@/lib/apply-client";

type Status = {
  applyReady?: boolean;
  hasApplySecret?: boolean;
  hasGithubToken?: boolean;
  repo?: string;
  branch?: string;
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

  const ready = Boolean(status?.applyReady);
  return (
    <label className="apply-secret">
      <span className="apply-secret-label">반영 암호</span>
      <input
        type="password"
        className="input apply-secret-input"
        value={secret}
        onChange={(event) => onChange(event.target.value)}
        placeholder="CONFIG_APPLY_SECRET"
        autoComplete="off"
        aria-label="GitHub 반영 암호"
      />
      <span className={ready ? "badge badge-green" : "badge badge-gray"}>
        {ready ? "반영 가능" : "토큰 필요"}
      </span>
    </label>
  );
}
