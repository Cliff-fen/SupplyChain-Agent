import type {
  AgentStep,
  AnalysisRun,
  KnowledgeBase,
  Source,
} from "../../app/domain-types";

type Props = {
  run: AnalysisRun;
  steps: AgentStep[];
  sources: Source[];
  knowledgeBases: KnowledgeBase[];
  busy: boolean;
  onClose: () => void;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
};

const STEP_LABELS: Record<string, string> = {
  answer_agent: "生成回答",
  answer_verifier: "校验答案",
  approval_gate: "审批确认",
  chart: "生成图表",
  complete: "完成分析",
  context_loader: "加载上下文",
  data_analysis: "数据分析",
  insight: "生成洞察",
  knowledge_research: "检索知识库",
  query: "执行查询",
  rag: "检索指标定义",
  report: "生成报告",
  router: "识别问题类型",
  schema: "读取数据结构",
  sql_guard: "校验 SQL 安全",
  sql_planner: "生成 SQL",
  synthesis_agent: "汇总答案",
};

const STATUS_LABELS: Record<string, string> = {
  archived: "已归档",
  cancelled: "已取消",
  completed: "已完成",
  failed: "失败",
  processing: "处理中",
  queued: "排队中",
  rejected: "已拒绝",
  running: "运行中",
  waiting_approval: "等待审批",
};

const formatStepName = (name: string) =>
  STEP_LABELS[name] || name.replace(/_/g, " ");

const formatStatus = (status: string) => STATUS_LABELS[status] || status;

export function AnalysisRunDetail({
  run,
  steps,
  sources,
  knowledgeBases,
  busy,
  onClose,
  onCancel,
  onRetry,
}: Props) {
  const source = sources.find((item) => item.id === run.data_source_id);
  const knowledgeBase = knowledgeBases.find(
    (item) => item.id === run.knowledge_base_id,
  );
  return (
    <section className="detail-panel analysis-run-detail">
      <div className="panel-heading">
        <div>
          <h3>{run.question}</h3>
          <p className="panel-meta">运行状态：{formatStatus(run.status)}</p>
        </div>
        <div className="analysis-run-actions">
          <button
            className="text-button analysis-session-close"
            onClick={onClose}
          >
            关闭
          </button>
        </div>
      </div>
      <div className="detail-meta">
        <span>运行 ID：{run.id}</span>
        <span>数据源：{source?.name || run.data_source_id || "-"}</span>
        <span>
          知识库：{knowledgeBase?.name || run.knowledge_base_id || "-"}
        </span>
        <span>
          创建时间：{new Date(run.created_at).toLocaleString("zh-CN")}
        </span>
      </div>
      <div className="row-actions analysis-actions">
        {["running", "queued"].includes(run.status) && (
          <button className="secondary-button" onClick={() => onCancel(run.id)}>
            取消分析
          </button>
        )}
        {["failed", "cancelled"].includes(run.status) && (
          <button
            className="primary-button"
            onClick={() => onRetry(run.id)}
            disabled={busy}
          >
            重试分析
          </button>
        )}
      </div>
      {run.sql_draft && (
        <details className="result-detail">
          <summary>SQL 草案</summary>
          <pre className="sql-preview">{run.sql_draft}</pre>
        </details>
      )}
      {run.sql && (
        <details className="result-detail">
          <summary>最终 SQL</summary>
          <pre className="sql-preview">{run.sql}</pre>
        </details>
      )}
      {run.guard_error && (
        <p className="form-error">SQL Guard：{run.guard_error}</p>
      )}
      {run.result && (
        <details className="result-detail">
          <summary>查询结果摘要</summary>
          <pre className="schema-preview">
            {JSON.stringify(run.result, null, 2)}
          </pre>
        </details>
      )}
      <section className="analysis-run-steps">
        <div className="panel-heading">
          <strong>运行轨迹</strong>
          <span className="panel-meta">{steps.length} 个步骤</span>
        </div>
        <div className="step-timeline">
          {steps.length ? steps.map((step) => (
            <article className="step-item" key={step.id}>
              <span className={`status-dot-label ${step.status}`}>
                {formatStatus(step.status)}
              </span>
              <div>
                <strong>{formatStepName(step.name)}</strong>
                <p>{step.input_summary}</p>
                {step.error_message && <small>{step.error_message}</small>}
              </div>
              <time>{step.elapsed_ms ? `${step.elapsed_ms} ms` : "-"}</time>
            </article>
          )) : <p className="detail-hint">该历史运行没有保留阶段记录。请查看运行状态；失败或已取消的任务可重新发起分析。</p>}
        </div>
      </section>
    </section>
  );
}
