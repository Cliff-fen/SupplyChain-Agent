import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { Citation, Document, DocumentSource, KnowledgeBase, KnowledgeDetail, OrganizationSummary } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { KnowledgeBasePage } from "./KnowledgeBasePage";
import type { DocumentTaskRow } from "./DocumentTaskList";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };
type Metadata = { metric_name: string; metric_definition: string; metric_formula: string; metric_unit: string; applicable_factories: string[]; applicable_product_lines: string[]; effective_from: string | null };

export function KnowledgeRoute() {
  const nav = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [filter, setFilter] = useState({ name: "", status: "" });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [hasMore, setHasMore] = useState(false);
  const [selected, setSelected] = useState<KnowledgeDetail | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<DocumentSource | null>(null);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [archiveTarget, setArchiveTarget] = useState<KnowledgeDetail | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeDetail | null>(null);
  const [documentAction, setDocumentAction] = useState<{ document: DocumentTaskRow; kind: "archive" | "delete" } | null>(null);
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (filter.name) params.set("name", filter.name);
    if (filter.status) params.set("status", filter.status);
    const [knowledge, org] = await Promise.all([api<KnowledgeBase[]>(`/knowledge-bases?${params}`), api<OrganizationSummary>("/organization")]);
    setItems(knowledge); setHasMore(knowledge.length === pageSize); setOrganization(org);
  }, [api, filter, page, pageSize]);
  const open = useCallback(async (id: string) => {
    setActiveAction(`knowledge:${id}:open`); setNotice("");
    try {
      const [detail, listed] = await Promise.all([api<KnowledgeDetail>(`/knowledge-bases/${id}`), api<Document[]>(`/knowledge-bases/${id}/documents?page=1&page_size=200`)]);
      setSelected(detail); setDocuments(listed); setCitations([]); setSource(null);
    } catch (error) { setNotice(error instanceof Error ? error.message : "知识库详情读取失败"); }
    finally { setActiveAction(null); }
  }, [api]);
  useEffect(() => { if (!token) nav("/"); else void load().catch((error) => setNotice(error instanceof Error ? error.message : "知识库读取失败")); }, [load, nav, token]);
  const pendingIds = useMemo(() => documents.filter((document) => ["queued", "processing"].includes(document.status)).map((document) => document.id), [documents]);
  useEffect(() => {
    if (!token || !pendingIds.length) return;
    let stopped = false;
    const refresh = async () => { try { const next = await Promise.all(pendingIds.map((id) => api<Document>(`/documents/${id}`))); if (!stopped) setDocuments((current) => current.map((document) => next.find((item) => item.id === document.id) || document)); } catch { /* Preserve the known status and leave retry/cancel available. */ } };
    void refresh(); const timer = window.setInterval(() => void refresh(), 2500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [api, pendingIds, token]);
  const refreshSelected = async () => { await load(); if (selected) await open(selected.id); };
  const create = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); setActiveAction("knowledge:create"); try { await api("/knowledge-bases", { method: "POST", body: JSON.stringify({ name: form.get("name"), description: form.get("description") || "" }) }); formElement.reset(); await load(); setNotice("知识库已创建"); } catch (error) { setNotice(error instanceof Error ? error.message : "创建失败"); } finally { setActiveAction(null); } };
  const upload = async (event: FormEvent<HTMLFormElement>, id: string) => { event.preventDefault(); const formElement = event.currentTarget; const file = new FormData(formElement).get("file"); if (!(file instanceof File) || !file.name) { setNotice("请选择 PDF、Markdown 或 TXT 文件"); return; } setActiveAction(`knowledge:${id}:upload`); try { const body = new FormData(); body.append("file", file); const document = await api<Document>(`/knowledge-bases/${id}/documents`, { method: "POST", body }); setDocuments((current) => [document, ...current.filter((item) => item.id !== document.id)]); formElement.reset(); setNotice("文档已进入摄取队列，可在详情查看实时状态。"); } catch (error) { setNotice(error instanceof Error ? error.message : "文档上传失败"); } finally { setActiveAction(null); } };
  const replace = async (document: DocumentTaskRow, file: File) => { if (!document.knowledge_base_id) return; setActiveAction(`document:${document.id}:replace`); try { const body = new FormData(); body.append("file", file); body.append("replace_document_id", document.id); const updated = await api<Document>(`/knowledge-bases/${document.knowledge_base_id}/documents`, { method: "POST", body }); setDocuments((current) => [updated, ...current.filter((item) => item.id !== document.id)]); setNotice("新版本已进入摄取队列。"); } catch (error) { setNotice(error instanceof Error ? error.message : "文档替换失败"); throw error; } finally { setActiveAction(null); } };
  const update = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!selected) return; const form = new FormData(event.currentTarget); setActiveAction(`knowledge:${selected.id}:save`); try { const updated = await api<KnowledgeDetail>(`/knowledge-bases/${selected.id}`, { method: "PATCH", body: JSON.stringify({ name: form.get("name"), description: form.get("description") || "" }) }); setSelected(updated); await load(); setNotice("知识库信息已保存"); } catch (error) { setNotice(error instanceof Error ? error.message : "知识库更新失败"); } finally { setActiveAction(null); } };
  const toggleArchive = async (target: KnowledgeDetail) => { setActiveAction(`knowledge:${target.id}:archive`); try { const updated = await api<KnowledgeDetail>(`/knowledge-bases/${target.id}/archive`, { method: "POST" }); setSelected((current) => current?.id === target.id ? updated : current); setArchiveTarget(null); await load(); setNotice(updated.is_archived ? "知识库已归档，不能用于新的分析。" : "知识库已恢复。"); } catch (error) { setNotice(error instanceof Error ? error.message : "知识库状态更新失败"); } finally { setActiveAction(null); } };
  const removeKnowledge = async () => { if (!deleteTarget) return; const target = deleteTarget; setActiveAction(`knowledge:${target.id}:delete`); try { await api(`/knowledge-bases/${target.id}`, { method: "DELETE" }); setItems((current) => current.filter((item) => item.id !== target.id)); setDocuments([]); setSelected(null); setDeleteTarget(null); await load(); setNotice("知识库已永久删除。"); } catch (error) { setNotice(error instanceof Error ? error.message : "知识库删除失败"); } finally { setActiveAction(null); } };
  const search = async (event: FormEvent) => { event.preventDefault(); if (!selected || !query.trim()) return; setActiveAction(`knowledge:${selected.id}:search`); try { const result = await api<{ results: Citation[] }>(`/knowledge-bases/${selected.id}/search`, { method: "POST", body: JSON.stringify({ query, limit: 5 }) }); setCitations(result.results); } catch (error) { setNotice(error instanceof Error ? error.message : "检索失败"); } finally { setActiveAction(null); } };
  const taskAction = async (taskId: string, action: "retry" | "cancel") => { setActiveAction(`task:${taskId}:${action}`); try { await api(`/ingestion-tasks/${taskId}/${action}`, { method: "POST" }); await refreshSelected(); setNotice(action === "retry" ? "摄取任务已重新排队。" : "摄取任务已取消。"); } catch (error) { setNotice(error instanceof Error ? error.message : "任务操作失败"); } finally { setActiveAction(null); } };
  const updateMetadata = async (document: DocumentTaskRow, metadata: Metadata) => { const updated = await api<Document>(`/documents/${document.id}/metadata`, { method: "PATCH", body: JSON.stringify(metadata) }); setDocuments((current) => current.map((item) => item.id === updated.id ? updated : item)); setNotice("指标口径已保存。"); };
  const executeDocumentAction = async () => { if (!documentAction) return; const { document, kind } = documentAction; setActiveAction(`document:${document.id}:${kind}`); try { if (kind === "archive") await api(`/documents/${document.id}/archive`, { method: "POST" }); else await api(`/documents/${document.id}`, { method: "DELETE" }); setDocumentAction(null); await refreshSelected(); setNotice(kind === "archive" ? (document.is_archived ? "文档已恢复。" : "文档已归档。") : "文档已删除。"); } catch (error) { setNotice(error instanceof Error ? error.message : "文档操作失败"); } finally { setActiveAction(null); } };
  return <AppShell nav="知识库" items={NAV_ITEMS} organizationName={organization?.name} busy={Boolean(activeAction)} onNavigate={(item) => nav(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); nav("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    <KnowledgeBasePage filter={filter} setFilter={setFilter} page={page} pageSize={pageSize} hasMore={hasMore} setPage={setPage} setPageSize={setPageSize} knowledgeBases={items} documents={documents} busy={Boolean(activeAction)} onCreate={(event) => void create(event)} onUpload={upload} onAnalyze={(name) => nav(`/analysis?question=${encodeURIComponent(name)}`)} onManage={(id) => void open(id)} selected={selected} onCloseDetail={() => { setSelected(null); setSource(null); }} onToggleArchive={() => selected && void toggleArchive(selected)} onRequestArchive={() => setArchiveTarget(selected)} onRequestDelete={() => setDeleteTarget(selected)} onUpdate={(event) => void update(event)} query={query} setQuery={setQuery} onSearch={(event) => void search(event)} citations={citations} role={organization?.role} onSource={(document) => void api<DocumentSource>(`/knowledge-bases/${document.knowledge_base_id}/documents/${document.id}/source`).then(setSource).catch((error) => setNotice(error instanceof Error ? error.message : "文档原文读取失败"))} onRetry={(id) => void taskAction(id, "retry")} onCancel={(id) => void taskAction(id, "cancel")} onArchiveDocument={(document) => setDocumentAction({ document, kind: "archive" })} onDeleteDocument={(document) => setDocumentAction({ document, kind: "delete" })} onReplace={replace} onMetadata={updateMetadata} source={source} onCloseSource={() => setSource(null)} />
    {archiveTarget && <Confirm title="归档这个知识库？" copy={`“${archiveTarget.name}”归档后不能用于新的分析，已有文档与审计记录会保留，且可随时恢复。`} confirm="确认归档" busy={Boolean(activeAction)} onCancel={() => setArchiveTarget(null)} onConfirm={() => void toggleArchive(archiveTarget)} />}
    {deleteTarget && <Confirm title="永久删除这个空知识库？" copy={`“${deleteTarget.name}”已归档且不包含任何文档。确认后将永久删除，无法恢复。`} confirm="确认永久删除" destructive busy={Boolean(activeAction)} onCancel={() => setDeleteTarget(null)} onConfirm={() => void removeKnowledge()} />}
    {documentAction && <Confirm title={documentAction.kind === "delete" ? "删除这个文档？" : documentAction.document.is_archived ? "恢复这个文档？" : "归档这个文档？"} copy={documentAction.kind === "delete" ? `“${documentAction.document.filename}”将被永久删除，无法恢复。` : "归档文档不会删除原始版本，可在需要时恢复。"} confirm={documentAction.kind === "delete" ? "确认删除" : documentAction.document.is_archived ? "确认恢复" : "确认归档"} destructive={documentAction.kind === "delete"} busy={Boolean(activeAction)} onCancel={() => setDocumentAction(null)} onConfirm={() => void executeDocumentAction()} />}
  </AppShell>;
}

function Confirm({ title, copy, confirm, destructive, busy, onCancel, onConfirm }: { title: string; copy: string; confirm: string; destructive?: boolean; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  return <div className="modal-backdrop" role="presentation" onClick={onCancel}><section className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="knowledge-confirm-title" onClick={(event) => event.stopPropagation()}><h3 id="knowledge-confirm-title">{title}</h3><p>{copy}</p><div className="confirm-actions"><button className="secondary-button" disabled={busy} onClick={onCancel}>取消</button><button className={`primary-button${destructive ? " danger-button" : ""}`} disabled={busy} onClick={onConfirm}>{busy ? "提交中..." : confirm}</button></div></section></div>;
}
