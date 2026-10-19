import { ApiError } from "./api";

export type ApiErrorState = "authentication" | "forbidden" | "not-found" | "conflict" | "validation" | "rate-limited" | "server" | "network";
export function getApiErrorState(error: unknown): ApiErrorState {
  if (!(error instanceof ApiError)) return "network";
  if (error.status === 401) return "authentication";
  if (error.status === 403) return "forbidden";
  if (error.status === 404) return "not-found";
  if (error.status === 409) return "conflict";
  if (error.status === 422) return "validation";
  if (error.status === 429) return "rate-limited";
  return "server";
}

export function getApiErrorMessage(state: ApiErrorState): string {
  return { authentication: "登录已过期，请重新登录。", forbidden: "当前角色没有执行该操作的权限。", "not-found": "资源不存在、已归档或不属于当前组织。", conflict: "资源状态已变化，请刷新后重试。", validation: "输入内容不符合要求，请检查后重试。", "rate-limited": "请求过于频繁，请稍后再试。", server: "服务暂时不可用，请稍后重试。", network: "无法连接服务，请检查网络后重试。" }[state];
}
