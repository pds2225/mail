"use client";

import { useEffect, useState } from "react";
import { readApplySecret, writeApplySecret } from "@/lib/apply-client";

type Status = {
  applyReady?: boolean;
  mode?: "server" | "github-web";
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

  if (status?.mode !== "server") {
    return (
      <span className="apply-secret">
        <span className="badge badge-green">반영 가능</span>
      </span>
    );
  }

  return (
    <label className="apply-secret">
      <span className="apply-secret-label">반영 암호</span>
      <input
        type="password"
        className="input apply-secret-input"
        value={secret}
        onChange={(event) => {
          setSecret(event.target.value);
          writeApplySecret(event.target.value);
        }}
        placeholder="CONFIG_APPLY_SECRET"
        autoComplete="off"
        aria-label="반영 암호"
      />
      <span className={secret.trim() ? "badge badge-green" : "badge badge-gray"}>
        {secret.trim() ? "반영 가능" : "암호 필요"}
      </span>
    </label>
  );
}
