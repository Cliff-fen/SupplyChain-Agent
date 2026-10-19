# SupplyChain Agent 前端架构

## 运行边界

- `frontend/src/main.tsx` 只负责挂载应用。
- `app/` 管理 Provider、路由、查询客户端和全局错误边界。
- `design-system/` 管理语义令牌和可访问基础组件；业务页面不能直接使用 Radix 原语。
- `components/` 管理跨领域复合组件，如应用壳、状态页、数据表和 Trace ID 提示。
- `features/<domain>/` 管理领域页面、组件、API hooks、类型和测试。运营总览、分析、项目管理、数据源、知识库、报告、组织审计、系统状态和大屏配置均已有独立页面。
- `mocks/` 仅可由 `VITE_DEMO_MODE=true` 使用，生产环境不得静默使用演示数据。

## 质量门槛

```powershell
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

单元测试使用 Vitest、Testing Library 和 MSW。E2E 使用 Playwright，覆盖深链登录、桌面领域导航、移动端“更多”导航以及只读成员的受限深链重定向。每次视觉变更同时保留桌面与移动端截图，并检查键盘可达性、窄屏布局、加载/空/错误/无权限状态。

## 响应式导航

- 桌面端使用完整侧边导航。
- 760px 以下仅将运营总览、项目管理、分析会话、数据源、知识库置于底部；企业管理、大屏配置、报告、审计和系统状态收纳至“更多”。
- 所有移动端导航操作的最小触控高度为 44px，并使用 `viewport-fit=cover` 与安全区内边距。

## API 规则

领域 API hooks 必须使用 `services/api.ts`，保留刷新令牌、组织上下文和 Trace ID。错误统一由 `services/api-errors.ts` 映射为认证、权限、资源不存在、冲突、校验、限流、服务端和网络状态。
