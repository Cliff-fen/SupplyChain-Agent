import { DataView } from "../../components/DataView";
import { DeadLetterPanel } from "./DeadLetterPanel";
import { SystemStatusPanel, type SystemStatusData } from "./SystemStatusPanel";

type FailedTask = { id: string; document_id: string; status: string; dead_letter?: boolean; attempts?: number; error_message?: string; created_at: string };
export function SystemStatusPage({ details, showDeadLetters, failedTasks, onRetry }: { details: SystemStatusData | null; showDeadLetters: boolean; failedTasks: FailedTask[]; onRetry: (id: string) => void }) {
  return <DataView kicker="SYSTEM / OBSERVABILITY" title="系统状态" copy="查看平台依赖、Worker 队列、模型和组织数据源的实时状态。"><SystemStatusPanel details={details} />{showDeadLetters && <DeadLetterPanel tasks={failedTasks} onRetry={onRetry} />}</DataView>;
}
