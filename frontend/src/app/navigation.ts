export const NAV_ITEMS = ["运营总览", "项目管理", "企业管理", "大屏配置", "分析会话", "Agent 平台", "数据源", "知识库", "报告中心", "组织与审计", "系统状态"] as const;

export type NavItem = (typeof NAV_ITEMS)[number];
