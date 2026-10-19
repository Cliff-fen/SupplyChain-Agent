import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { OrganizationSummary } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { DashboardConfigurationPage } from "./DashboardConfigurationPage";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };
type Config = { dashboard_id: string; refresh_interval_seconds: number; visible_widgets: string[] };

export function DashboardConfigurationRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [config, setConfig] = useState<Config>({ dashboard_id: "", refresh_interval_seconds: 300, visible_widgets: [] });
  const [notice, setNotice] = useState("");
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async () => { try { const [nextConfig, nextOrganization] = await Promise.all([api<Config>("/dashboards/supply-chain/config"), api<OrganizationSummary>("/organization")]); setConfig(nextConfig); setOrganization(nextOrganization); } catch (error) { setNotice(error instanceof Error ? error.message : "大屏配置读取失败"); } }, [api]);
  useEffect(() => { if (!token) { navigate("/"); return; } void load(); }, [load, navigate, token]);
  const save = async (seconds: number, widgets: string[]) => { setNotice(""); try { const saved = await api<Config>("/dashboards/supply-chain/config", { method: "PATCH", body: JSON.stringify({ refresh_interval_seconds: seconds, visible_widgets: widgets }) }); setConfig(saved); setNotice("大屏配置已保存"); } catch (error) { setNotice(error instanceof Error ? error.message : "大屏配置保存失败"); } };
  const allowed = ["org_admin", "platform_admin"].includes(organization?.role || "");
  return <AppShell nav="大屏配置" items={NAV_ITEMS} organizationName={organization?.name} onNavigate={(item) => navigate(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    {allowed ? <DashboardConfigurationPage config={config} onSave={save} /> : <main className="access-denied"><h1>无权限访问大屏配置</h1><p>仅组织管理员可修改指标显隐和刷新策略。</p></main>}
  </AppShell>;
}
