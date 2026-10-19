import { describe, expect, it } from "vitest";
import { ApiError, apiRequest } from "./api";
import { getApiErrorMessage, getApiErrorState } from "./api-errors";

describe("API error mapping", () => {
  it.each([[401, "authentication"], [403, "forbidden"], [404, "not-found"], [409, "conflict"], [422, "validation"], [429, "rate-limited"], [500, "server"]] as const)("maps status %s to %s", (status, expected) => expect(getApiErrorState(new ApiError(status, "failed"))).toBe(expected));
  it("uses a recovery-focused network message", () => expect(getApiErrorMessage("network")).toContain("检查网络"));
  it("keeps an API recovery hint and Trace ID for structured failures", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: { message: "无法连接到数据源", hint: "请检查主机。" } }), { status: 502, headers: { "content-type": "application/json", "x-trace-id": "trace-123" } });
    await expect(apiRequest("/api", "token", "/data-sources/source/test")).rejects.toThrow("无法连接到数据源：请检查主机。（Trace ID: trace-123）");
    globalThis.fetch = originalFetch;
  });
});
