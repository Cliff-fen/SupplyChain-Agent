import { FormEvent, useEffect, useMemo, useState } from "react";
import { EmptyState } from "../../components/EmptyState";
import type { AuditEvent } from "../audit/AuditPanel";

type Member = { user_id: string; display_name: string; email: string; role: string; is_active: boolean };
type Invitation = { id: string; email: string; role: string; status: string; expires_at: string; created_at: string; token?: string };
type Organization = { quota: Record<string, number>; quota_usage: Record<string, number>; member_count: number; active_member_count: number };

type Props = {
  members: Member[];
  invitations: Invitation[];
  auditEvents: AuditEvent[];
  organization: Organization | null;
  auditFilter: string;
  auditRunId: string;
  setAuditFilter: (value: string) => void;
  setAuditRunId: (value: string) => void;
  onInvite: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onRoleChange: (member: Member, role: string) => Promise<void>;
  onToggle: (member: Member) => Promise<void>;
  onResend: (invitation: Invitation) => Promise<void>;
  onRevoke: (invitation: Invitation) => Promise<void>;
  selectedAudit: AuditEvent | null;
  setSelectedAudit: (event: AuditEvent | null) => void;
  invitationLink: string | null;
  onDismissInvitationLink: () => void;
};

const roleLabels: Record<string, string> = { org_admin: "组织管理员", analyst: "分析师", viewer: "只读成员", platform_admin: "平台管理员" };

function Usage({ label, value, limit, unit = "" }: { label: string; value: number; limit?: number; unit?: string }) {
  const ratio = limit ? Math.min(100, Math.round((value / limit) * 100)) : 0;
  return <article className="quota-card"><div className="quota-card-top"><span>{label}</span><strong>{value.toLocaleString("zh-CN")}{unit} <small>/ {limit?.toLocaleString("zh-CN") ?? "—"}{unit}</small></strong></div><div className="quota-track"><span style={{ width: `${ratio}%` }} /></div><small className={ratio >= 85 ? "quota-warning" : ""}>{ratio >= 85 ? "接近组织上限" : `${ratio}% 已使用`}</small></article>;
}

export function OrganizationCenter(props: Props) {
  const [tab, setTab] = useState<"members" | "invitations" | "quota" | "audit">("members");
  const [memberFilter, setMemberFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [pendingToggle, setPendingToggle] = useState<Member | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<Invitation | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  useEffect(() => setLinkCopied(false), [props.invitationLink]);
  const filteredMembers = useMemo(() => props.members.filter((member) => {
    const matchesText = !memberFilter || `${member.display_name} ${member.email}`.toLowerCase().includes(memberFilter.toLowerCase());
    const matchesStatus = statusFilter === "all" || (statusFilter === "active" ? member.is_active : !member.is_active);
    return matchesText && matchesStatus;
  }), [props.members, memberFilter, statusFilter]);
  const filteredAudits = props.auditEvents.filter((event) => !props.auditFilter || `${event.action} ${event.resource_type} ${event.actor_role || ""}`.toLowerCase().includes(props.auditFilter.toLowerCase())).filter((event) => !props.auditRunId || event.resource_id?.includes(props.auditRunId));
  const pending = props.invitations.filter((item) => item.status === "pending");
  const quota = props.organization?.quota || {};
  const usage = props.organization?.quota_usage || {};

  const copyInvitationLink = async () => {
    if (!props.invitationLink) return;
    await navigator.clipboard.writeText(props.invitationLink);
    setLinkCopied(true);
  };

  return <section className="org-center">
    <div className="org-overview"><div><span className="org-eyebrow">ORGANIZATION CONTROL</span><h3>团队与访问控制</h3><p>管理成员、邀请、用量和组织级审计。</p></div><div className="org-stats"><span><strong>{props.organization?.active_member_count ?? 0}</strong><small>活跃成员</small></span><span><strong>{pending.length}</strong><small>待处理邀请</small></span></div></div>
    <div className="org-tabs" role="tablist" aria-label="组织管理分区">{([["members", "成员与邀请"], ["invitations", "邀请管理"], ["quota", "配额与用量"], ["audit", "审计日志"]] as const).map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "org-tab active" : "org-tab"} onClick={() => setTab(id)}>{label}{id === "invitations" && pending.length > 0 ? <b>{pending.length}</b> : null}</button>)}</div>

    {tab === "members" && <div className="org-section"><form className="invite-composer" onSubmit={props.onInvite}><div><span className="section-kicker">ADD MEMBER</span><strong>邀请新的团队成员</strong><small>邀请链接将在 7 天后失效。</small></div><input required type="email" name="email" placeholder="name@company.com" aria-label="成员邮箱" /><select name="role" defaultValue="viewer" aria-label="成员角色"><option value="viewer">只读成员</option><option value="analyst">分析师</option><option value="org_admin">组织管理员</option></select><button className="primary-button">发送邀请 <span>→</span></button></form><div className="list-toolbar"><div><strong>成员目录</strong><span>{filteredMembers.length} 人</span></div><div className="toolbar-controls"><input value={memberFilter} onChange={(event) => setMemberFilter(event.target.value)} placeholder="搜索姓名或邮箱" aria-label="搜索成员" /><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="筛选成员状态"><option value="all">全部状态</option><option value="active">已启用</option><option value="inactive">已停用</option></select></div></div>{filteredMembers.length ? <div className="member-table"><div className="member-table-head"><span>成员</span><span>角色</span><span>状态</span><span>操作</span></div>{filteredMembers.map((member) => <article className={`member-table-row ${member.is_active ? "" : "is-inactive"}`} key={member.user_id}><div className="member-identity"><span className="member-avatar">{(member.display_name || member.email).slice(0, 1).toUpperCase()}</span><span><strong>{member.display_name}</strong><small>{member.email}</small></span></div><select value={member.role} onChange={(event) => void props.onRoleChange(member, event.target.value)} aria-label={`${member.email}角色`}><option value="viewer">只读成员</option><option value="analyst">分析师</option><option value="org_admin">组织管理员</option></select><span className={`status-chip ${member.is_active ? "" : "muted"}`}><i />{member.is_active ? "已启用" : "已停用"}</span><button className="row-action" onClick={() => setPendingToggle(member)}>{member.is_active ? "停用成员" : "重新启用"}</button></article>)}</div> : <EmptyState title="暂无匹配成员" copy="调整搜索条件，或从上方邀请新的团队成员。" />}</div>}

    {tab === "invitations" && <div className="org-section"><div className="section-heading-row"><div><span className="section-kicker">INVITATIONS</span><h3>邀请管理</h3><p>查看邀请状态并处理即将过期的邀请。</p></div><span className="count-badge">{pending.length} 待处理</span></div>{props.invitations.length ? <div className="invitation-list">{props.invitations.map((item) => <article className="invitation-row" key={item.id}><div className="invitation-icon">@</div><div><strong>{item.email}</strong><p>{roleLabels[item.role] || item.role} · {item.status === "pending" ? `截止 ${new Date(item.expires_at).toLocaleDateString("zh-CN")}` : item.status === "revoked" ? "已撤销" : item.status}</p></div><span className={`status-chip ${item.status === "pending" ? "" : "muted"}`}>{item.status === "pending" ? "待处理" : item.status === "revoked" ? "已撤销" : item.status}</span>{item.status === "pending" && <div className="invitation-actions"><button className="secondary-button" onClick={() => void props.onResend(item)}>重新发送</button><button className="row-action danger-action" onClick={() => setPendingRevoke(item)}>撤销邀请</button></div>}</article>)}</div> : <EmptyState title="暂无邀请" copy="成员邀请发送后会显示在这里。" />}</div>}

    {tab === "quota" && <div className="org-section"><div className="section-heading-row"><div><span className="section-kicker">QUOTA & USAGE</span><h3>组织配额与用量</h3><p>用量统计按当前组织计算，接近上限时会提前提示。</p></div><span className="data-source-note">实时统计</span></div><div className="quota-grid"><Usage label="并发分析" value={usage.concurrent_analyses || 0} limit={quota.max_concurrent_analyses} /><Usage label="今日分析" value={usage.daily_analysis_runs || 0} limit={quota.daily_analysis_runs} /><Usage label="文档存储" value={Math.round((usage.document_storage_bytes || 0) / 1024)} limit={Math.round((quota.max_document_storage_mb || 10) * 1024)} unit=" KB" /><Usage label="报告文件" value={usage.report_storage_files || 0} limit={quota.max_report_files} unit=" 个" /></div></div>}

    {tab === "audit" && <div className="org-section"><div className="section-heading-row"><div><span className="section-kicker">AUDIT TRAIL</span><h3>审计日志</h3><p>关键操作会被记录，支持按动作和运行上下文追溯。</p></div><span className="data-source-note">{filteredAudits.length} 条记录</span></div><div className="audit-toolbar"><input value={props.auditFilter} onChange={(event) => props.setAuditFilter(event.target.value)} placeholder="搜索动作、资源或角色" aria-label="筛选审计动作" /><input value={props.auditRunId} onChange={(event) => props.setAuditRunId(event.target.value)} placeholder="运行 ID" aria-label="按运行 ID 筛选审计" /></div>{filteredAudits.length ? <div className="audit-table">{filteredAudits.map((event) => <button className="audit-event-row" key={event.id} onClick={() => props.setSelectedAudit(event)}><span className="audit-event-mark" /><span><strong>{event.action}</strong><small>{event.resource_type}{event.resource_id ? ` · ${event.resource_id.slice(0, 12)}` : ""}</small></span><span className="audit-event-actor">{event.actor_role || "系统"}</span><time>{new Date(event.occurred_at).toLocaleString("zh-CN")}</time></button>)}</div> : <EmptyState title="暂无审计记录" copy="组织操作发生后，事件会自动出现在这里。" />}</div>}
    {props.selectedAudit && <div className="drawer-backdrop" role="presentation" onClick={() => props.setSelectedAudit(null)}><aside className="detail-drawer" role="dialog" aria-modal="true" aria-label="审计事件详情" onClick={(event) => event.stopPropagation()}><div className="drawer-header"><div><span className="section-kicker">AUDIT / DETAIL</span><h3>{props.selectedAudit.action}</h3></div><button className="icon-button" onClick={() => props.setSelectedAudit(null)} aria-label="关闭详情">×</button></div><dl className="audit-detail-grid"><dt>资源</dt><dd>{props.selectedAudit.resource_type} · {props.selectedAudit.resource_id || "—"}</dd><dt>操作者角色</dt><dd>{props.selectedAudit.actor_role || "系统"}</dd><dt>发生时间</dt><dd>{new Date(props.selectedAudit.occurred_at).toLocaleString("zh-CN")}</dd><dt>Trace ID</dt><dd className="trace-value">{props.selectedAudit.trace_id || "—"}</dd><dt>失败原因</dt><dd>{props.selectedAudit.failure_reason || "无"}</dd></dl></aside></div>}
    {pendingToggle && <div className="modal-backdrop" role="presentation"><section className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="member-confirm-title"><span className="section-kicker">MEMBER ACCESS</span><h3 id="member-confirm-title">{pendingToggle.is_active ? "停用这个成员？" : "重新启用这个成员？"}</h3><p>{pendingToggle.email} 将{pendingToggle.is_active ? "无法继续访问当前组织资源。" : "恢复当前组织访问权限。"}</p><div className="confirm-actions"><button className="secondary-button" onClick={() => setPendingToggle(null)}>取消</button><button className="primary-button" onClick={() => { const member = pendingToggle; setPendingToggle(null); void props.onToggle(member); }}>{pendingToggle.is_active ? "确认停用" : "确认启用"}</button></div></section></div>}
    {pendingRevoke && <div className="modal-backdrop" role="presentation" onClick={() => setPendingRevoke(null)}><section className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="invite-revoke-title" onClick={(event) => event.stopPropagation()}><span className="section-kicker">INVITATION ACCESS</span><h3 id="invite-revoke-title">撤销这条邀请？</h3><p>{pendingRevoke.email} 将无法再使用当前邀请链接加入组织。这个操作不会删除历史记录。</p><div className="confirm-actions"><button className="secondary-button" onClick={() => setPendingRevoke(null)}>取消</button><button className="primary-button danger-button" onClick={() => { const invitation = pendingRevoke; setPendingRevoke(null); void props.onRevoke(invitation); }}>确认撤销</button></div></section></div>}
    {props.invitationLink && <div className="modal-backdrop" role="presentation"><section className="confirm-modal invitation-link-modal" role="dialog" aria-modal="true" aria-labelledby="invitation-link-title"><h3 id="invitation-link-title">复制一次性邀请链接</h3><p>此链接只在当前窗口展示。请通过可信渠道发送给受邀成员；重发或撤销后，旧链接立即失效。</p><input readOnly value={props.invitationLink} aria-label="一次性邀请链接" onFocus={(event) => event.currentTarget.select()} /><div className="confirm-actions"><button className="secondary-button" onClick={props.onDismissInvitationLink}>关闭</button><button className="primary-button" onClick={() => void copyInvitationLink()}>{linkCopied ? "已复制" : "复制链接"}</button></div></section></div>}
  </section>;
}
