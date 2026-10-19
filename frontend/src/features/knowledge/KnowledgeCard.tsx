import { FormEvent, useState } from "react";
import type { Document, KnowledgeBase } from "../../app/domain-types";

type Props = {
  knowledgeBase: KnowledgeBase;
  documents: Document[];
  onUpload: (event: FormEvent<HTMLFormElement>, id: string) => Promise<void>;
  onAnalyze: () => void;
  onManage: () => void;
};

export function KnowledgeCard({ knowledgeBase, documents, onUpload, onAnalyze, onManage }: Props) {
  const [fileName, setFileName] = useState("");
  const [uploading, setUploading] = useState(false);
  const completed = documents.filter((document) => document.status === "completed").length;
  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    setUploading(true);
    try {
      await onUpload(event, knowledgeBase.id);
      setFileName("");
    } finally {
      setUploading(false);
    }
  }
  return (
    <article className="knowledge-card">
      <header className="knowledge-card-header"><div><div className="knowledge-title-row"><span className="knowledge-mark">K</span><div><h3>{knowledgeBase.name}</h3><p>{knowledgeBase.description || "暂无用途说明"}</p></div></div></div><span className="status-chip">{completed}/{documents.length || 0} 已摄取</span></header>
      <div className="knowledge-stats"><span><strong>{documents.length}</strong> 文档</span><span><strong>{documents.reduce((total, document) => total + document.chunk_count, 0)}</strong> 片段</span><span><strong>可检索</strong> 状态</span></div>
      <form className="knowledge-upload" onSubmit={(event) => void submitUpload(event)}>
        <label className="upload-dropzone" htmlFor={`file-${knowledgeBase.id}`}><span className="upload-icon">↑</span><span><strong>{fileName || "选择或拖入文档"}</strong><small>支持 PDF、Markdown、TXT，单文件不超过 10 MB</small></span><input id={`file-${knowledgeBase.id}`} type="file" name="file" accept=".pdf,.md,.markdown,.txt" required aria-label={`${knowledgeBase.name}上传文档`} onChange={(event) => setFileName(event.target.files?.[0]?.name || "")} /></label>
        <button className="primary-button upload-button" disabled={uploading || !fileName}>{uploading ? "正在提交..." : "开始摄取"}</button>
      </form>
      {documents.length > 0 && <div className="knowledge-documents"><div className="knowledge-documents-heading"><span>最近文档</span><span>{documents.length} 个</span></div>{documents.slice(0, 3).map((document) => <div className="knowledge-document" key={document.id}><span className="document-type">{document.filename.split(".").pop()?.toUpperCase() || "DOC"}</span><div><strong>{document.filename}</strong><small>{document.chunk_count} 个片段 · {new Date(document.created_at).toLocaleDateString("zh-CN")}</small></div><span className={`status-dot-label ${document.status}`}>{document.status === "completed" ? "已完成" : document.status === "processing" ? "处理中" : document.status === "failed" ? "失败" : "排队中"}</span></div>)}</div>}
      <footer className="knowledge-card-footer"><button className="text-button" onClick={onManage}>管理详情 <span>↗</span></button><button className="text-button" onClick={onAnalyze}>用此知识库分析 <span>→</span></button><span className="knowledge-id">ID · {knowledgeBase.id.slice(0, 8)}</span></footer>
    </article>
  );
}
