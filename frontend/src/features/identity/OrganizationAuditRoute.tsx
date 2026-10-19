import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { Invitation, Member, OrganizationSummary } from "../../app/domain-types";
import type { AuditEvent } from "../audit/AuditPanel";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { OrganizationAuditPage } from "./OrganizationAuditPage";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };

export function OrganizationAuditRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditFilter, setAuditFilter] = useState("");
  const [auditRunId, setAuditRunId] = useState("");
  const [selectedAudit, setSelectedAudit] = useState<AuditEvent | null>(null);
  const [invitationLink, setInvitationLink] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async (filter = auditFilter, runId = auditRunId) => {
    try {
      const query = new URLSearchParams({ limit: "50", ...(filter ? { action: filter } : {}), ...(runId ? { run_id: runId } : {}) });
      const [nextOrganization, nextMembers, nextInvitations, nextAudits] = await Promise.all([api<OrganizationSummary>("/organization"), api<Member[]>("/members"), api<Invitation[]>("/members/invitations"), api<AuditEvent[]>(`/audit?${query}`)]);
      setOrganization(nextOrganization); setMembers(nextMembers); setInvitations(nextInvitations); setAuditEvents(nextAudits);
    } catch (error) { setNotice(error instanceof Error ? error.message : "组织管理数据读取失败"); }
  }, [api, auditFilter, auditRunId]);
  useEffect(() => { if (!token) { navigate("/"); return; } void load(); }, [load, navigate, token]);
  const guarded = ["org_admin", "platform_admin"].includes(organization?.role || "");
  const invite = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); try { const created = await api<Invitation>("/members/invitations", { method: "POST", body: JSON.stringify({ email: form.get("email"), role: form.get("role"), expires_in_days: 7 }) }); if (created.token) setInvitationLink(`${window.location.origin}/overview?invite=${encodeURIComponent(created.token)}`); formElement.reset(); setNotice("邀请已创建，请复制一次性链接并通过可信渠道发送。"); await load(); } catch (error) { setNotice(error instanceof Error ? error.message : "邀请创建失败"); } };
  const roleChange = async (member: Member, role: string) => { try { await api(`/members/${member.user_id}`, { method: "PATCH", body: JSON.stringify({ role }) }); setNotice("成员角色已更新"); await load(); } catch (error) { setNotice(error instanceof Error ? error.message : "成员角色更新失败"); } };
  const toggle = async (member: Member) => { try { await api(`/members/${member.user_id}/status`, { method: "PATCH", body: JSON.stringify({ is_active: !member.is_active }) }); setNotice("成员状态已更新"); await load(); } catch (error) { setNotice(error instanceof Error ? error.message : "成员状态更新失败"); } };
  const resend = async (invitation: Invitation) => { try { const updated = await api<Invitation>(`/members/invitations/${invitation.id}/resend`, { method: "POST" }); if (updated.token) setInvitationLink(`${window.location.origin}/overview?invite=${encodeURIComponent(updated.token)}`); setNotice("邀请已重发，旧链接已失效。"); await load(); } catch (error) { setNotice(error instanceof Error ? error.message : "邀请重发失败"); } };
  const revoke = async (invitation: Invitation) => { try { await api(`/members/invitations/${invitation.id}/revoke`, { method: "POST" }); setNotice("邀请已撤销，历史记录已保留。"); await load(); } catch (error) { setNotice(error instanceof Error ? error.message : "邀请撤销失败"); } };
  const changeAuditFilter = (value: string) => { setAuditFilter(value); void load(value, auditRunId); };
  const changeAuditRun = (value: string) => { setAuditRunId(value); void load(auditFilter, value); };
  return <AppShell nav="组织与审计" items={NAV_ITEMS} organizationName={organization?.name} onNavigate={(item) => navigate(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    {guarded ? <OrganizationAuditPage members={members} invitations={invitations} auditEvents={auditEvents} organization={organization} auditFilter={auditFilter} auditRunId={auditRunId} setAuditFilter={changeAuditFilter} setAuditRunId={changeAuditRun} onInvite={invite} onRoleChange={roleChange} onToggle={toggle} onResend={resend} onRevoke={revoke} selectedAudit={selectedAudit} setSelectedAudit={setSelectedAudit} invitationLink={invitationLink} onDismissInvitationLink={() => setInvitationLink(null)} /> : <main className="access-denied"><h1>无权限访问组织与审计</h1><p>仅组织管理员可管理成员、邀请和配额。</p></main>}
  </AppShell>;
}
