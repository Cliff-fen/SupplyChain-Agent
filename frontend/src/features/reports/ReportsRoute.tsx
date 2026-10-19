import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import type { KnowledgeBase, OrganizationSummary, Report, ReportExport, Source } from "../../app/domain-types";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { ReportsPage, type ReportFilters } from "./ReportsPage";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };
const initialFilters: ReportFilters = { title: "", status: "", createdBy: "", runId: "", createdFrom: "", createdTo: "" };

export function ReportsRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [filters, setFilters] = useState(initialFilters);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [exports, setExports] = useState<ReportExport[]>([]);
  const [notice, setNotice] = useState("");
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async (nextFilters: ReportFilters) => {
    const query = new URLSearchParams({ ...(nextFilters.title ? { title: nextFilters.title } : {}), ...(nextFilters.status ? { status: nextFilters.status } : {}), ...(nextFilters.createdBy ? { created_by: nextFilters.createdBy } : {}), ...(nextFilters.runId ? { run_id: nextFilters.runId } : {}), ...(nextFilters.createdFrom ? { created_from: new Date(nextFilters.createdFrom).toISOString() } : {}), ...(nextFilters.createdTo ? { created_to: new Date(nextFilters.createdTo).toISOString() } : {}) });
    try {
      const [nextReports, nextSources, nextKnowledge, nextOrganization] = await Promise.all([api<Report[]>(`/reports?${query}`), api<Source[]>("/data-sources"), api<KnowledgeBase[]>("/knowledge-bases?page=1&page_size=100"), api<OrganizationSummary>("/organization")]);
      setReports(nextReports); setSources(nextSources); setKnowledgeBases(nextKnowledge); setOrganization(nextOrganization);
    } catch (error) { setNotice(error instanceof Error ? error.message : "报告读取失败"); }
  }, [api]);
  useEffect(() => { if (!token) { navigate("/"); return; } void load(filters); }, [filters, load, navigate, token]);
  const open = async (id: string) => { setNotice(""); try { const [report, items] = await Promise.all([api<Report>(`/reports/${id}`), api<ReportExport[]>(`/reports/${id}/exports`)]); setSelectedReport(report); setExports(items); } catch (error) { setNotice(error instanceof Error ? error.message : "报告详情读取失败"); } };
  const download = async (id: string, previewWindow?: Window | null) => {
    try {
      let response = await fetch(`${API_BASE}/reports/${id}/exports/pdf/download`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok && response.status === 404) {
        await api(`/reports/${id}/exports/pdf`, { method: "POST" });
        setNotice("PDF 已进入导出队列，正在等待生成...");
        for (let attempt = 0; attempt < 20; attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 1500));
          const exportStatus = await api<ReportExport>(`/reports/${id}/exports/pdf`);
          setExports((current) => [exportStatus, ...current.filter((item) => item.id !== exportStatus.id)]);
          if (exportStatus.status === "failed") throw new Error(`PDF 导出失败：${exportStatus.error_message || "未知原因"}`);
          if (exportStatus.status === "completed") { response = await fetch(`${API_BASE}/reports/${id}/exports/pdf/download`, { headers: { Authorization: `Bearer ${token}` } }); break; }
        }
      }
      if (!response.ok) throw new Error(`PDF 下载失败（Trace ID: ${response.headers.get("x-trace-id") || "-"}）`);
      const url = URL.createObjectURL(await response.blob());
      if (previewWindow) { previewWindow.location.href = url; window.setTimeout(() => URL.revokeObjectURL(url), 60_000); setNotice("PDF 已在新窗口打开"); return; }
      const link = document.createElement("a"); link.href = url; link.download = `${id}.pdf`; link.click(); URL.revokeObjectURL(url); setNotice("PDF 下载已开始");
    } catch (error) { previewWindow?.close(); setNotice(error instanceof Error ? error.message : "PDF 下载失败"); }
  };
  const preview = (id: string) => { const previewWindow = window.open("", "_blank"); if (!previewWindow) { setNotice("浏览器阻止了预览窗口，请允许弹窗后重试。"); return; } previewWindow.document.title = "SupplyMind PDF 预览"; previewWindow.document.body.textContent = "正在准备 PDF，请勿关闭此窗口..."; void download(id, previewWindow); };
  const retryExport = (reportId: string, exportId: string) => { void api<ReportExport>(`/reports/${reportId}/exports/${exportId}/retry`, { method: "POST" }).then((updated) => { setExports((current) => [updated, ...current.filter((item) => item.id !== updated.id)]); setNotice("PDF 导出已重新排队"); }).catch((error) => setNotice(error instanceof Error ? error.message : "PDF 重试失败")); };
  const regenerateExport = (reportId: string) => { void api<ReportExport>(`/reports/${reportId}/exports/pdf?force=true`, { method: "POST" }).then((updated) => { setExports((current) => [updated, ...current]); setNotice("正在按最新渲染规则重新生成 PDF..."); }).catch((error) => setNotice(error instanceof Error ? error.message : "PDF 重新生成失败")); };
  return <AppShell nav="报告中心" items={NAV_ITEMS} organizationName={organization?.name} onNavigate={(item) => navigate(paths[item])} onRefresh={() => void load(filters)} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    <ReportsPage reports={reports} selectedReport={selectedReport} exports={exports} sources={sources} knowledgeBases={knowledgeBases} filters={filters} setFilters={setFilters} onOpen={(id) => void open(id)} onClose={() => setSelectedReport(null)} onDownload={(id) => void download(id)} onPreview={preview} onRetryExport={retryExport} onRegenerateExport={regenerateExport} />
  </AppShell>;
}
