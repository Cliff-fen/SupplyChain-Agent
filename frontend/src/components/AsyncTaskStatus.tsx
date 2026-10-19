import { Badge } from "../design-system/primitives";
const toneFor = (status: string) => status === "completed" || status === "ready" ? "success" : status === "failed" || status === "cancelled" ? "danger" : status === "running" || status === "queued" ? "warning" : "neutral";
export function AsyncTaskStatus({ status, detail }: { status: string; detail?: string }) { return <span title={detail}><Badge tone={toneFor(status) as "success" | "warning" | "danger" | "neutral"}>{status}</Badge></span>; }
