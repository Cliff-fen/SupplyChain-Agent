type Task = { id: string; document_id: string; status: string; dead_letter?: boolean; attempts?: number; error_message?: string; created_at: string };

export function DeadLetterPanel({ tasks, onRetry }: { tasks: Task[]; onRetry: (id: string) => void }) {
  const dead = tasks.filter((task) => task.dead_letter || task.status === "failed");
  return <section className="project-access"><div><p className="section-kicker">WORKER / RECOVERY</p><h3>失败与死信任务</h3><p>仅组织管理员可重新入队，所有操作会记录审计。</p></div><div className="access-list">{dead.length ? dead.map((task) => <div key={task.id} className="system-task-row"><span><b className="access-dot blocked" />{task.status} · 尝试 {task.attempts || 0}</span><small>{task.error_message || "任务失败，等待人工处理"}</small><button className="text-button" onClick={() => onRetry(task.id)}>重新入队</button></div>) : <span>暂无失败或死信任务</span>}</div></section>;
}
