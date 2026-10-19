type Props = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
};

export function Pagination({ page, pageSize, total, onPageChange, onPageSizeChange }: Props) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= 0) return null;
  return <div className="pagination" aria-label="分页"><span>共 {total} 条</span><label>每页<select value={pageSize} onChange={(event) => onPageSizeChange?.(Number(event.target.value))}><option value="10">10</option><option value="20">20</option><option value="50">50</option></select></label><button className="secondary-button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>上一页</button><strong>{page} / {pages}</strong><button className="secondary-button" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>下一页</button></div>;
}
