import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { OrganizationSummary, SchemaTable, Source } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { DataSourceDetail } from "./DataSourceDetail";
import { DataSourcesPage } from "./DataSourcesPage";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };
type Schema = { tables: SchemaTable[]; table_count: number };
type Task = { id: string; status: string; started_at?: string; finished_at?: string; error_message?: string; celery_task_id?: string };
type QueryResult = { sql: string; tables: string[]; rows: Record<string, unknown>[]; row_count: number; max_rows: number; elapsed_ms: number; redacted: boolean };
const emptyDraft = { name: "", engine: "postgresql", host: "", port: "5432", database_name: "", username: "", password: "", allowed_tables: "", tls_required: true };

export function DataSourcesRoute() {
  const nav = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [sources, setSources] = useState<Source[]>([]);
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [selected, setSelected] = useState<Source | null>(null);
  const [schema, setSchema] = useState<Schema | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null);
  const [allowlist, setAllowlist] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async () => { const [items, org] = await Promise.all([api<Source[]>("/data-sources"), api<OrganizationSummary>("/organization")]); setSources(items); setOrganization(org); }, [api]);
  const open = useCallback(async (id: string) => { setActiveAction(`source:${id}:open`); try { const [source, nextSchema, nextTasks] = await Promise.all([api<Source>(`/data-sources/${id}`), api<Schema | null>(`/data-sources/${id}/schema`), api<Task[]>(`/data-sources/${id}/sync-tasks`)]); setSelected(source); setSchema(nextSchema); setTasks(nextTasks); setAllowlist(source.allowed_tables); setSelectedTable(null); setResult(null); } catch (error) { setNotice(error instanceof Error ? error.message : "数据源详情读取失败"); } finally { setActiveAction(null); } }, [api]);
  useEffect(() => { if (!token) nav("/"); else void load().catch((error) => setNotice(error instanceof Error ? error.message : "数据源读取失败")); }, [token, nav, load]);
  const action = async (key: string, path: string, body?: unknown, method = "POST", successNotice = "") => { setActiveAction(key); setNotice(""); try { await api(path, { method, body: body === undefined ? undefined : JSON.stringify(body) }); await load(); if (successNotice) setNotice(successNotice); } catch (error) { setNotice(error instanceof Error ? error.message : "操作失败"); } finally { setActiveAction(null); } };
  const create = (event: FormEvent) => { event.preventDefault(); void action("create", "/data-sources", { ...draft, port: Number(draft.port), allowed_tables: [] }).then(() => setDraft(emptyDraft)); };
  const saveAllowlist = () => { if (!selected) return; void action(`source:${selected.id}:allowlist`, `/data-sources/${selected.id}/allowlist`, { allowed_tables: allowlist }, "PATCH").then(() => void open(selected.id)); };
  const runQuery = (event: FormEvent) => { event.preventDefault(); if (!selected || !query.trim()) return; setActiveAction(`source:${selected.id}:query`); setNotice(""); void api<QueryResult>(`/data-sources/${selected.id}/query`, { method: "POST", body: JSON.stringify({ sql: query }) }).then(setResult).catch((error) => setNotice(error instanceof Error ? error.message : "查询试跑失败")).finally(() => setActiveAction(null)); };
  const canManage = ["org_admin", "platform_admin"].includes(organization?.role || "");
  return <AppShell nav="数据源" items={NAV_ITEMS} organizationName={organization?.name} onNavigate={(item) => nav(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); nav("/"); }}><DataSourcesPage activeAction={activeAction} sources={sources} draft={draft} setDraft={setDraft} onImportDemo={() => void action("import", "/data-sources/import-demo")} onCreate={create} onOpen={(id) => void open(id)} onTest={(id) => void action(`source:${id}:test`, `/data-sources/${id}/test`, undefined, "POST", "连接测试通过，可继续同步 Schema。") } onSync={(id) => void action(`source:${id}:sync`, `/data-sources/${id}/sync`).then(() => void open(id))} onToggle={(id) => void action(`source:${id}:toggle`, `/data-sources/${id}/disable`).then(() => selected?.id === id && void open(id))}>{notice && <p className="form-notice" role="status">{notice}</p>}{selected && <DataSourceDetail source={selected} schema={schema} tasks={tasks} selectedTable={selectedTable} onSelectTable={(name) => void api<SchemaTable>(`/data-sources/${selected.id}/schema/tables/${encodeURIComponent(name)}`).then(setSelectedTable).catch((error) => setNotice(error instanceof Error ? error.message : "表结构读取失败"))} allowlist={allowlist} setAllowlist={setAllowlist} onSaveAllowlist={saveAllowlist} onSync={() => void action(`source:${selected.id}:sync`, `/data-sources/${selected.id}/sync`).then(() => void open(selected.id))} onCancelTask={(taskId) => void action(`source:${selected.id}:sync:${taskId}:cancel`, `/data-sources/${selected.id}/sync-tasks/${taskId}/cancel`).then(() => void open(selected.id))} canManage={canManage} query={query} setQuery={setQuery} onRunQuery={runQuery} result={result} onClose={() => setSelected(null)} />}</DataSourcesPage></AppShell>;
}
