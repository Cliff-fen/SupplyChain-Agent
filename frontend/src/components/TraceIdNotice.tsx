import styles from "./shared.module.css";
export function TraceIdNotice({ traceId }: { traceId?: string }) { return traceId ? <p className={styles.trace}>Trace ID: <code>{traceId}</code></p> : null; }
