import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { KnowledgeBase, Member, OrganizationSummary, PermissionMatrix, Report, Source } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { ProjectManagementPage } from "./ProjectManagementPage";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };
type Quotas = { max_concurrent_analyses: number; daily_analysis_runs: number; max_document_size_mb: number; retention_days: number };
const emptyQuotas: Quotas = { max_concurrent_analyses: 4, daily_analysis_runs: 100, max_document_size_mb: 10, retention_days: 90 };

export function ProjectManagementRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [permissions, setPermissions] = useState<PermissionMatrix | null>(null);
  const [quotas, setQuotas] = useState<Quotas>(emptyQuotas);
  const [notice, setNotice] = useState("");
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async () => { try { const [nextOrganization, nextMembers, nextSources, nextKnowledge, nextReports, nextPermissions] = await Promise.all([api<OrganizationSummary>("/organization"), api<Member[]>("/members"), api<Source[]>("/data-sources"), api<KnowledgeBase[]>("/knowledge-bases?page=1&page_size=100"), api<Report[]>("/reports"), api<PermissionMatrix>("/organization/permissions")]); setOrganization(nextOrganization); setMembers(nextMembers); setSources(nextSources); setKnowledgeBases(nextKnowledge); setReports(nextReports); setPermissions(nextPermissions); setQuotas((current) => ({ ...current, ...nextOrganization.quota })); } catch (error) { setNotice(error instanceof Error ? error.message : "项目管理数据读取失败"); } }, [api]);
  useEffect(() => { if (!token) { navigate("/"); return; } void load(); }, [load, navigate, token]);
  const updateOwner = async (event: FormEvent) => { event.preventDefault(); if (!organization?.owner_user_id) { setNotice("请选择负责人"); return; } try { const saved = await api<OrganizationSummary>("/organization/settings", { method: "PATCH", body: JSON.stringify({ owner_user_id: organization.owner_user_id }) }); setOrganization(saved); setNotice("组织负责人已更新"); } catch (error) { setNotice(error instanceof Error ? error.message : "负责人保存失败"); } };
  const updateQuotas = async (event: FormEvent) => { event.preventDefault(); try { const saved = await api<Record<string, number>>("/organization/quotas", { method: "PATCH", body: JSON.stringify(quotas) }); setQuotas((current) => ({ ...current, ...saved })); setNotice("组织配额已保存"); } catch (error) { setNotice(error instanceof Error ? error.message : "配额保存失败"); } };
  return <AppShell nav="项目管理" items={NAV_ITEMS} organizationName={organization?.name} onNavigate={(item) => navigate(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    <ProjectManagementPage organization={organization} members={members} sources={sources} knowledgeBases={knowledgeBases} reports={reports} permissions={permissions} quotas={quotas} setQuotas={setQuotas} onNavigate={(item) => navigate(paths[item as NavItem] || "/overview")} onUpdateOwner={updateOwner} onOwnerChange={(userId) => setOrganization((current) => current ? { ...current, owner_user_id: userId } : current)} onUpdateQuotas={updateQuotas} />
  </AppShell>;
}
