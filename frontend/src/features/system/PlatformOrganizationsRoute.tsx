import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { OrganizationSummary } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { PlatformOrganizationsPage } from "./PlatformOrganizationsPage";
import type { PlatformOrganization } from "./OrganizationAdminPanel";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };

export function PlatformOrganizationsRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [organizations, setOrganizations] = useState<PlatformOrganization[]>([]);
  const [notice, setNotice] = useState("");
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async () => { try { const [nextOrganization, items] = await Promise.all([api<OrganizationSummary>("/organization"), api<PlatformOrganization[]>("/platform/organizations?page=1&page_size=100")]); setOrganization(nextOrganization); setOrganizations(items); } catch (error) { setNotice(error instanceof Error ? error.message : "企业目录读取失败"); } }, [api]);
  useEffect(() => { if (!token) { navigate("/"); return; } void load(); }, [load, navigate, token]);
  const update = async (item: PlatformOrganization, path: string, body: unknown) => { try { const saved = await api<PlatformOrganization>(path, { method: path.endsWith("/status") ? "POST" : "PATCH", body: JSON.stringify(body) }); setOrganizations((current) => current.map((entry) => entry.id === saved.id ? saved : entry)); } catch (error) { setNotice(error instanceof Error ? error.message : "企业更新失败"); } };
  const allowed = organization?.role === "platform_admin";
  return <AppShell nav="企业管理" items={NAV_ITEMS} organizationName={organization?.name} onNavigate={(item) => navigate(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    {allowed ? <PlatformOrganizationsPage organizations={organizations} onToggle={(item) => update(item, `/platform/organizations/${item.id}/status`, { is_active: !item.is_active })} onRename={(item, name) => update(item, `/platform/organizations/${item.id}`, { name })} /> : <main className="access-denied"><h1>无权限访问企业管理</h1><p>仅平台管理员可管理企业组织。</p></main>}
  </AppShell>;
}
