import { useMemo, useState } from "react";
import { EmptyState } from "../../components/EmptyState";
import { Pagination } from "../../components/Pagination";

export type PlatformOrganization = {
  id: string;
  slug: string;
  name: string;
  owner_name?: string | null;
  member_count: number;
  active_member_count: number;
  data_source_count: number;
  knowledge_base_count: number;
  report_count: number;
  created_at: string;
  is_active: boolean;
  quota: Record<string, number>;
};

type Props = { organizations: PlatformOrganization[]; onToggle: (organization: PlatformOrganization) => Promise<void>; onRename: (organization: PlatformOrganization, name: string) => Promise<void> };

export function OrganizationAdminPanel({ organizations, onToggle, onRename }: Props) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(null);
  const filtered = useMemo(() => organizations.filter((item) => `${item.name} ${item.slug}`.toLowerCase().includes(search.toLowerCase())), [organizations, search]);
  return <section className="platform-admin-panel">
    <div className="section-heading-row"><div><span className="section-kicker">PLATFORM / TENANTS</span><h3>企业组织管理</h3><p>平台管理员可查看和维护所有企业的访问状态、负责人和资源概况。</p></div><span className="data-source-note">仅平台管理员可见</span></div>
    <div className="list-toolbar"><div><strong>企业目录</strong><span>{filtered.length} 家企业</span></div><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="搜索企业名称或标识" aria-label="搜索企业" /></div>
    {filtered.length ? <div className="tenant-table"><div className="tenant-table-head"><span>企业</span><span>负责人</span><span>资源</span><span>状态</span><span>操作</span></div>{filtered.slice((page - 1) * 10, page * 10).map((item) => { const working = activeOrganizationId === item.id; return <article className={`tenant-table-row ${item.is_active ? "" : "is-inactive"}`} key={item.id}><div><strong>{item.name}</strong><small>{item.slug}</small></div><span>{item.owner_name || "未设置"}</span><span>{item.member_count} 成员 · {item.data_source_count} 数据源 · {item.knowledge_base_count} 知识库</span><span className={`status-chip ${item.is_active ? "" : "muted"}`}><i />{item.is_active ? "已启用" : "已停用"}</span><div className="row-actions"><button className="row-action" disabled={working} onClick={() => { const name = window.prompt("修改企业名称", item.name); if (name && name.trim() !== item.name) { setActiveOrganizationId(item.id); void onRename(item, name.trim()).finally(() => setActiveOrganizationId(null)); } }}>{working ? "处理中..." : "编辑"}</button><button className={`row-action ${item.is_active ? "danger-action" : ""}`} disabled={working} onClick={() => { setActiveOrganizationId(item.id); void onToggle(item).finally(() => setActiveOrganizationId(null)); }}>{working ? "处理中..." : item.is_active ? "停用" : "启用"}</button></div></article>; })}</div> : <EmptyState title="暂无企业" copy="没有找到匹配的企业组织。" />}
    {filtered.length > 10 && <Pagination page={page} pageSize={10} total={filtered.length} onPageChange={setPage} onPageSizeChange={() => undefined} />}
  </section>;
}
