import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { Plus } from "lucide-react";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { readSseResponse, type SseEvent } from "../../services/sse";
import type {
  AgentStep,
  AnalysisResult,
  AnalysisRun,
  KnowledgeBase,
  Source,
} from "../../app/domain-types";
import { AnalysisPanel } from "./AnalysisPanel";
import { AnalysisHistory } from "./AnalysisHistory";
import { AnalysisRunDetail } from "./AnalysisRunDetail";
import { freshSnapshot, mergeAnalysisEvent } from "./analysis-stream";

export function AnalysisRoute() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [token, setToken] = useState(
    () => localStorage.getItem("supplymind_token") || "",
  );
  const [sources, setSources] = useState<Source[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [knowledgeBaseId, setKnowledgeBaseId] = useState("");
  const [question, setQuestion] = useState(() => searchParams.get("question") || "");
  const [stream, setStream] = useState(freshSnapshot);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<AnalysisRun | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const api = useCallback(
    <T,>(path: string, init?: RequestInit) =>
      apiRequest<T>(
        API_BASE,
        token,
        path,
        init,
        localStorage.getItem("supplymind_refresh") || undefined,
        (access, refresh) => {
          setToken(access);
          localStorage.setItem("supplymind_token", access);
          localStorage.setItem("supplymind_refresh", refresh);
        },
      ),
    [token],
  );
  useEffect(() => {
    const preset = searchParams.get("question");
    if (preset) setQuestion(preset);
  }, [searchParams]);
  const refreshRuns = useCallback(
    () => api<AnalysisRun[]>("/analyses?page=1&page_size=10").then(setRuns),
    [api],
  );
  useEffect(() => {
    if (!token) {
      navigate("/");
      return;
    }
    void Promise.all([
      api<Source[]>("/data-sources"),
      api<KnowledgeBase[]>("/knowledge-bases?page=1&page_size=100"),
      refreshRuns(),
    ])
      .then(([nextSources, nextKnowledge]) => {
        setSources(nextSources.filter((item) => item.status === "active"));
        setKnowledgeBases(nextKnowledge);
      })
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "无法加载分析资源"),
      );
  }, [api, navigate, refreshRuns, token]);
  const openRun = useCallback(
    async (id: string) => {
      setBusy(true);
      try {
        const [run, nextSteps] = await Promise.all([
          api<AnalysisRun>(`/analyses/${id}`),
          api<AgentStep[]>(`/analyses/${id}/steps`),
        ]);
        setSelectedRun(run);
        setSteps(nextSteps);
        setStream((current) => ({
          ...current,
          runId: run.id,
          result: run.result
            ? {
                run_id: run.id,
                sql: run.sql,
                sql_draft: run.sql_draft,
                guard_error: run.guard_error,
                result: run.result,
              }
            : null,
        }));
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "无法恢复分析运行");
      } finally {
        setBusy(false);
      }
    },
    [api],
  );
  useEffect(() => {
    if (!selectedRun || !["running", "queued"].includes(selectedRun.status))
      return;
    let disposed = false;
    const id = selectedRun.id;
    const recover = async () => {
      try {
        const recovered = await api<{
          status: string;
          sql?: string;
          sql_draft?: string;
          guard_error?: string;
          result?: AnalysisResult["result"];
          steps: AgentStep[];
        }>(`/analyses/${id}/events`);
        if (disposed) return;
        setSelectedRun((current) =>
          current?.id === id
            ? {
                ...current,
                status: recovered.status,
                sql: recovered.sql,
                sql_draft: recovered.sql_draft,
                guard_error: recovered.guard_error,
                result: recovered.result,
              }
            : current,
        );
        setSteps(recovered.steps || []);
        if (recovered.status !== "running" && recovered.status !== "queued")
          void refreshRuns();
      } catch (cause) {
        if (!disposed)
          setError(cause instanceof Error ? cause.message : "无法恢复会话状态");
      }
    };
    void recover();
    const timer = window.setInterval(() => void recover(), 2000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [api, refreshRuns, selectedRun?.id, selectedRun?.status]);
  const update = useCallback(
    (event: SseEvent) => {
      setStream((current) => mergeAnalysisEvent(current, event));
      if (["completed", "failed", "cancelled"].includes(event.event))
        void refreshRuns();
    },
    [refreshRuns],
  );
  const resumeRunStream = useCallback(async (runId: string, initialEventId = 0) => {
    let lastEventId = initialEventId;
    for (let retry = 0; retry < 4; retry += 1) {
      const response = await fetch(`${API_BASE}/analyses/${runId}/stream`, {
        headers: { Authorization: `Bearer ${token}`, "Last-Event-ID": String(lastEventId) },
      });
      if (!response.ok) throw new Error("无法恢复分析事件流");
      await readSseResponse(response, (events) => events.forEach((event) => {
        if (event.id) lastEventId = event.id;
        update(event);
      }));
      const run = await api<AnalysisRun>(`/analyses/${runId}`);
      if (["completed", "failed", "cancelled", "rejected", "waiting_approval"].includes(run.status)) return;
      await new Promise((resolve) => window.setTimeout(resolve, 700 * (retry + 1)));
    }
    throw new Error("事件流多次中断，请从运行历史恢复查看");
  }, [api, token, update]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!sourceId || !knowledgeBaseId)
      return setError("请选择数据源和知识库。");
    setSelectedRun(null);
    setBusy(true);
    setError("");
    setStream(freshSnapshot());
    try {
      const response = await fetch(`${API_BASE}/analyses`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          data_source_id: sourceId,
          knowledge_base_id: knowledgeBaseId,
          question,
          conversation_id: crypto.randomUUID(),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const detail = payload.detail;
        const message =
          typeof detail === "object" && detail
            ? String(detail.message || detail.hint || "分析请求失败")
            : String(detail || "分析请求失败");
        throw new Error(
          `${message}（Trace ID: ${response.headers.get("x-trace-id") || "-"}）`,
        );
      }
      const accepted = await response.json() as { run_id: string };
      setStream((current) => ({ ...current, runId: accepted.run_id }));
      await resumeRunStream(accepted.run_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "分析失败");
    } finally {
      setBusy(false);
    }
  };
  const cancel = (id: string) =>
    void api(`/analyses/${id}/cancel`, { method: "POST" })
      .then(() => openRun(id))
      .then(refreshRuns)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "取消失败"),
      );
  const retry = (id: string) =>
    void fetch(`${API_BASE}/analyses/${id}/retry`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("分析重试失败");
        await readSseResponse(response, (events) => events.forEach(update));
      })
      .then(refreshRuns)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "分析重试失败"),
      );
  const startNewSession = useCallback(() => {
    setSelectedRun(null);
    setSteps([]);
    setError("");
    setStream(freshSnapshot());
    setQuestion("");
    window.setTimeout(
      () => document.getElementById("analysis-question")?.focus(),
      0,
    );
  }, []);
  return (
    <AppShell
      nav="分析会话"
      items={[
        "运营总览",
        "项目管理",
        "企业管理",
        "大屏配置",
        "分析会话",
        "Agent 平台",
        "数据源",
        "知识库",
        "报告中心",
        "组织与审计",
        "系统状态",
      ]}
      busy={busy}
      onNavigate={(item) =>
        navigate(
          (
            {
              运营总览: "/overview",
              项目管理: "/project",
              企业管理: "/platform/organizations",
              大屏配置: "/dashboard/configuration",
              分析会话: "/analysis",
              "Agent 平台": "/agent-platform",
              数据源: "/data-sources",
              知识库: "/knowledge",
              报告中心: "/reports",
              组织与审计: "/audit",
              系统状态: "/system-status",
            } as Record<string, string>
          )[item],
        )
      }
      onRefresh={() => void refreshRuns()}
      onLogout={() => {
        localStorage.clear();
        navigate("/");
      }}
    >
      <section className="hermes-analysis-frame" aria-label="Hermes 分析框架">
        <div className="hermes-frame-header">
          <div>
            <p className="section-kicker">HERMES / SESSION ORCHESTRATION</p>
            <h3>Hermes 会话框架</h3>
            <p>从同一个外层框架管理新建分析、实时运行与历史追溯。</p>
          </div>
          <button
            className="primary-button hermes-new-session"
            onClick={startNewSession}
            type="button"
          >
            <Plus size={15} aria-hidden="true" />
            新建会话
          </button>
        </div>
        <div className="analysis-workspace-layout">
          <aside className="analysis-history-pane">
            <AnalysisHistory
              runs={runs}
              selectedId={selectedRun?.id}
              onOpen={(id) => void openRun(id)}
            />
          </aside>
          <div className="analysis-workspace-main">
            <AnalysisPanel
              question={question}
              setQuestion={setQuestion}
              loading={busy}
              onSubmit={submit}
              sources={sources}
              knowledgeBases={knowledgeBases}
              sourceId={sourceId}
              knowledgeBaseId={knowledgeBaseId}
              setSourceId={setSourceId}
              setKnowledgeBaseId={setKnowledgeBaseId}
              stages={stream.stages}
              activity={stream.activity}
              citationCount={stream.citationCount}
              rowCount={stream.rowCount}
              chartReady={stream.chartReady}
              error={error || stream.error}
              result={stream.result}
            />
          </div>
        </div>
      </section>
      {selectedRun && (
        <Dialog.Root
          open
          onOpenChange={(open) => !open && setSelectedRun(null)}
        >
          <Dialog.Portal>
            <Dialog.Overlay className="analysis-session-overlay" />
            <Dialog.Content
              className="analysis-session-window"
              aria-describedby={undefined}
            >
              <Dialog.Title className="sr-only">分析会话详情</Dialog.Title>
              <AnalysisRunDetail
                run={selectedRun}
                steps={steps}
                sources={sources}
                knowledgeBases={knowledgeBases}
                busy={busy}
                onClose={() => setSelectedRun(null)}
                onCancel={cancel}
                onRetry={retry}
              />
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </AppShell>
  );
}
