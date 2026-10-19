import type { NavItem } from "./navigation";

export const NAV_CAPABILITIES: Partial<Record<NavItem, keyof Record<string, boolean>>> = {
  "项目管理": "manage_members",
  "企业管理": "manage_members",
  "大屏配置": "manage_members",
  "分析会话": "run_analysis",
  "Agent 平台": "run_analysis",
  "数据源": "manage_data_sources",
  "知识库": "manage_knowledge",
  "组织与审计": "view_audit",
};

export function canAccessNav(item: NavItem, role: string | undefined, permissions: { roles: Record<string, Record<string, boolean>> } | null): boolean {
  if (!role) return true;
  if (item === "企业管理") return role === "platform_admin";
  const capability = NAV_CAPABILITIES[item];
  if (!capability) return true;
  return permissions?.roles?.[role]?.[capability] ?? ["org_admin", "platform_admin"].includes(role);
}
