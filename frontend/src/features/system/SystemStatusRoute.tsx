import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { OrganizationSummary } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { SystemStatusPage } from "./SystemStatusPage";
import type { SystemStatusData } from "./SystemStatusPanel";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };
type FailedTask = { id: string; document_id: string; status: string; dead_letter?: boolean; attempts?: number; error_message?: string; created_at: string };

export function SystemStatusRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [details, setDetails] = useState<SystemStatusData | null>(null);
  const [failedTasks, setFailedTasks] = useState<FailedTask[]>([]);
  const [notice, setNotice] = useState("");
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async () => {
    try {
      const [nextDetails, nextOrganization] = await Promise.all([api<SystemStatusData>("/system/status"), api<OrganizationSummary>("/organization")]);
      setDetails(nextDetails); setOrganization(nextOrganization);
      if (["org_admin", "platform_admin"].includes(nextOrganization.role)) setFailedTasks(await api<FailedTask[]>("/ingestion-tasks?status=failed&page=1&page_size=20"));
      else setFailedTasks([]);
    } catch (error) { setNotice(error instanceof Error ? error.message : "系统状态读取失败"); }
  }, [api]);
  useEffect(() => { if (!token) { navigate("/"); return; } void load(); }, [load, navigate, token]);
  const retry = (id: string) => { void api(`/ingestion-tasks/${id}/dead-letter/retry`, { method: "POST" }).then(() => { setFailedTasks((current) => current.filter((task) => task.id !== id)); setNotice("死信任务已重新入队"); }).catch((error) => setNotice(error instanceof Error ? error.message : "死信任务重试失败")); };
  return <AppShell nav="系统状态" items={NAV_ITEMS} organizationName={organization?.name} systemStatus={details?.dependencies && Object.values(details.dependencies).some((item) => ["error", "unavailable"].includes(item.status)) ? "degraded" : "ready"} onNavigate={(item) => navigate(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    <SystemStatusPage details={details} showDeadLetters={["org_admin", "platform_admin"].includes(organization?.role || "")} failedTasks={failedTasks} onRetry={retry} />
  </AppShell>;
}
