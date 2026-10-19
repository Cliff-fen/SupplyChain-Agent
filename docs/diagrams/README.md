# 流程图

图示根据当前状态图、执行器、事件持久化和报告服务绘制。

- 系统架构与 Agent 执行图：源码位于根目录 [README](../../README.md)。
- 持久化恢复时序与报告追溯图：源码位于 [架构说明](../ARCHITECTURE.md)。

## 高清图

- [系统架构](system-architecture.svg)
- [Agent 执行流程](agent-workflow.svg)
- [持久化、审批与 SSE 恢复](persistence-recovery.svg)
- [报告与来源追踪](report-provenance.svg)

Markdown 中的 Mermaid 是可编辑源码，SVG 是同一源码的渲染版本。
修改节点、连线或业务行为时，应同时更新源码和 SVG。

使用 Mermaid CLI 渲染两个 Markdown 文件，并按本目录文件名保存输出。
统一样式位于 [mermaid-config.json](mermaid-config.json)；不需要任何服务密钥：

```bash
npx --package @mermaid-js/mermaid-cli mmdc -i README.md -o docs/diagrams/overview.svg -c docs/diagrams/mermaid-config.json --no-font-embed
npx --package @mermaid-js/mermaid-cli mmdc -i docs/ARCHITECTURE.md -o docs/diagrams/persistence.svg -c docs/diagrams/mermaid-config.json --no-font-embed
```

两次命令分别产生 `overview-1.svg` / `overview-2.svg` 和
`persistence-1.svg` / `persistence-2.svg`，依次对应系统架构、Agent 执行、
持久化恢复和报告追溯。渲染需要可用的 Chromium 浏览器与中文字体。
