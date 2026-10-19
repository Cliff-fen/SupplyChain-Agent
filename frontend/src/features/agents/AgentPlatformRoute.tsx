import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  BrainCircuit,
  Check,
  DatabaseZap,
  ExternalLink,
  Plus,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { NAV_ITEMS } from "../../app/navigation";
import { NAV_PATHS } from "../../app/routes";
import type { AgentApproval, AgentStep, AnalysisRun, HermesRuntime, MCPServer, UserMemory } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";

type Tab = "runs" | "evolution" | "memory" | "mcp" | "approvals";

const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "runs", label: "运行观测", icon: Activity },
  { id: "evolution", label: "自进化", icon: Sparkles },
  { id: "memory", label: "长期记忆", icon: BrainCircuit },
  { id: "mcp", label: "MCP 工具", icon: ServerCog },
  { id: "approvals", label: "人工审批", icon: ShieldCheck },
];

export function AgentPlatformRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [tab, setTab] = useState<Tab>("runs");
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>();
  const [memories, setMemories] = useState<UserMemory[]>([]);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [approvals, setApprovals] = useState<AgentApproval[]>([]);
  const [hermesRuntime, setHermesRuntime] = useState<HermesRuntime>();
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [newMemory, setNewMemory] = useState({ category: "kpi_interest", memory_key: "", content: "" });
  const [newServer, setNewServer] = useState({ name: "", endpoint: "" });

  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(
    API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined,
    (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); },
  ), [token]);

  const load = useCallback(async () => {
    setLoading(true); setNotice("");
    const [runsResult, memoriesResult, settingsResult, serversResult, approvalsResult, hermesResult] = await Promise.allSettled([
      api<AnalysisRun[]>("/analyses?page=1&page_size=20"), api<UserMemory[]>("/me/memories"),
      api<{ enabled: boolean }>("/me/memory/settings"), api<MCPServer[]>("/mcp/servers"),
      api<AgentApproval[]>("/agent-approvals?status=pending"), api<HermesRuntime>("/hermes/runtime"),
    ]);
    if (runsResult.status === "fulfilled") setRuns(runsResult.value);
    if (memoriesResult.status === "fulfilled") setMemories(memoriesResult.value);
    if (settingsResult.status === "fulfilled") setMemoryEnabled(settingsResult.value.enabled);
    if (serversResult.status === "fulfilled") setServers(serversResult.value);
    if (approvalsResult.status === "fulfilled") setApprovals(approvalsResult.value);
    if (hermesResult.status === "fulfilled") setHermesRuntime(hermesResult.value);
    const failed = [serversResult, approvalsResult].some((item) => item.status === "rejected");
    if (failed) setNotice("部分组织级管理数据需要管理员权限。");
    setLoading(false);
  }, [api]);

  useEffect(() => { if (!token) navigate("/"); else void load(); }, [load, navigate, token]);

  const openRun = async (runId: string) => {
    setSelectedRun(runId); setLoading(true);
    try { setSteps(await api<AgentStep[]>(`/analyses/${runId}/steps`)); }
    catch (error) { setNotice(error instanceof Error ? error.message : "无法读取运行轨迹"); }
    finally { setLoading(false); }
  };
  const toggleMemory = async () => {
    const next = !memoryEnabled;
    await api("/me/memory/settings", { method: "PATCH", body: JSON.stringify({ enabled: next }) });
    setMemoryEnabled(next);
  };
  const createMemory = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const item = await api<UserMemory>("/me/memories", { method: "POST", body: JSON.stringify({ ...newMemory, confidence: 1 }) });
      setMemories((current) => [item, ...current]); setNewMemory({ category: "kpi_interest", memory_key: "", content: "" });
    } catch (error) { setNotice(error instanceof Error ? error.message : "记忆保存失败"); }
  };
  const removeMemory = async (id: string) => { await api(`/me/memories/${id}`, { method: "DELETE" }); setMemories((current) => current.filter((item) => item.id !== id)); };
  const createServer = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const item = await api<MCPServer>("/mcp/servers", { method: "POST", body: JSON.stringify({ name: newServer.name, transport: "streamable_http", endpoint: newServer.endpoint }) });
      setServers((current) => [item, ...current]); setNewServer({ name: "", endpoint: "" });
    } catch (error) { setNotice(error instanceof Error ? error.message : "MCP Server 添加失败"); }
  };
  const testServer = async (id: string) => { const item = await api<MCPServer>(`/mcp/servers/${id}/test`, { method: "POST" }); setServers((current) => current.map((server) => server.id === id ? item : server)); };
  const toggleServer = async (server: MCPServer) => { const item = await api<MCPServer>(`/mcp/servers/${server.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !server.enabled }) }); setServers((current) => current.map((value) => value.id === item.id ? item : value)); };
  const removeServer = async (id: string) => { await api(`/mcp/servers/${id}`, { method: "DELETE" }); setServers((current) => current.filter((item) => item.id !== id)); };
  const decide = async (id: string, approved: boolean) => {
    const item = await api<AgentApproval>(`/agent-approvals/${id}/${approved ? "approve" : "reject"}`, { method: "POST", body: JSON.stringify({ reason: "已在控制台确认" }) });
    setApprovals((current) => current.filter((value) => value.id !== item.id));
  };

  return <AppShell nav="Agent 平台" items={NAV_ITEMS} busy={loading} onNavigate={(item) => navigate(NAV_PATHS[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    <section className="agent-platform">
      <div className="agent-platform-heading"><div><span className="section-kicker">HERMES / ENTERPRISE AGENT CONTROL PLANE</span><h3>运行、治理与自进化</h3><p>查看分析路由、持久化记忆、受控工具连接、待审批操作和 Hermes 候选改进。</p></div><a className="icon-button" href={`${API_BASE.replace("/api/v1", "")}/.well-known/agent-card.json`} target="_blank" rel="noreferrer" title="查看 A2A Agent Card" aria-label="查看 A2A Agent Card"><ExternalLink size={16} /></a></div>
      <div className="agent-tabs" role="tablist" aria-label="Agent 平台视图">{tabs.map(({ id, label, icon: Icon }) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}><Icon size={15} />{label}{id === "approvals" && approvals.length > 0 ? <b>{approvals.length}</b> : null}</button>)}</div>
      {notice ? <p className="agent-notice">{notice}</p> : null}
      {tab === "runs" && <section className="agent-grid"><div className="agent-panel"><div className="panel-heading"><div><strong>最近运行</strong><p>路由、Token 与成本估算按运行保存。</p></div><span>{runs.length}</span></div>{runs.length ? <div className="agent-run-list">{runs.map((run) => <button key={run.id} className={selectedRun === run.id ? "selected" : ""} onClick={() => void openRun(run.id)}><span className={`run-dot ${run.status}`} /><div><strong>{run.question}</strong><small>{run.route || "待路由"} · {run.status}</small></div><small>{run.estimated_cost_usd ? `$${run.estimated_cost_usd.toFixed(4)}` : "-"}</small></button>)}</div> : <p className="agent-empty">暂无分析运行。</p>}</div><div className="agent-panel"><div className="panel-heading"><div><strong>Agent Trace</strong><p>{selectedRun ? `运行 ${selectedRun.slice(0, 8)}` : "选择左侧运行查看节点轨迹"}</p></div></div>{steps.length ? <ol className="agent-trace">{steps.map((step) => <li key={step.id}><span className={step.status} /><div><strong>{step.name}</strong><small>{step.prompt_version || "enterprise-agent-v2"} · {step.status}</small></div><code>{Object.keys(step.output || {}).join(", ") || "-"}</code></li>)}</ol> : <p className="agent-empty">尚未选择运行。</p>}</div></section>}
      {tab === "evolution" && <section className="agent-grid hermes-evolution-grid"><div className="agent-panel"><div className="panel-heading"><div><strong>Hermes Evolution Loop</strong><p>候选改进先进入评测与审批门禁，只有通过后才可被采纳。</p></div><span>{hermesRuntime?.status || "loading"}</span></div>{hermesRuntime ? <><div className="hermes-signal-grid">{hermesRuntime.signals.map((signal) => <article key={signal.id} className={`hermes-signal ${signal.status}`}><span>{signal.label}</span><strong>{signal.value}{signal.unit}</strong><small>{signal.status === "healthy" ? "健康" : signal.status === "blocked" ? "阻塞" : "观察"}</small></article>)}</div><div className="hermes-candidate-list">{hermesRuntime.candidates.map((candidate) => <article key={candidate.id}><div><strong>{candidate.title}</strong><small>{candidate.target} · {candidate.status}</small><p>{candidate.reason}</p></div><code>{candidate.gate}</code></article>)}</div></> : <p className="agent-empty">正在读取 Hermes 状态。</p>}</div><aside className="agent-panel agent-policy hermes-safeguards"><Sparkles size={19} /><strong>自进化护栏</strong>{(hermesRuntime?.safeguards || ["候选改进默认不自动上线", "训练数据先脱敏再进入评测集", "评测门禁失败时保持当前生产配置"]).map((item) => <p key={item}>{item}</p>)}</aside></section>}
      {tab === "memory" && <section className="agent-grid"><div className="agent-panel"><div className="panel-heading"><div><strong>用户级长期记忆</strong><p>仅保存偏好、范围与 KPI 关注点，可随时关闭或清空。</p></div><label className="switch"><input type="checkbox" checked={memoryEnabled} onChange={() => void toggleMemory()} /><span /></label></div><form className="agent-inline-form" onSubmit={createMemory}><select value={newMemory.category} onChange={(event) => setNewMemory({ ...newMemory, category: event.target.value })}><option value="kpi_interest">KPI 关注</option><option value="factory_scope">工厂范围</option><option value="product_line">产品线</option><option value="time_range">时间范围</option></select><input value={newMemory.memory_key} onChange={(event) => setNewMemory({ ...newMemory, memory_key: event.target.value })} placeholder="记忆键" required /><input value={newMemory.content} onChange={(event) => setNewMemory({ ...newMemory, content: event.target.value })} placeholder="内容" required /><button className="icon-button" title="添加记忆" aria-label="添加记忆"><Plus size={16} /></button></form>{memories.length ? <div className="agent-memory-list">{memories.map((item) => <article key={item.id}><div><strong>{item.memory_key}</strong><small>{item.category} · 置信度 {Math.round(item.confidence * 100)}%</small><p>{item.content}</p></div><button className="icon-button danger" title="删除记忆" aria-label="删除记忆" onClick={() => void removeMemory(item.id)}><Trash2 size={15} /></button></article>)}</div> : <p className="agent-empty">暂无长期记忆。</p>}</div><aside className="agent-panel agent-policy"><BrainCircuit size={19} /><strong>记忆策略</strong><p>敏感凭据与个人身份信息不会写入长期记忆。记忆按组织和用户隔离，并携带置信度、来源和版本。</p></aside></section>}
      {tab === "mcp" && <section className="agent-grid"><div className="agent-panel"><div className="panel-heading"><div><strong>受控 MCP Server</strong><p>仅允许白名单 HTTP 地址或部署目录预定义的 stdio 工具。</p></div></div><form className="agent-inline-form" onSubmit={createServer}><input value={newServer.name} onChange={(event) => setNewServer({ ...newServer, name: event.target.value })} placeholder="服务名称" required /><input value={newServer.endpoint} onChange={(event) => setNewServer({ ...newServer, endpoint: event.target.value })} placeholder="http://approved-host/mcp" required /><button className="icon-button" title="添加 MCP Server" aria-label="添加 MCP Server"><Plus size={16} /></button></form>{servers.length ? <div className="agent-server-list">{servers.map((server) => <article key={server.id}><div><span className={`server-status ${server.status}`} /><strong>{server.name}</strong><small>{server.transport} · {server.discovered_tools.length} 个工具</small><p>{server.endpoint || server.stdio_catalog_key}</p></div><div className="agent-actions"><button className="icon-button" title="测试连接" aria-label="测试连接" onClick={() => void testServer(server.id)}><RefreshCw size={15} /></button><button className="icon-button" title={server.enabled ? "停用 Server" : "启用 Server"} aria-label={server.enabled ? "停用 Server" : "启用 Server"} onClick={() => void toggleServer(server)}><DatabaseZap size={15} /></button><button className="icon-button danger" title="删除 Server" aria-label="删除 Server" onClick={() => void removeServer(server.id)}><Trash2 size={15} /></button></div></article>)}</div> : <p className="agent-empty">暂无外部 MCP Server。</p>}</div><aside className="agent-panel agent-policy"><ServerCog size={19} /><strong>内置工具</strong><p>平台内置 Schema、只读 SQL、Advanced RAG、图表与报告导出工具。所有调用都会进行租户令牌、RBAC、参数校验和审计。</p></aside></section>}
      {tab === "approvals" && <section className="agent-panel"><div className="panel-heading"><div><strong>待审批操作</strong><p>只读分析自动执行；报告导出与外部副作用需要确认。</p></div><span>{approvals.length}</span></div>{approvals.length ? <div className="agent-approval-list">{approvals.map((item) => <article key={item.id}><div><strong>{item.tool_name}</strong><small>运行 {item.analysis_run_id.slice(0, 8)} · {item.side_effect}</small><code>{JSON.stringify(item.request_payload)}</code></div><div className="agent-actions"><button className="icon-button approve" title="批准操作" aria-label="批准操作" onClick={() => void decide(item.id, true)}><Check size={16} /></button><button className="icon-button danger" title="拒绝操作" aria-label="拒绝操作" onClick={() => void decide(item.id, false)}><X size={16} /></button></div></article>)}</div> : <p className="agent-empty">当前没有待审批操作。</p>}</section>}
    </section>
  </AppShell>;
}
