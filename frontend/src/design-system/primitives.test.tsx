import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button, ConfirmDialog } from "./primitives";

describe("design-system primitives", () => {
  it("disables a loading action", () => {
    render(<Button loading>保存</Button>);
    expect(screen.getByRole("button", { name: "处理中..." })).toBeDisabled();
  });

  it("confirms a destructive action", async () => {
    const user = userEvent.setup();
    const confirm = vi.fn();
    render(<ConfirmDialog open onOpenChange={vi.fn()} title="删除资源" description="不可恢复" onConfirm={confirm} />);
    await user.click(screen.getByRole("button", { name: "确认" }));
    expect(confirm).toHaveBeenCalledOnce();
  });
});
