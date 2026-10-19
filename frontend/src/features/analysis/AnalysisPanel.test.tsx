import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalysisPanel } from "./AnalysisPanel";

const base = { question: "分析库存风险", setQuestion: vi.fn(), loading: false, onSubmit: vi.fn(), sources: [{ id: "active", name: "可用演示库", status: "active" }, { id: "failed", name: "失败演示库", status: "failed" }], knowledgeBases: [{ id: "knowledge", name: "供应链知识库" }], sourceId: "", knowledgeBaseId: "", setSourceId: vi.fn(), setKnowledgeBaseId: vi.fn(), stages: [], citationCount: 0, chartReady: false, result: null };

describe("AnalysisPanel", () => {
  it("shows a cited knowledge answer even without SQL rows", () => {
    render(<AnalysisPanel {...base} citationCount={1} result={{ result: {
      rows: [], direct_answer: "生产达成率为完工数量除以计划数量。",
      citations: [{ document_name: "指标口径.md", text: "生产达成率定义" }],
    } }} />);
    expect(screen.getByText("结论已生成")).toBeVisible();
    expect(screen.getByText("生产达成率为完工数量除以计划数量。")).toBeVisible();
    expect(screen.queryByText("未返回可用于判断的数据")).not.toBeInTheDocument();
  });
  it("does not present an unsupported answer as a verified conclusion", () => {
    render(<AnalysisPanel {...base} result={{ result: { rows: [], direct_answer: "没有证据的回答" } }} />);
    expect(screen.getByText("空结果")).toBeVisible();
    expect(screen.queryByText("没有证据的回答")).not.toBeInTheDocument();
  });
  it("does not offer failed sources for a new analysis", () => {
    render(<AnalysisPanel {...base} />);
    expect(screen.getByRole("option", { name: "可用演示库" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "失败演示库" })).not.toBeInTheDocument();
  });
  it("shows a recoverable API failure instead of an empty result", () => {
    render(<AnalysisPanel {...base} error="所选数据源当前不可用于分析（Trace ID: abc）" />);
    expect(screen.getByText("所选数据源当前不可用于分析（Trace ID: abc）")).toBeVisible();
    expect(screen.getByText("实时运行状态")).toBeVisible();
  });
});
