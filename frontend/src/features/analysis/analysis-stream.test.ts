import { describe, expect, it } from "vitest";
import { freshSnapshot, mergeAnalysisEvent } from "./analysis-stream";

describe("analysis stream state", () => {
  it("merges retrieval, SQL, query and completion events without exposing raw logs", () => {
    let snapshot = freshSnapshot();
    snapshot = mergeAnalysisEvent(snapshot, { event: "queued", data: { run_id: "run-1" } });
    snapshot = mergeAnalysisEvent(snapshot, { event: "tool_result", data: { tool: "knowledge.search", result_count: 3 } });
    snapshot = mergeAnalysisEvent(snapshot, { event: "sql_draft", data: { sql: "select * from orders" } });
    snapshot = mergeAnalysisEvent(snapshot, { event: "tool_result", data: { tool: "sql.query", row_count: 2 } });
    snapshot = mergeAnalysisEvent(snapshot, { event: "completed", data: { run_id: "run-1", sql: "select * from orders", result: { rows: [{ id: 1 }, { id: 2 }] } } });
    expect(snapshot).toMatchObject({ runId: "run-1", citationCount: 3, rowCount: 2, result: { run_id: "run-1" } });
    expect(snapshot.stages.every((stage) => stage.status === "completed")).toBe(true);
    expect(snapshot.activity.map((item) => item.event)).toContain("分析完成");
  });
  it("marks only the active stage failed and keeps a recoverable reason", () => {
    const started = mergeAnalysisEvent(freshSnapshot(), { event: "step_started", data: { step: "query" } });
    const failed = mergeAnalysisEvent(started, { event: "failed", data: { message: "SQL Guard 拒绝了查询" } });
    expect(failed.error).toBe("SQL Guard 拒绝了查询");
    expect(failed.stages.find((stage) => stage.id === "query")?.status).toBe("failed");
    expect(failed.activity.at(-1)?.message).toBe("SQL Guard 拒绝了查询");
  });
});
