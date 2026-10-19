type Props = { title: string; copy: string };

export function EmptyState({ title, copy }: Props) {
  return <div className="empty-state"><span>—</span><strong>{title}</strong><p>{copy}</p></div>;
}
