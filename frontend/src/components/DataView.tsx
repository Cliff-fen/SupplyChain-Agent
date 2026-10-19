import type { ReactNode } from "react";

type Props = { kicker: string; title: string; copy: string; children: ReactNode };

export function DataView({ kicker, title, copy, children }: Props) {
  return <section className="data-view"><div className="view-intro"><div><p className="section-kicker">{kicker}</p><h1>{title}</h1><p>{copy}</p></div></div><div className="source-list">{children}</div></section>;
}
