"use client";

export const APPLY_SECRET_STORAGE_KEY = "mail-config-apply-secret";

export function readApplySecret(): string {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem(APPLY_SECRET_STORAGE_KEY) || "";
}

export function writeApplySecret(value: string): void {
  window.sessionStorage.setItem(APPLY_SECRET_STORAGE_KEY, value);
}

export function applyHeaders(): HeadersInit {
  const secret = readApplySecret();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (secret) headers["x-config-apply-secret"] = secret;
  return headers;
}
