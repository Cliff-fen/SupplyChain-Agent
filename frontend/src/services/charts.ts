let chartsPromise: Promise<typeof import("./charts-runtime")> | undefined;

/** Load ECharts only when the operations dashboard is actually opened. */
export function loadCharts(): Promise<typeof import("./charts-runtime")> {
  chartsPromise ??= import("./charts-runtime");
  return chartsPromise;
}
