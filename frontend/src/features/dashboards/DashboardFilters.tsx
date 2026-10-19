import type { DashboardFilters as DashboardFilterState } from "../../app/types";

type Props = {
  value: DashboardFilterState;
  refreshing: boolean;
  cacheStatus?: string;
  refreshedAt?: string;
  onChange: (next: DashboardFilterState) => void;
  onRefresh: () => void;
  dimensions?: { factories: string[]; product_lines: string[] };
  config?: { refresh_interval_seconds: number };
  canConfigure?: boolean;
  onSaveConfig?: (seconds: number) => void;
};

export function DashboardFilters({ value, refreshing, cacheStatus, refreshedAt, onChange, onRefresh, dimensions, config, canConfigure, onSaveConfig }: Props) {
  return <section className="dashboard-toolbar" aria-label="大屏筛选和刷新">
    <div className="dashboard-filters">
      <label>工厂<select value={value.factory} onChange={(event) => onChange({ ...value, factory: event.target.value })}><option value="">全部工厂</option>{(dimensions?.factories || []).map((factory) => <option key={factory} value={factory}>{factory}</option>)}</select></label>
      <label>产品线<select value={value.productLine} onChange={(event) => onChange({ ...value, productLine: event.target.value })}><option value="">全部产品线</option>{(dimensions?.product_lines || []).map((productLine) => <option key={productLine} value={productLine}>{productLine}</option>)}</select></label>
      <label>时间范围<select value={value.period} onChange={(event) => onChange({ ...value, period: event.target.value as DashboardFilterState["period"] })}><option value="7d">近 7 天</option><option value="30d">近 30 天</option><option value="90d">近 90 天</option></select></label>
    </div>
    <div className="dashboard-refresh-state"><span>{cacheStatus === "redis" ? "缓存命中" : cacheStatus === "queued" ? "刷新排队中" : "数据已同步"}</span><small>{refreshedAt ? new Date(refreshedAt).toLocaleString("zh-CN") : "尚未刷新"}</small>{canConfigure && config && onSaveConfig && <select aria-label="刷新间隔" value={config.refresh_interval_seconds} onChange={(event) => onSaveConfig(Number(event.target.value))}><option value={60}>每 1 分钟</option><option value={300}>每 5 分钟</option><option value={900}>每 15 分钟</option><option value={3600}>每小时</option></select>}<button className="secondary-button" onClick={onRefresh} disabled={refreshing}>{refreshing ? "刷新中..." : "刷新大屏"}</button></div>
  </section>;
}
