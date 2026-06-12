import { afterEach, describe, expect, it, vi } from "vitest";
import { probeUrlReachable } from "@/lib/site-validation";

const originalFetch = globalThis.fetch;

describe("url reachability probe", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("falls back to GET when HEAD is blocked", async () => {
    const methods: string[] = [];
    const fetchMock = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      methods.push(init?.method || "GET");
      if (init?.method === "HEAD") {
        throw new Error("HEAD blocked");
      }
      return new Response("ok", { status: 200 });
    });
    globalThis.fetch = fetchMock as typeof fetch;

    await expect(probeUrlReachable("https://example.com/notices", 1000)).resolves.toBe(true);
    expect(methods).toEqual(["HEAD", "GET"]);
  });

  it("accepts 405 from HEAD without retrying GET", async () => {
    const fetchMock = vi.fn(async () => new Response("", { status: 405 }));
    globalThis.fetch = fetchMock as typeof fetch;

    await expect(probeUrlReachable("https://example.com/notices", 1000)).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]?.method).toBe("HEAD");
  });

  it("returns false when HEAD and GET both fail", async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error("network failed");
    });
    globalThis.fetch = fetchMock as typeof fetch;

    await expect(probeUrlReachable("https://example.com/notices", 1000)).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
