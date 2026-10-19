import type { FormEvent } from "react";
import type { AnalysisResult } from "../../app/domain-types";
import type { AnalysisStage, StreamActivity } from "./analysis-stream";

type Resource = { id: string; name: string; status?: string };
type Props = { question: string; setQuestion: (value: string) => void; loading: boolean; onSubmit: (event: FormEvent) => void; sources?: Resource[]; knowledgeBases?: Resource[]; sourceId?: string; knowledgeBaseId?: string; setSourceId?: (value: string) => void; setKnowledgeBaseId?: (value: string) => void; stages?: AnalysisStage[]; activity?: StreamActivity[]; citationCount?: number; rowCount?: number; chartReady?: boolean; error?: string; result: AnalysisResult | null; events?: string[]; messages?: unknown[]; onDownloadReport?: (id: string) => Promise<void> };
const titles = { facts: "事实", risks: "风险", recommendations: "建议" } as const;

export function AnalysisPanel(p: Props) {
  const rows = p.result?.result?.rows || [];
  const insight = p.result?.result?.insight;
  const citationCount = p.citationCount ?? p.result?.result?.citations?.length ?? 0;
  const hasEvidence = rows.length > 0 || citationCount > 0;
  const hasStructuredInsights = (["facts", "risks", "recommendations"] as const).some(
    (key) => Boolean(p.result?.result?.insights?.[key]?.length),
  );
  const summary = p.result?.result?.direct_answer || (hasStructuredInsights
    ? `已验证 ${rows.length} 条结果。下方按事实、风险和建议呈现可执行信息。`
    : insight || "分析已完成。");
  const activeSources = (p.sources || []).filter((source) => !source.status || source.status === "active");
  const stages = p.stages || [];
  const current = stages.find((stage) => stage.status === "running");
  const activity = p.activity || [];
  return <section className="analysis-workbench">
    <header className="analysis-header"><div><h3>供应链分析</h3><p>基于已授权数据与口径，生成可追溯的业务判断。</p></div><span className="live-indicator"><i />{p.loading ? current?.name || "正在准备分析" : "准备就绪"}</span></header>
    <div className="analysis-resources"><label htmlFor="analysis-source">数据源<select id="analysis-source" value={p.sourceId || ""} onChange={(event) => p.setSourceId?.(event.target.value)}><option value="">选择可用数据源</option>{activeSources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}</select></label><label htmlFor="analysis-knowledge-base">知识库<select id="analysis-knowledge-base" value={p.knowledgeBaseId || ""} onChange={(event) => p.setKnowledgeBaseId?.(event.target.value)}><option value="">选择知识库</option>{(p.knowledgeBases || []).map((knowledgeBase) => <option key={knowledgeBase.id} value={knowledgeBase.id}>{knowledgeBase.name}</option>)}</select></label></div>
    <form onSubmit={p.onSubmit} className="analysis-composer"><label htmlFor="analysis-question">分析问题</label><div><input id="analysis-question" value={p.question} onChange={(event) => p.setQuestion(event.target.value)} placeholder="例如：哪些工厂的生产达成率需要优先处理？" required /><button className="primary-button" disabled={p.loading || !p.sourceId || !p.knowledgeBaseId}>{p.loading ? "分析中…" : "开始分析"}</button></div></form>
    {(p.loading || activity.length > 0 || p.error || p.events?.length) && <section className="analysis-status-panel" aria-live="polite"><div className="panel-heading"><div><strong>实时运行状态</strong><p>{p.error || current?.detail || activity.at(-1)?.message || "已提交，正在等待分析服务响应"}</p></div><span>{p.loading ? "实时更新中" : p.error ? "运行失败" : "运行记录"}</span></div><ol className="analysis-stage-list">{stages.map((stage) => <li key={stage.id} className={stage.status}><span aria-hidden="true" /><div><strong>{stage.name}</strong><small>{stage.detail || (stage.status === "pending" ? "等待执行" : stage.status === "completed" ? "已完成" : "处理中")}</small></div></li>)}</ol>{activity.length > 0 && <div className="analysis-activity" aria-label="实时事件"><strong>刚刚发生</strong>{activity.slice(-4).reverse().map((item, index) => <p key={`${item.event}-${index}`}><span>{item.event}</span>{item.message}</p>)}</div>}{!activity.length && p.events?.length ? <div className="analysis-activity">{p.events.slice(-4).reverse().map((event, index) => <p key={index}>{event}</p>)}</div> : null}</section>}
    {p.result && <section className="analysis-evidence"><div className="result-heading"><div><h3>{hasEvidence ? "分析结论" : "未返回可用于判断的数据"}</h3><p className="analysis-summary">{hasEvidence ? summary : "本次查询没有结果行或知识引用，因此未生成确定性结论或图表。请调整筛选范围后重试。"}</p><p className="analysis-result-meta">已验证 {rows.length} 条结果，引用 {citationCount} 条知识依据。</p></div><span className="analysis-status">{hasEvidence ? "结论已生成" : "空结果"}</span></div>{hasEvidence && <>{hasStructuredInsights && <div className="insight-grid">{(["facts", "risks", "recommendations"] as const).map((key) => p.result?.result?.insights?.[key]?.length ? <section className="insight-block" key={key}><strong>{titles[key]}</strong>{p.result.result.insights[key]?.map((item, index) => <p key={index}>{item}</p>)}</section> : null)}</div>}{rows.length > 0 && p.chartReady && <p className="detail-hint">关键图表已生成，可在导出的报告中查看完整图形。</p>}</>}<details className="result-detail"><summary>分析证据</summary><p className="detail-hint">引用 {citationCount} 条，查询结果 {p.rowCount ?? rows.length} 行。</p>{p.result.sql_draft && <><h4>SQL 草案</h4><pre className="sql-preview">{p.result.sql_draft}</pre></>}{p.result.sql && <><h4>最终 SQL</h4><pre className="sql-preview">{p.result.sql}</pre></>}{rows.length > 0 && <details className="result-detail"><summary>原始查询行（前 {Math.min(20, rows.length)} / {rows.length}）</summary><pre className="schema-preview">{JSON.stringify(rows.slice(0, 20), null, 2)}</pre></details>}</details></section>}
  </section>;
}
