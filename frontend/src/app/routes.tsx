import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { type NavItem } from "./navigation";

const AnalysisRoute = lazy(() =>
  import("../features/analysis/AnalysisRoute").then((module) => ({ default: module.AnalysisRoute })),
);
const DataSourcesRoute = lazy(() =>
  import("../features/datasources/DataSourcesRoute").then((module) => ({ default: module.DataSourcesRoute })),
);
const OperationsOverviewRoute = lazy(() =>
  import("../features/dashboards/OperationsOverviewRoute").then((module) => ({ default: module.OperationsOverviewRoute })),
);
const ReportsRoute = lazy(() =>
  import("../features/reports/ReportsRoute").then((module) => ({ default: module.ReportsRoute })),
);
const SystemStatusRoute = lazy(() =>
  import("../features/system/SystemStatusRoute").then((module) => ({ default: module.SystemStatusRoute })),
);
const DashboardConfigurationRoute = lazy(() =>
  import("../features/dashboards/DashboardConfigurationRoute").then((module) => ({ default: module.DashboardConfigurationRoute })),
);
const ProjectManagementRoute = lazy(() =>
  import("../features/projects/ProjectManagementRoute").then((module) => ({ default: module.ProjectManagementRoute })),
);
const PlatformOrganizationsRoute = lazy(() =>
  import("../features/system/PlatformOrganizationsRoute").then((module) => ({ default: module.PlatformOrganizationsRoute })),
);
const OrganizationAuditRoute = lazy(() =>
  import("../features/identity/OrganizationAuditRoute").then((module) => ({ default: module.OrganizationAuditRoute })),
);
const KnowledgeRoute = lazy(() =>
  import("../features/knowledge/KnowledgeRoute").then((module) => ({ default: module.KnowledgeRoute })),
);
const AgentPlatformRoute = lazy(() =>
  import("../features/agents/AgentPlatformRoute").then((module) => ({ default: module.AgentPlatformRoute })),
);

export const NAV_PATHS: Record<NavItem, string> = {
  "运营总览": "/overview",
  "项目管理": "/project",
  "企业管理": "/platform/organizations",
  "大屏配置": "/dashboard/configuration",
  "分析会话": "/analysis",
  "Agent 平台": "/agent-platform",
  "数据源": "/data-sources",
  "知识库": "/knowledge",
  "报告中心": "/reports",
  "组织与审计": "/audit",
  "系统状态": "/system-status",
};

function RouteLoading() {
  return <main className="route-loading" role="status">正在加载工作区…</main>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={NAV_PATHS["运营总览"]} replace />} />
      <Route path="/analysis" element={<Suspense fallback={<RouteLoading />}><AnalysisRoute /></Suspense>} />
      <Route path="/agent-platform" element={<Suspense fallback={<RouteLoading />}><AgentPlatformRoute /></Suspense>} />
      <Route path="/data-sources" element={<Suspense fallback={<RouteLoading />}><DataSourcesRoute /></Suspense>} />
      <Route path="/overview" element={<Suspense fallback={<RouteLoading />}><OperationsOverviewRoute /></Suspense>} />
      <Route path="/reports" element={<Suspense fallback={<RouteLoading />}><ReportsRoute /></Suspense>} />
      <Route path="/system-status" element={<Suspense fallback={<RouteLoading />}><SystemStatusRoute /></Suspense>} />
      <Route path="/dashboard/configuration" element={<Suspense fallback={<RouteLoading />}><DashboardConfigurationRoute /></Suspense>} />
      <Route path="/project" element={<Suspense fallback={<RouteLoading />}><ProjectManagementRoute /></Suspense>} />
      <Route path="/platform/organizations" element={<Suspense fallback={<RouteLoading />}><PlatformOrganizationsRoute /></Suspense>} />
      <Route path="/audit" element={<Suspense fallback={<RouteLoading />}><OrganizationAuditRoute /></Suspense>} />
      <Route path="/knowledge" element={<Suspense fallback={<RouteLoading />}><KnowledgeRoute /></Suspense>} />
      <Route path="*" element={<Navigate to={NAV_PATHS["运营总览"]} replace />} />
    </Routes>
  );
}
