import { use, init, type ECharts } from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

export type ChartInstance = ECharts;
export { init };
