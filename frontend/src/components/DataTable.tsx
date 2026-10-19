import type { ReactNode } from "react";
import styles from "./shared.module.css";

export type DataColumn<T> = { id: string; header: string; cell: (row: T) => ReactNode };
export function DataTable<T extends { id?: string }>({ rows, columns, empty }: { rows: T[]; columns: DataColumn<T>[]; empty?: ReactNode }) {
  if (!rows.length) return <>{empty}</>;
  return <div className={styles.tableWrap}><table className={styles.table}><thead><tr>{columns.map((column) => <th key={column.id}>{column.header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id || index}>{columns.map((column) => <td key={column.id}>{column.cell(row)}</td>)}</tr>)}</tbody></table></div>;
}
