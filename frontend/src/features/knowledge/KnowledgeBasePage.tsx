import type { FormEvent } from "react";
import { DataView } from "../../components/DataView";
import { Pagination } from "../../components/Pagination";
import { EmptyState } from "../../components/EmptyState";
import type {
  Citation,
  Document,
  DocumentSource,
  KnowledgeBase,
  KnowledgeDetail,
} from "../../app/domain-types";
import { KnowledgeCard } from "./KnowledgeCard";
import { DocumentTaskList } from "./DocumentTaskList";
import type { DocumentTaskRow } from "./DocumentTaskList";
type Filter = { name: string; status: string };
type Metadata = {
  metric_name: string;
  metric_definition: string;
  metric_formula: string;
  metric_unit: string;
  applicable_factories: string[];
  applicable_product_lines: string[];
  effective_from: string | null;
};
type Props = {
  filter: Filter;
  setFilter: (filter: Filter) => void;
  page: number;
  pageSize: number;
  hasMore: boolean;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  knowledgeBases: KnowledgeBase[];
  documents: Document[];
  busy: boolean;
  onCreate: (event: FormEvent<HTMLFormElement>) => void;
  onUpload: (event: FormEvent<HTMLFormElement>, id: string) => Promise<void>;
  onAnalyze: (name: string) => void;
  onManage: (id: string) => void;
  selected: KnowledgeDetail | null;
  onCloseDetail: () => void;
  onToggleArchive: () => void;
  onRequestArchive: () => void;
  onRequestDelete: () => void;
  onUpdate: (event: FormEvent<HTMLFormElement>) => void;
  query: string;
  setQuery: (query: string) => void;
  onSearch: (event: FormEvent) => void;
  citations: Citation[];
  role?: string;
  onSource: (document: DocumentTaskRow) => void;
  onRetry: (id: string) => void;
  onCancel: (id: string) => void;
  onArchiveDocument: (document: DocumentTaskRow) => void;
  onDeleteDocument: (document: DocumentTaskRow) => void;
  onReplace: (document: DocumentTaskRow, file: File) => Promise<void>;
  onMetadata: (document: DocumentTaskRow, metadata: Metadata) => Promise<void>;
  source: DocumentSource | null;
  onCloseSource: () => void;
};
export function KnowledgeBasePage(p: Props) {
  const total =
    (p.page - 1) * p.pageSize + p.knowledgeBases.length + (p.hasMore ? 1 : 0);
  return (
    <DataView
      kicker="KNOWLEDGE / CITATIONS"
      title="知识库"
      copy="维护指标口径、制造规则与可追溯引用。"
    >
      <div className="report-filters knowledge-filters">
        <input
          value={p.filter.name}
          onChange={(event) => {
            p.setPage(1);
            p.setFilter({ ...p.filter, name: event.target.value });
          }}
          placeholder="按知识库名称筛选"
          aria-label="按知识库名称筛选"
        />
        <select
          value={p.filter.status}
          onChange={(event) => {
            p.setPage(1);
            p.setFilter({ ...p.filter, status: event.target.value });
          }}
          aria-label="按知识库状态筛选"
        >
          <option value="">全部状态</option>
          <option value="active">启用</option>
          <option value="archived">已归档</option>
        </select>
      </div>
      <form className="inline-form knowledge-create" onSubmit={p.onCreate}>
        <div>
          <label htmlFor="knowledge-name">新建知识库</label>
          <input
            id="knowledge-name"
            name="name"
            required
            placeholder="例如：供应链演示口径"
            aria-label="知识库名称"
          />
        </div>
        <div>
          <label htmlFor="knowledge-description">用途说明</label>
          <input
            id="knowledge-description"
            name="description"
            placeholder="指标定义、制度或制造规则"
            aria-label="知识库描述"
          />
        </div>
        <button className="primary-button">
          创建知识库 <span>+</span>
        </button>
      </form>
      {p.knowledgeBases.length ? (
        <div className="knowledge-grid">
          {p.knowledgeBases.map((item) => (
            <KnowledgeCard
              key={item.id}
              knowledgeBase={item}
              documents={p.documents.filter(
                (doc) => doc.knowledge_base_id === item.id,
              )}
              onUpload={p.onUpload}
              onAnalyze={() => p.onAnalyze(item.name)}
              onManage={() => p.onManage(item.id)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title="从第一套口径开始"
          copy="创建知识库后上传 PDF、Markdown 或 TXT 文档。"
        />
      )}
      <Pagination
        page={p.page}
        pageSize={p.pageSize}
        total={total}
        onPageChange={p.setPage}
        onPageSizeChange={(size) => {
          p.setPageSize(size);
          p.setPage(1);
        }}
      />
      {p.selected && (
        <section className="knowledge-detail">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">KNOWLEDGE / DETAIL</p>
              <h3>{p.selected.name}</h3>
              <p>{p.selected.description || "暂无用途说明"}</p>
            </div>
            <div className="row-actions">
              <button
                className="secondary-button"
                onClick={
                  p.selected.is_archived
                    ? p.onToggleArchive
                    : p.onRequestArchive
                }
              >
                {p.selected.is_archived ? "恢复知识库" : "归档知识库"}
              </button>
              {p.selected.is_archived &&
                !p.documents.some(
                  (doc) => doc.knowledge_base_id === p.selected?.id,
                ) && (
                  <button
                    className="text-button danger-action"
                    onClick={p.onRequestDelete}
                  >
                    永久删除空知识库
                  </button>
                )}
              <button className="text-button" onClick={p.onCloseDetail}>
                关闭
              </button>
            </div>
          </div>
          <form className="knowledge-edit-form" onSubmit={p.onUpdate}>
            <label>
              知识库名称
              <input name="name" defaultValue={p.selected.name} required />
            </label>
            <label>
              用途说明
              <input name="description" defaultValue={p.selected.description} />
            </label>
            <button className="secondary-button">保存信息</button>
          </form>
          <form className="knowledge-search" onSubmit={p.onSearch}>
            <input
              value={p.query}
              onChange={(event) => p.setQuery(event.target.value)}
              placeholder="预览检索，例如：生产达成率口径"
              aria-label="知识库检索预览"
            />
            <button className="primary-button">检索引用</button>
          </form>
          {p.citations.length ? (
            <div className="citation-list">
              {p.citations.map((citation, index) => (
                <article
                  className="citation-item"
                  key={`${citation.document_id}-${index}`}
                >
                  <strong>{citation.document_name || "文档片段"}</strong>
                  <span>
                    相似度{" "}
                    {typeof citation.score === "number"
                      ? citation.score.toFixed(3)
                      : "—"}
                  </span>
                  <p>{citation.text || "暂无片段文本"}</p>
                  <small>
                    {citation.location
                      ? JSON.stringify(citation.location)
                      : "未提供位置"}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <p className="detail-hint">
              检索结果会显示文档、片段、相似度和引用位置。
            </p>
          )}
          <DocumentTaskList
            documents={p.documents}
            knowledgeBaseId={p.selected.id}
            organizationRole={p.role}
            onSource={p.onSource}
            onRetry={p.onRetry}
            onCancel={p.onCancel}
            onArchive={p.onArchiveDocument}
            onDelete={p.onDeleteDocument}
            onReplace={p.onReplace}
            onMetadata={p.onMetadata}
          />
          {p.source && (
            <section className="detail-panel document-source-panel">
              <div className="panel-heading">
                <div>
                  <p className="section-kicker">DOCUMENT / SOURCE</p>
                  <h3>
                    {p.source.filename} · v{p.source.version}
                  </h3>
                  <p>
                    {p.source.category || "other"} · {p.source.chunks.length}{" "}
                    个分块
                  </p>
                </div>
                <button className="text-button" onClick={p.onCloseSource}>
                  关闭
                </button>
              </div>
              <div className="citation-list">
                {p.source.chunks.map((chunk) => (
                  <article className="citation-item" key={chunk.id}>
                    <strong>#{chunk.ordinal + 1}</strong>
                    <p>{chunk.text}</p>
                    <small>
                      {chunk.location
                        ? JSON.stringify(chunk.location)
                        : "未提供位置"}
                    </small>
                  </article>
                ))}
              </div>
            </section>
          )}
        </section>
      )}
    </DataView>
  );
}
