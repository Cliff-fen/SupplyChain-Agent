import { DataView } from "../../components/DataView";
import { OrganizationAdminPanel, type PlatformOrganization } from "./OrganizationAdminPanel";

export function PlatformOrganizationsPage({ organizations, onToggle, onRename }: { organizations: PlatformOrganization[]; onToggle: (item: PlatformOrganization) => Promise<void>; onRename: (item: PlatformOrganization, name: string) => Promise<void> }) {
  return <DataView kicker="PLATFORM / TENANTS" title="企业管理" copy="集中管理企业组织与平台级访问状态。"><OrganizationAdminPanel organizations={organizations} onToggle={onToggle} onRename={onRename} /></DataView>;
}
