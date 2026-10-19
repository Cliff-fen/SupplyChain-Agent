import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import type { Dashboard, DashboardFilters } from "../../app/types";
import type { OrganizationSummary } from "../../app/domain-types";
import { NAV_ITEMS, type NavItem } from "../../app/navigation";
import { AppShell } from "../../components/AppShell";
import { API_BASE, apiRequest } from "../../services/api";
import { loadCharts } from "../../services/charts";
import { AuthScreen } from "../auth/AuthScreen";
import { OperationsOverviewPage } from "./OperationsOverviewPage";

const paths: Record<NavItem, string> = { "运营总览": "/overview", "项目管理": "/project", "企业管理": "/platform/organizations", "大屏配置": "/dashboard/configuration", "分析会话": "/analysis", "Agent 平台": "/agent-platform", "数据源": "/data-sources", "知识库": "/knowledge", "报告中心": "/reports", "组织与审计": "/audit", "系统状态": "/system-status" };
type Dimensions = { factories: string[]; product_lines: string[]; suppliers: string[] };
type DashboardConfig = { dashboard_id: string; refresh_interval_seconds: number; visible_widgets: string[] };
type ChartOption = Parameters<import("../../services/charts-runtime").ChartInstance["setOption"]>[0];

export function OperationsOverviewRoute() {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem("supplymind_token") || "");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [organization, setOrganization] = useState<OrganizationSummary | null>(null);
  const [dimensions, setDimensions] = useState<Dimensions>({ factories: [], product_lines: [], suppliers: [] });
  const [config, setConfig] = useState<DashboardConfig>({ dashboard_id: "", refresh_interval_seconds: 300, visible_widgets: [] });
  const [filters, setFilters] = useState<DashboardFilters>({ factory: "", productLine: "", period: "30d" });
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginOrganization, setLoginOrganization] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [inviteError, setInviteError] = useState("");
  const inviteToken = new URLSearchParams(window.location.search).get("invite") || "";
  const trendRef = useRef<HTMLDivElement>(null);
  const factoryRef = useRef<HTMLDivElement>(null);
  const supplierRef = useRef<HTMLDivElement>(null);
  const api = useCallback(<T,>(path: string, init?: RequestInit) => apiRequest<T>(API_BASE, token, path, init, localStorage.getItem("supplymind_refresh") || undefined, (access, refresh) => { setToken(access); localStorage.setItem("supplymind_token", access); localStorage.setItem("supplymind_refresh", refresh); }), [token]);
  const load = useCallback(async (nextFilters = filters) => {
    setRefreshing(true); setNotice("");
    try {
      const query = new URLSearchParams({ ...(nextFilters.factory ? { factory: nextFilters.factory } : {}), ...(nextFilters.productLine ? { product_line: nextFilters.productLine } : {}), period: nextFilters.period });
      const [nextDashboard, nextDimensions, nextConfig, nextOrganization] = await Promise.all([
        api<Dashboard>(`/dashboards/supply-chain?${query}`), api<Dimensions>("/dashboards/supply-chain/dimensions"), api<DashboardConfig>("/dashboards/supply-chain/config"), api<OrganizationSummary>("/organization"),
      ]);
      setDashboard(nextDashboard); setDimensions(nextDimensions); setConfig(nextConfig); setOrganization(nextOrganization);
    } catch (error) { setNotice(error instanceof Error ? error.message : "运营数据读取失败"); }
    finally { setRefreshing(false); }
  }, [api, filters]);
  useEffect(() => { if (token) void load(); }, [load, token]);
  useEffect(() => {
    if (!dashboard || !trendRef.current) return;
    let disposed = false;
    let charts: { dispose: () => void; resize: () => void }[] = [];
    const render = async () => {
      const echarts = await loadCharts();
      if (disposed || !trendRef.current) return;
      const make = (element: HTMLDivElement, option: ChartOption) => { const chart = echarts.init(element); chart.setOption(option); charts.push(chart); };
      make(trendRef.current, { grid: { left: 12, right: 12, top: 20, bottom: 18, containLabel: true }, tooltip: { trigger: "axis" }, xAxis: { type: "category", boundaryGap: false, data: dashboard.trend.map((item) => item.month) }, yAxis: { type: "value", min: 80, max: 100, axisLabel: { formatter: "{value}%" } }, series: [{ type: "line", smooth: true, data: dashboard.trend.map((item) => item.rate), lineStyle: { width: 3, color: "#15966d" }, itemStyle: { color: "#15966d" }, areaStyle: { color: "rgba(21,150,109,.1)" } }] });
      const ranking = (element: HTMLDivElement | null, values: { label: string; value: number }[], color: string) => element && make(element, { grid: { left: 82, right: 28, top: 8, bottom: 8 }, xAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}%" } }, yAxis: { type: "category", inverse: true, data: values.map((item) => item.label) }, series: [{ type: "bar", data: values.map((item) => item.value), barWidth: 16, itemStyle: { color } }] });
      ranking(factoryRef.current, (dashboard.rankings?.factories || []).map((item) => ({ label: item.factory || "未命名", value: Number(item.rate || 0) })), "#15966d");
      ranking(supplierRef.current, (dashboard.rankings?.suppliers || []).map((item) => ({ label: item.supplier_name || "未命名", value: Number(item.rate || 0) })), "#4c8fba");
    };
    const observer = new ResizeObserver(() => charts.forEach((chart) => chart.resize()));
    observer.observe(trendRef.current); void render();
    return () => { disposed = true; observer.disconnect(); charts.forEach((chart) => chart.dispose()); };
  }, [dashboard]);
  const changeFilters = (next: DashboardFilters) => { setFilters(next); void load(next); };
  const saveConfig = (seconds: number) => { setRefreshing(true); void api<DashboardConfig>("/dashboards/supply-chain/config", { method: "PATCH", body: JSON.stringify({ refresh_interval_seconds: seconds, visible_widgets: config.visible_widgets }) }).then(setConfig).catch((error) => setNotice(error instanceof Error ? error.message : "刷新策略保存失败")).finally(() => setRefreshing(false)); };
  const openAnalysis = (question?: string) => navigate(`/analysis${question ? `?question=${encodeURIComponent(question)}` : ""}`);
  const login = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setLoginError("");
    if (!loginEmail.trim() || !loginPassword || !loginOrganization.trim()) { setLoginError("请填写邮箱、密码和组织标识"); return; }
    setLoginBusy(true);
    try {
      const session = await api<{ access_token: string; refresh_token?: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email: loginEmail.trim(), password: loginPassword, organization_slug: loginOrganization.trim() }) });
      localStorage.setItem("supplymind_token", session.access_token);
      if (session.refresh_token) localStorage.setItem("supplymind_refresh", session.refresh_token);
      setToken(session.access_token);
    } catch (error) { setLoginError(error instanceof Error ? error.message : "登录失败"); setLoginPassword(""); }
    finally { setLoginBusy(false); }
  };
  const acceptInvitation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setInviteError("");
    const values = new FormData(event.currentTarget);
    setLoginBusy(true);
    try {
      const response = await fetch(`${API_BASE}/members/invitations/accept`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: inviteToken, display_name: values.get("display_name"), password: values.get("password") }) });
      const session = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(session.detail || "邀请接受失败"));
      localStorage.setItem("supplymind_token", session.access_token); localStorage.setItem("supplymind_refresh", session.refresh_token || ""); setToken(session.access_token);
    } catch (error) { setInviteError(error instanceof Error ? error.message : "邀请接受失败"); }
    finally { setLoginBusy(false); }
  };
  if (!token) return <AuthScreen inviteToken={inviteToken} loginEmail={loginEmail} loginPassword={loginPassword} loginOrganization={loginOrganization} showPassword={showPassword} loginBusy={loginBusy} oidcBusy={false} loginError={loginError} inviteError={inviteError} onLogin={login} onAcceptInvitation={acceptInvitation} onStartOidc={() => { if (!loginOrganization.trim()) { setLoginError("请先填写组织标识"); return; } window.location.assign(`${API_BASE}/auth/oidc/start?organization_slug=${encodeURIComponent(loginOrganization.trim())}`); }} onEmailChange={setLoginEmail} onPasswordChange={setLoginPassword} onOrganizationChange={setLoginOrganization} onTogglePassword={() => setShowPassword((value) => !value)} />;
  return <AppShell nav="运营总览" items={NAV_ITEMS} organizationName={organization?.name} onNavigate={(item) => navigate(paths[item])} onRefresh={() => void load()} onLogout={() => { localStorage.clear(); navigate("/"); }}>
    {notice && <p className="form-notice" role="status">{notice}</p>}
    <OperationsOverviewPage dashboard={dashboard} dimensions={dimensions} filters={filters} refreshing={refreshing} config={config} canConfigure={["org_admin", "platform_admin"].includes(organization?.role || "")} onChangeFilters={changeFilters} onRefresh={() => void load()} onSaveConfig={saveConfig} onOpenAnalysis={openAnalysis} onStartRetailAnalysis={() => openAnalysis("分析真实交易数据的国家销售额、退货风险与客户价值")} chartRef={trendRef} factoryChartRef={factoryRef} supplierChartRef={supplierRef} question="" setQuestion={() => undefined} events={[]} result={null} busy={false} onSubmit={(event) => event.preventDefault()} onDownloadReport={async () => undefined} sources={[]} knowledgeBases={[]} sourceId="" knowledgeBaseId="" setSourceId={() => undefined} setKnowledgeBaseId={() => undefined} showAnalysisPanel={false} />
  </AppShell>;
}
