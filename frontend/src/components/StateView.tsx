import { EmptyState, ErrorState, Skeleton } from "../design-system/primitives";

type Props = { state: "loading" | "empty" | "error"; title?: string; description?: string; retry?: () => void };
export function StateView({ state, title, description, retry }: Props) {
  if (state === "loading") return <Skeleton lines={4} />;
  if (state === "error") return <ErrorState title={title} description={description || "请稍后重试。"} retry={retry} />;
  return <EmptyState title={title || "暂无内容"} description={description || "当前筛选条件下没有可显示的结果。"} />;
}
