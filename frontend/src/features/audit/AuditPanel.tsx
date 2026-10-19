import { EmptyState as Empty } from "../../components/EmptyState";

export type AuditEvent = {
  id: string;
  actor_id?: string;
  actor_role?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  occurred_at: string;
  details: Record<string, unknown>;
  trace_id?: string;
  input_summary?: string;
  result_summary?: string;
  failure_reason?: string;
};

type Props = {
  events: AuditEvent[];
  filter: string;
  setFilter: (value: string) => void;
  selected: AuditEvent | null;
  setSelected: (event: AuditEvent | null) => void;
};

export function AuditPanel({ events, filter, setFilter, selected, setSelected }: Props) {
  const filtered = events.filter((event) => !filter || `${event.action} ${event.resource_type}`.toLowerCase().includes(filter.toLowerCase()));
  return <section className="audit-section">
      <div className="audit-heading"><div><p className="section-kicker">RECENT ACTIVITY</p><h3>最近审计动作</h3></div><input className="audit-filter" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="筛选动作或资源" aria-label="筛选审计动作" /></div>
      {filtered.length ? filtered.map((event) => <button className="audit-row audit-row-button" key={event.id} onClick={() => setSelected(event)}><strong>{event.action}</strong><span>{event.resource_type}</span><time>{new Date(event.occurred_at).toLocaleString("zh-CN")}</time></button>) : <Empty title={filter ? "没有匹配记录" : "暂无审计事件"} copy={filter ? "尝试更换动作或资源关键词。" : "组织操作产生的审计记录会显示在这里。"} />}
      {selected && <section className="detail-panel audit-detail"><div className="panel-heading"><div><p className="section-kicker">AUDIT / DETAIL</p><h3>{selected.action}</h3></div><button className="text-button" onClick={() => setSelected(null)}>关闭</button></div><div className="detail-meta"><span>资源：{selected.resource_type}{selected.resource_id ? ` · ${selected.resource_id}` : ""}</span><span>操作者：{selected.actor_role || "未知角色"}</span><span>发生时间：{new Date(selected.occurred_at).toLocaleString("zh-CN")}</span><span>Trace ID：{selected.trace_id || "未记录"}</span></div><div className="audit-summary-grid"><div><small>输入摘要</small><p>{selected.input_summary || "无"}</p></div><div><small>结果摘要</small><p>{selected.result_summary || "无"}</p></div><div><small>失败原因</small><p>{selected.failure_reason || "无"}</p></div></div><pre className="schema-preview">{JSON.stringify(selected.details || {}, null, 2)}</pre></section>}
  </section>;
}
