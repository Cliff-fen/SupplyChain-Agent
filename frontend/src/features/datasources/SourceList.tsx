export type SourceRow = { id: string; name: string; engine: string; host: string; port: number; database_name: string; allowed_tables: string[]; status?: string };
type Props = { sources: SourceRow[]; activeAction?: string | null; onOpen: (id: string) => void; onTest: (id: string) => void; onSync: (id: string) => void; onToggle: (id: string) => void };
export function SourceList({ sources, activeAction, onOpen, onTest, onSync, onToggle }: Props) {
  return <section className="source-list list-scroll">{sources.length ? sources.map((source) => {
    const disabled = source.status === "disabled";
    const label = disabled ? "已停用" : source.status === "failed" ? "连接异常" : source.status === "syncing" ? "同步中" : "已启用";
    const action = activeAction?.startsWith(`source:${source.id}:`) ? activeAction.split(":").at(-1) : null;
    const working = !!action;
    return <article className="list-row datasource-row" key={source.id}><button className="row-main-button" onClick={() => onOpen(source.id)} disabled={working}><strong>{source.name}</strong><p>{source.engine} · {source.host}:{source.port} · {source.database_name}</p></button><span className={`status-chip ${disabled || source.status === "failed" ? "muted" : ""}`}>{label} · {source.allowed_tables.length} 张表</span><div className="row-actions"><button className="secondary-button" onClick={() => onTest(source.id)} disabled={working || disabled || source.status === "syncing"}>{action === "test" ? "测试中..." : "测试连接"}</button><button className="secondary-button" onClick={() => onSync(source.id)} disabled={working || disabled || source.status === "syncing"}>{action === "sync" ? "已提交..." : "同步 Schema"}</button><button className="text-button" onClick={() => onToggle(source.id)} disabled={working}>{action === "toggle" ? "处理中..." : disabled ? "启用" : "停用"}</button></div></article>;
  }) : <p className="detail-hint">还没有数据源，请由组织管理员接入只读数据库。</p>}</section>;
}
