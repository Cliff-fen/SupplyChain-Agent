import { DataView } from "../../components/DataView";
import { Pagination } from "../../components/Pagination";
import type { FormEvent } from "react";
import type { AgentStep, AnalysisResult, AnalysisRun, KnowledgeBase, Source } from "../../app/domain-types";
import { AnalysisPanel } from "./AnalysisPanel";
import { AnalysisHistory } from "./AnalysisHistory";
import { AnalysisRunDetail } from "./AnalysisRunDetail";

type Message = { role: "user" | "assistant"; content: string; created_at: string };
type Props = {
  conversationId: string; messages: Message[]; onClearContext: () => void; onNewConversation: () => void;
  question: string; setQuestion: (value: string) => void; events: string[]; result: AnalysisResult | null; busy: boolean;
  onSubmit: (event: FormEvent) => void; onDownloadReport: (id: string) => Promise<void>;
  sources: Source[]; knowledgeBases: KnowledgeBase[]; sourceId: string; knowledgeBaseId: string;
  setSourceId: (value: string) => void; setKnowledgeBaseId: (value: string) => void;
  runs: AnalysisRun[]; page: number; pageSize: number; hasMore: boolean; setPage: (value: number) => void; setPageSize: (value: number) => void;
  onOpenRun: (id: string) => void; selectedRun: AnalysisRun | null; steps: AgentStep[]; onCloseRun: () => void; onCancelRun: (id: string) => void; onRetryRun: (id: string) => void;
};

export function AnalysisSessionPage(props: Props) {
  const total = (props.page - 1) * props.pageSize + props.runs.length + (props.hasMore ? 1 : 0);
  return <DataView kicker="ANALYSIS / AGENT TRACE" title="分析会话" copy="查看模型、RAG、SQL Guard 和报告生成轨迹。">
    <div className="conversation-toolbar"><div><span className="section-kicker">CONVERSATION / {props.conversationId.slice(0, 8)}</span><strong>供应链分析会话</strong><small>{props.messages.length ? `${props.messages.length} 条上下文消息` : "尚未开始对话"}</small></div><div className="row-actions"><button className="secondary-button" onClick={props.onClearContext} disabled={!props.messages.length}>清空上下文</button><button className="primary-button" onClick={props.onNewConversation}>新建会话 <span>＋</span></button></div></div>
    <AnalysisPanel question={props.question} setQuestion={props.setQuestion} events={props.events} result={props.result} loading={props.busy} onSubmit={props.onSubmit} onDownloadReport={props.onDownloadReport} messages={props.messages} sources={props.sources} knowledgeBases={props.knowledgeBases} sourceId={props.sourceId} knowledgeBaseId={props.knowledgeBaseId} setSourceId={props.setSourceId} setKnowledgeBaseId={props.setKnowledgeBaseId} />
    {props.runs.length > 0 && <><AnalysisHistory runs={props.runs} onOpen={props.onOpenRun} /><Pagination page={props.page} pageSize={props.pageSize} total={total} onPageChange={props.setPage} onPageSizeChange={(size) => { props.setPageSize(size); props.setPage(1); }} /></>}
    {props.selectedRun && <AnalysisRunDetail run={props.selectedRun} steps={props.steps} sources={props.sources} knowledgeBases={props.knowledgeBases} busy={props.busy} onClose={props.onCloseRun} onCancel={props.onCancelRun} onRetry={props.onRetryRun} />}
  </DataView>;
}
