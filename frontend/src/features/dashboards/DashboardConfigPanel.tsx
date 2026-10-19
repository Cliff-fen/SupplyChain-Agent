import { useState } from "react";
type Props = { config: { refresh_interval_seconds: number; visible_widgets: string[] }; onSave: (seconds: number, widgets: string[]) => Promise<void> };
const widgets = [["delivery", "采购交付"], ["production", "生产达成"], ["inventory", "库存健康"], ["quality", "质量合格"], ["fulfillment", "订单履约"], ["retail", "真实交易经营"], ["trend", "生产趋势"], ["factories", "工厂排行"], ["suppliers", "供应商排行"], ["anomalies", "异常清单"]];

export function DashboardConfigPanel({ config, onSave }: Props) {
  const [saving, setSaving] = useState(false);
  const selected = new Set(config.visible_widgets);
  return <form className="dashboard-config-panel" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); setSaving(true); void onSave(Number(form.get("refresh") || 300), widgets.map(([key]) => key).filter((key) => form.get(key) === "on")).finally(() => setSaving(false)); }}><div className="panel-heading"><div><p className="section-kicker">DASHBOARD / GOVERNANCE</p><h3>大屏组件配置</h3><p>保存后仅影响当前组织的指标显隐和刷新周期。</p></div></div><label>刷新周期<select name="refresh" defaultValue={String(config.refresh_interval_seconds)}><option value="60">每 1 分钟</option><option value="300">每 5 分钟</option><option value="900">每 15 分钟</option><option value="3600">每小时</option></select></label><div className="dashboard-widget-grid">{widgets.map(([key, label]) => <label key={key}><input type="checkbox" name={key} defaultChecked={!config.visible_widgets.length || selected.has(key)} />{label}</label>)}</div><button className="primary-button" disabled={saving}>{saving ? "保存中..." : "保存大屏配置"}</button></form>;
}
