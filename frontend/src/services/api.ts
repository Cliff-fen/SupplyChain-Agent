export const API_BASE = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "/api/v1" : "http://localhost:8000/api/v1");

export class ApiError extends Error {
  status: number;
  traceId?: string;

  constructor(status: number, message: string, traceId?: string) {
    super(traceId ? `${message}（Trace ID: ${traceId}）` : message);
    this.name = "ApiError";
    this.status = status;
    this.traceId = traceId;
  }
}

let refreshInFlight: Promise<{ access_token: string; refresh_token?: string }> | null = null;

export async function apiRequest<T>(
  baseUrl: string,
  token: string,
  path: string,
  init?: RequestInit,
  refreshToken?: string,
  onTokenUpdate?: (accessToken: string, refreshToken: string) => void,
): Promise<T> {
  const request = (accessToken: string) => {
    const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
    const headers: HeadersInit = {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(init?.body && !isFormData ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    };
    return fetch(`${baseUrl}${path}`, { ...init, headers });
  };
  let response = await request(token);
  if (response.status === 401 && refreshToken && !path.startsWith("/auth/refresh")) {
    refreshInFlight ??= fetch(`${baseUrl}/auth/refresh`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).then(async (refreshResponse) => {
      if (!refreshResponse.ok) throw new ApiError(401, "登录已过期，请重新登录");
      return await refreshResponse.json() as { access_token: string; refresh_token?: string };
    }).finally(() => { refreshInFlight = null; });
    const refreshed = await refreshInFlight;
    const nextRefresh = refreshed.refresh_token || refreshToken;
    onTokenUpdate?.(refreshed.access_token, nextRefresh);
    response = await request(refreshed.access_token);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object"
        ? `${String(detail.message || "请求失败")}${detail.hint ? `：${String(detail.hint)}` : ""}`
        : "请求失败";
    throw new ApiError(response.status, message, response.headers.get("x-trace-id") || undefined);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
