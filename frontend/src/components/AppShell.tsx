import { useState, type ReactNode } from "react";
import type { NavItem } from "../app/navigation";
import { useHermes } from "../app/hermes";

type Props = {
  nav: string;
  items: readonly NavItem[];
  organizationName?: string;
  systemStatus?: "ready" | "degraded";
  busy?: boolean;
  topbarActions?: ReactNode;
  children: ReactNode;
  onNavigate: (item: NavItem) => void;
  onRefresh: () => void;
  onLogout: () => void;
};

export function AppShell({ nav, items, organizationName, systemStatus = "ready", topbarActions, children, onNavigate, onRefresh, onLogout }: Props) {
  const [moreOpen, setMoreOpen] = useState(false);
  const hermes = useHermes();
  const primaryItems = items.filter((item) => ["运营总览", "项目管理", "分析会话", "数据源", "知识库"].includes(item));
  const secondaryItems = items.filter((item) => !primaryItems.includes(item));
  const navigateMobile = (item: NavItem) => { setMoreOpen(false); onNavigate(item); };
  return <main className="app-shell"><aside className="sidebar"><div className="sidebar-top"><button className="brand-button" onClick={() => onNavigate("运营总览")} aria-label="返回运营总览"><span className="wordmark"><span className="wordmark-mark">S</span><span>SupplyChain Agent</span></span></button></div><div className="workspace-switch"><span className="workspace-dot" /><span><small>当前组织</small><strong>{organizationName || "当前组织"}</strong></span></div><nav className="desktop-nav" aria-label="主导航">{items.map((item, index) => <button key={item} className={`nav-item ${nav === item ? "active" : ""}`} onClick={() => onNavigate(item)}><span>{item}</span><small>{index ? `0${index}` : "TODAY"}</small></button>)}</nav><div className="sidebar-footer"><div className="status-line"><span className="status-dot" />{systemStatus === "ready" ? "所有系统正常" : "依赖异常，请查看监控"}</div><button className="logout-button" onClick={onLogout}>退出工作区</button></div></aside><section className="workspace"><header className="topbar"><div><p className="section-kicker">{nav === "运营总览" ? "OPERATIONS / OVERVIEW" : `WORKSPACE / ${nav.toUpperCase()}`}</p><h2>{nav}</h2></div><div className="topbar-actions"><span className="hermes-status-pill" title={hermes.capabilities.map((item) => item.label).join(" / ")}>{hermes.name} {hermes.version}</span><span className="last-sync">最后同步 <strong>刚刚</strong></span><button className="icon-button" onClick={onRefresh} aria-label="刷新数据" title="刷新数据">↻</button>{topbarActions}</div></header>{children}</section><nav className="mobile-nav" aria-label="移动主导航">{primaryItems.map((item) => <button key={item} className={`mobile-nav-item ${nav === item ? "active" : ""}`} onClick={() => navigateMobile(item)}>{item}</button>)}<button className={`mobile-nav-item ${secondaryItems.includes(nav as NavItem) ? "active" : ""}`} onClick={() => setMoreOpen((open) => !open)} aria-expanded={moreOpen} aria-controls="mobile-more-menu">更多</button></nav>{moreOpen && <section className="mobile-more-menu" id="mobile-more-menu" aria-label="更多工作区功能">{secondaryItems.map((item) => <button key={item} className={nav === item ? "active" : ""} onClick={() => navigateMobile(item)}>{item}</button>)}<button className="mobile-logout" onClick={onLogout}>退出工作区</button></section>}</main>;
}
