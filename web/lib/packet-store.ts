/** Client-side persistence key for last generated PR packet (browser only). */
export const SITE_PACKET_STORAGE_KEY = "mail_admin_site_packet_v1";
export const RECIPIENT_PACKET_STORAGE_KEY = "mail_admin_recipient_packet_v1";

export type StoredPacket = {
  savedAt: string;
  markdown: string;
  branch?: string;
  meta?: Record<string, unknown>;
};

export function savePacketToSession(key: string, data: StoredPacket): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify(data));
  } catch {
    /* quota / private mode */
  }
}

export function loadPacketFromSession(key: string): StoredPacket | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as StoredPacket;
  } catch {
    return null;
  }
}
