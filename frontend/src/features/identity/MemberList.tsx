export type MemberRow = { user_id: string; display_name: string; email: string; role: string; is_active: boolean };
export function MemberList({ members }: { members: MemberRow[] }) {
  return <section className="source-list list-scroll">{members.length ? members.map((member) => <article className="list-row" key={member.user_id}><div><strong>{member.display_name}</strong><p>{member.email}</p></div><span className={`status-chip ${member.is_active ? "" : "muted"}`}>{member.role} · {member.is_active ? "启用" : "已停用"}</span></article>) : <p className="detail-hint">成员列表暂不可用或当前组织暂无成员。</p>}</section>;
}
